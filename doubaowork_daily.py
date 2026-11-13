#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
豆包工作每日奖励 - 青龙 / GitHub Actions 单文件脚本

协议依据：Agent2API Agent2Providers v3.4.2 的 doubaowork provider。
本脚本是独立的 clean-room 实现，不依赖 3.3 插件进程，也不复制其源码。

流程：
  Cookie -> POST /alice/user/launch
         -> POST /alice/ug/campaign/v3/detail/（或 /campaign/list/）
         -> 找唯一 daily_checkin 任务
         -> 先把 pending 原子写入状态文件
         -> POST /alice/ug/campaign/landing/checkin  {"scene": campaign_group_code}
         -> 回执只认 data.checked_in=true，再以详情 checked_in_today=true 确认

环境变量：
  DOUBAOWORK_COOKIES    多账号，每行一个：备注|sessionid=...; sessionid_ss=...
  DOUBAOWORK_COOKIE     单账号 Cookie
  DOUBAOWORK_ACCOUNTS_FILE  可选 JSON 账号文件
  DOUBAOWORK_DEVICE_ID / WEB_ID / FINGERPRINT  可选，Cookie 里没有时补充
  DOUBAOWORK_USER_AGENT / CLIENT_VERSION        可选
  DOUBAOWORK_PROXY      可选代理
  DOUBAOWORK_STATE_FILE  可选 pending 台账路径
  DOUBAOWORK_LOCK_FILE   可选固定锁文件路径
  DOUBAOWORK_NO_NOTIFY=1  关闭通知

命令：
  python doubaowork_daily.py
  python doubaowork_daily.py --query
  python doubaowork_daily.py --only 1
  python doubaowork_daily.py --no-notify
  python doubaowork_daily.py --version

依赖：requests
"""

import argparse
import errno
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

import requests
import urllib3

urllib3.disable_warnings()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_URL = os.getenv("DOUBAOWORK_BASE_URL", "").strip().rstrip("/") or "https://www.doubao.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)
DEFAULT_CLIENT_VERSION = "2.33.5"
RUNTIME_VERSION = "3.42.2"
V3_GROUP = "pc_incentive_task_mvp_v3"
LEGACY_CLAIM_PATH = "/alice/ug/campaign/item/reward/claim/"
CLAIM_PATH = "/alice/ug/campaign/landing/checkin"
CLAIM_ENDPOINT_ITEM_REWARD = "item_reward"
CLAIM_ENDPOINT_LANDING_CHECKIN = "landing_checkin"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.getenv("DOUBAOWORK_STATE_FILE", "").strip() or os.path.join(
    SCRIPT_DIR, "doubaowork_state.json"
)
__version__ = "1.3.2"
STATE_VERSION = 1
CONFIRM_BUDGET_SECONDS = 18.0
CONFIRM_POLL_DELAYS = (0.0, 2.0, 4.0)
RETRY_GAP_MS = 10 * 60 * 1000
CONFIRM_WINDOW_MS = 30 * 60 * 1000
MAX_ROUNDS = 4
DIRECT_REJECT_STATUSES = frozenset((401, 403, 429))
CONDITIONAL_REJECT_STATUSES = frozenset((400, 404, 405, 422))
AUTH_BUSINESS_CODES = frozenset((710012001,))
RATE_LIMIT_BUSINESS_CODES = frozenset((710022004,))
EXPLICIT_REJECT_BUSINESS_CODES = AUTH_BUSINESS_CODES | RATE_LIMIT_BUSINESS_CODES
OFFICIAL_SYSTEM_ERROR_CODE = 710010702
CONFIRMING_MARKERS = ("领取结果确认中", "确认中", "稍后重试")
BEIJING_TZ = timezone(timedelta(hours=8))


class DoubaoError(RuntimeError):
    def __init__(
        self,
        message: str,
        status: int = 0,
        code: Any = None,
        diagnostic: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.status = int(status or 0)
        self.code = code
        self.diagnostic = dict(diagnostic or {})


class DoubaoAuthError(DoubaoError):
    pass


class DoubaoRateLimitError(DoubaoError):
    pass


def log(message: str) -> None:
    print(str(message), flush=True)


def mask_cookie(value: str) -> str:
    value = str(value or "")
    if len(value) <= 18:
        return "***"
    return value[:10] + "..." + value[-6:]


_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(sessionid(?:_ss)?|sid_guard|uid_tt(?:_ss)?|passport_csrf_token|"
    r"cookie(?:header)?|authorization|access_token|refresh_token|id_token|token|"
    r"device_id|web_id|s_v_web_id|fp)\s*[:=]\s*[\"']?([^\"'\s;,}&]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_JWT_TOKEN = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_PHONE_NUMBER = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")


def _configured_secret_values() -> List[str]:
    names = (
        "PUSHPLUS_TOKEN",
        "BARK_URL",
        "WECOM_WEBHOOK",
        "DOUBAOWORK_DEVICE_ID",
        "DOUBAOWORK_WEB_ID",
        "DOUBAOWORK_FINGERPRINT",
        "DOUBAOWORK_PROXY",
    )
    return [value for value in (os.getenv(name, "").strip() for name in names) if value]


def redact_sensitive_text(value: Any, secrets: Iterable[str] = ()) -> str:
    """Remove credential-shaped values before a log or notification leaves the process."""
    text = str(value or "")
    explicit_values = {str(item) for item in secrets if str(item)}
    for secret in sorted(explicit_values, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    configured_values = {str(item) for item in _configured_secret_values() if len(str(item)) >= 6}
    for secret in sorted(configured_values, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    text = _SENSITIVE_ASSIGNMENT.sub(
        lambda match: match.group(1) + "=[REDACTED]",
        text,
    )
    text = _BEARER_TOKEN.sub("Bearer [REDACTED]", text)
    text = _JWT_TOKEN.sub("[REDACTED_TOKEN]", text)
    text = _PHONE_NUMBER.sub("[REDACTED_PHONE]", text)
    return text[:500]


def account_secret_values(account: Optional["Account"]) -> List[str]:
    if account is None:
        return []
    values = [account.cookie, *account.cookie_pairs.values()]
    for value in (
        account.device_id,
        account.web_id,
        account.fingerprint,
        account.proxy,
        account.user_agent,
        account.client_version,
    ):
        if value:
            values.append(value)
    if account.proxy:
        try:
            parsed = urlsplit(
                account.proxy if "://" in account.proxy else "http://" + account.proxy
            )
            for value in (parsed.username, parsed.password):
                if value:
                    values.extend((value, unquote(value)))
        except ValueError:
            pass
    return [value for value in values if value]


def _session_cookie_shape(account: Optional["Account"]) -> str:
    if account is None:
        return "unknown"
    session_id = account.cookie_pairs.get("sessionid", "")
    session_id_ss = account.cookie_pairs.get("sessionid_ss", "")
    if session_id and session_id_ss:
        return "both_equal" if session_id == session_id_ss else "both_distinct"
    if session_id:
        return "sessionid_only"
    if session_id_ss:
        return "sessionid_ss_only"
    return "missing"


def _device_context_shape(account: Optional["Account"]) -> str:
    if account is None:
        return "unknown"
    if account.device_id:
        return "device_id"
    if account.fingerprint:
        return "fingerprint"
    return "none"


def build_diagnostic(
    account: Optional["Account"],
    action: str,
    client: Any,
    pending: str,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[BaseException] = None,
) -> Dict[str, Any]:
    client_last = getattr(client, "last_diagnostic", {}) if client is not None else {}
    client_last = client_last if isinstance(client_last, dict) else {}
    error_last = getattr(error, "diagnostic", {}) if error is not None else {}
    error_last = error_last if isinstance(error_last, dict) and error_last else {}
    last = error_last or client_last
    secrets = account_secret_values(account)
    if error is not None:
        message = str(error)
        business_code = getattr(error, "code", None)
    elif isinstance(result, dict):
        message = str(result.get("message", ""))
        business_code = result.get("business_code")
    else:
        message = str(last.get("message", ""))
        business_code = last.get("business_code")
    if business_code is None:
        business_code = last.get("business_code")

    checked_in_today: Optional[bool] = None
    if isinstance(result, dict) and "checked_in_today" in result:
        checked_value = result.get("checked_in_today")
        checked_in_today = checked_value if isinstance(checked_value, bool) else None
    elif isinstance(last.get("checked_in_today"), bool):
        checked_in_today = last["checked_in_today"]
    elif isinstance(client_last.get("checked_in_today"), bool):
        checked_in_today = client_last["checked_in_today"]

    return {
        "action": action,
        "account": redact_sensitive_text(account.name if account else "", secrets),
        "request_path": last.get("request_path"),
        "http_status": last.get("http_status"),
        "business_code": business_code,
        "message": redact_sensitive_text(message, secrets),
        "upstream_message": redact_sensitive_text(last.get("message", ""), secrets),
        "checked_in_today": checked_in_today,
        "pending": pending,
        "session_cookie_shape": _session_cookie_shape(account),
        "device_context": _device_context_shape(account),
    }


def log_diagnostic(
    account: Optional["Account"],
    action: str,
    client: Any,
    pending: str,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[BaseException] = None,
) -> None:
    payload = build_diagnostic(account, action, client, pending, result, error)
    log("   🩺 诊断: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def first_text(value: Any, keys: Iterable[str]) -> str:
    if not isinstance(value, dict):
        return ""
    for key in keys:
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, (int, float)):
            return str(item)
    return ""


def number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def integer(value: Any) -> Optional[int]:
    parsed = number(value)
    if parsed is None:
        return None
    return int(parsed)


def exact_integer(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() else None
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"[+-]?[0-9]+", text):
            return int(text)
    return None


def now_ms() -> int:
    return int(time.time() * 1000)


def beijing_date_key(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, BEIJING_TZ).strftime("%Y-%m-%d")


def _valid_date_key(value: str) -> bool:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") == value
    except (TypeError, ValueError):
        return False


def _cookie_pairs_from_json(value: Any) -> List[Tuple[str, str]]:
    result: List[Tuple[str, str]] = []
    if isinstance(value, dict):
        for name, item in value.items():
            if isinstance(item, str):
                result.append((str(name), item))
        return result
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain") or "")
            path = str(item.get("path") or "/")
            if domain and domain not in (
                "doubao.com",
                ".doubao.com",
                "www.doubao.com",
                ".www.doubao.com",
            ):
                continue
            if path not in ("", "/"):
                continue
            name = str(item.get("name") or "")
            value = item.get("value")
            if name and isinstance(value, str):
                result.append((name, value))
    return result


def parse_cookie(raw: str) -> Dict[str, str]:
    text = str(raw or "").strip()
    if not text:
        raise DoubaoError("Cookie 为空")
    pairs: List[Tuple[str, str]] = []
    if text.startswith("{") or text.startswith("["):
        try:
            pairs = _cookie_pairs_from_json(json.loads(text))
        except Exception as error:
            raise DoubaoError("Cookie JSON 格式无效: %s" % str(error)[:80])
    else:
        for part in text.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            name, value = part.split("=", 1)
            pairs.append((name.strip(), value.strip().strip('"')))

    result: Dict[str, str] = {}
    name_re = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
    for name, value in pairs:
        if not name or not name_re.fullmatch(name):
            continue
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
            raise DoubaoError("Cookie 含非法控制字符")
        if value:
            result[name] = value
    if not any(result.get(name) for name in ("sessionid", "sessionid_ss")):
        raise DoubaoAuthError(
            "Cookie 缺少 sessionid / sessionid_ss，请重新登录豆包工作后复制完整 Cookie"
        )
    size = sum(len(name) + len(value) + 3 for name, value in result.items())
    if size > 128 * 1024:
        raise DoubaoError("Cookie 过长")
    return result


def cookie_header(pairs: Dict[str, str]) -> str:
    return "; ".join("%s=%s" % (name, value) for name, value in pairs.items())


@dataclass
class Account:
    name: str
    cookie: str
    cookie_pairs: Dict[str, str]
    user_agent: str = DEFAULT_USER_AGENT
    client_version: str = DEFAULT_CLIENT_VERSION
    device_id: str = ""
    web_id: str = ""
    fingerprint: str = ""
    proxy: str = ""


def account_ledger_key(account: Account) -> str:
    identity = account.cookie_pairs.get("sessionid") or account.cookie_pairs.get("sessionid_ss")
    if not identity:
        raise DoubaoError("账号缺少可用于签到台账的身份 Cookie")
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


@dataclass
class PendingAttempt:
    group: str
    item: str
    submitted_at: int
    rounds: int
    points: Optional[float]
    endpoint: str = CLAIM_ENDPOINT_ITEM_REWARD
    upstream_failure: Optional[int] = None

    @classmethod
    def from_dict(cls, value: Any) -> "PendingAttempt":
        if not isinstance(value, dict):
            raise _invalid_ledger()
        group = value.get("group")
        item = value.get("item")
        submitted_at = value.get("submitted_at")
        rounds = value.get("rounds")
        points = value.get("points")
        endpoint = value.get("endpoint")
        if endpoint in (None, "", LEGACY_CLAIM_PATH, CLAIM_ENDPOINT_ITEM_REWARD):
            endpoint = CLAIM_ENDPOINT_ITEM_REWARD
        elif endpoint in (CLAIM_PATH, CLAIM_ENDPOINT_LANDING_CHECKIN):
            endpoint = CLAIM_ENDPOINT_LANDING_CHECKIN
        else:
            raise _invalid_ledger()
        upstream_failure = value.get("upstream_failure")
        if not isinstance(group, str) or not group.strip():
            raise _invalid_ledger()
        if not isinstance(item, str) or not item.strip():
            raise _invalid_ledger()
        if not isinstance(submitted_at, int) or isinstance(submitted_at, bool) or submitted_at <= 0:
            raise _invalid_ledger()
        if not isinstance(rounds, int) or isinstance(rounds, bool) or rounds < 1:
            raise _invalid_ledger()
        if points is not None:
            parsed_points = number(points)
            if parsed_points is None or parsed_points < 0:
                raise _invalid_ledger()
            points = parsed_points
        if upstream_failure is not None:
            parsed_failure = exact_integer(upstream_failure)
            if parsed_failure is None or parsed_failure <= 0:
                raise _invalid_ledger()
            upstream_failure = parsed_failure
        return cls(
            group.strip(),
            item.strip(),
            submitted_at,
            rounds,
            points,
            endpoint,
            upstream_failure,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group": self.group,
            "item": self.item,
            "submitted_at": self.submitted_at,
            "rounds": self.rounds,
            "points": self.points,
            "endpoint": self.endpoint,
            "upstream_failure": self.upstream_failure,
        }

    def retry_at(self, at_ms: int) -> Optional[int]:
        next_at = at_ms + RETRY_GAP_MS
        in_window = next_at <= self.submitted_at + CONFIRM_WINDOW_MS
        same_day = beijing_date_key(next_at) == beijing_date_key(at_ms)
        return next_at if self.rounds < MAX_ROUNDS and in_window and same_day else None


@dataclass
class LedgerEntry:
    day: str
    pending: Optional[PendingAttempt]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "day": self.day,
            "pending": self.pending.to_dict() if self.pending else None,
        }


def _invalid_ledger() -> DoubaoError:
    return DoubaoError(
        "豆包工作签到记录无效，已停止提交领取以避免重复操作",
        500,
    )


_LEDGER_THREAD_LOCK = threading.Lock()


def ledger_lock_path(state_path: str) -> str:
    custom = os.getenv("DOUBAOWORK_LOCK_FILE", "").strip()
    return os.path.abspath(custom or state_path + ".lock")


@contextmanager
def _ledger_lock(lock_path: str):
    """Serialize ledger access across threads and processes with one fixed file."""
    directory = os.path.dirname(os.path.abspath(lock_path))
    os.makedirs(directory, exist_ok=True)
    with _LEDGER_THREAD_LOCK:
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if os.name == "nt":
                import msvcrt

                while True:
                    try:
                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                        break
                    except OSError as error:
                        if error.errno not in (
                            errno.EACCES,
                            errno.EAGAIN,
                            errno.EDEADLK,
                        ):
                            raise
                        time.sleep(0.05)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _atomic_write_json(path: str, value: Dict[str, Any]) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    descriptor, temp_path = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".",
        suffix=".tmp",
        dir=directory,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


class CheckinLedgerStore:
    def __init__(
        self,
        path: str,
        account_key: str,
        now_ms_fn: Callable[[], int] = now_ms,
    ):
        if not account_key:
            raise DoubaoError("豆包工作签到台账缺少账号标识", 500)
        self.path = os.path.abspath(path)
        self.account_key = account_key
        self.now_ms_fn = now_ms_fn
        self.document = self._load_document()

    def _load_document(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {"version": STATE_VERSION, "accounts": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                value = json.load(handle)
        except json.JSONDecodeError as error:
            raise _invalid_ledger() from error
        if not isinstance(value, dict):
            raise _invalid_ledger()
        accounts = value.get("accounts")
        if value.get("version") != STATE_VERSION or not isinstance(accounts, dict):
            raise _invalid_ledger()
        return value

    def load(self) -> LedgerEntry:
        today = beijing_date_key(self.now_ms_fn())
        stored = self.document["accounts"].get(self.account_key)
        if stored is None:
            return LedgerEntry(today, None)
        if not isinstance(stored, dict):
            raise _invalid_ledger()
        day = stored.get("day")
        if not isinstance(day, str) or not _valid_date_key(day):
            raise _invalid_ledger()
        if day > today:
            raise DoubaoError("系统日期早于豆包工作签到记录，请先校准时间", 500)
        if day < today:
            return LedgerEntry(today, None)
        pending_value = stored.get("pending")
        pending = None
        if pending_value is not None:
            pending = PendingAttempt.from_dict(pending_value)
            if beijing_date_key(pending.submitted_at) != day:
                raise _invalid_ledger()
        return LedgerEntry(day, pending)

    def save(self, entry: LedgerEntry) -> None:
        self.document["accounts"][self.account_key] = entry.to_dict()
        _atomic_write_json(self.path, self.document)


def ledger_pending_state(
    account_key: str,
    state_path: Optional[str] = None,
    now_ms_fn: Callable[[], int] = now_ms,
) -> str:
    try:
        entry = CheckinLedgerStore(state_path or STATE_FILE, account_key, now_ms_fn).load()
    except (DoubaoError, OSError, TypeError, ValueError):
        return "unreadable"
    if entry.pending is None:
        return "none"
    if entry.pending.upstream_failure == OFFICIAL_SYSTEM_ERROR_CODE:
        return "pending_sdk_required"
    if entry.pending.endpoint == CLAIM_ENDPOINT_LANDING_CHECKIN:
        return "pending_landing_checkin"
    return "pending_item_reward"


def _account_from_cookie(name: str, cookie: str) -> Account:
    pairs = parse_cookie(cookie)
    return Account(
        name=name or "豆包工作",
        cookie=cookie_header(pairs),
        cookie_pairs=pairs,
        user_agent=os.getenv("DOUBAOWORK_USER_AGENT", "").strip() or DEFAULT_USER_AGENT,
        client_version=os.getenv("DOUBAOWORK_CLIENT_VERSION", "").strip() or DEFAULT_CLIENT_VERSION,
        device_id=os.getenv("DOUBAOWORK_DEVICE_ID", "").strip() or pairs.get("device_id", ""),
        web_id=os.getenv("DOUBAOWORK_WEB_ID", "").strip() or pairs.get("web_id", ""),
        fingerprint=(
            os.getenv("DOUBAOWORK_FINGERPRINT", "").strip()
            or pairs.get("s_v_web_id", "")
            or pairs.get("fp", "")
        ),
        proxy=os.getenv("DOUBAOWORK_PROXY", "").strip(),
    )


def load_accounts() -> List[Account]:
    accounts: List[Account] = []
    file_path = os.getenv("DOUBAOWORK_ACCOUNTS_FILE", "").strip()
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            rows = data if isinstance(data, list) else data.get("accounts", [])
            for index, row in enumerate(rows, 1):
                if not isinstance(row, dict):
                    continue
                cookie = first_text(row, ("cookie", "cookieHeader", "cookie_header"))
                if not cookie:
                    continue
                account = _account_from_cookie(
                    first_text(row, ("name", "备注")) or "账号%d" % index, cookie
                )
                for key in (
                    "userAgent",
                    "user_agent",
                    "clientVersion",
                    "client_version",
                    "deviceId",
                    "device_id",
                    "webId",
                    "web_id",
                    "fingerprint",
                    "proxy",
                ):
                    value = first_text(row, (key,))
                    if value:
                        setattr(
                            account,
                            {
                                "userAgent": "user_agent",
                                "user_agent": "user_agent",
                                "clientVersion": "client_version",
                                "client_version": "client_version",
                                "deviceId": "device_id",
                                "device_id": "device_id",
                                "webId": "web_id",
                                "web_id": "web_id",
                                "fingerprint": "fingerprint",
                                "proxy": "proxy",
                            }[key],
                            value,
                        )
                accounts.append(account)
        except Exception as error:
            log(
                "⚠️ 读取 DOUBAOWORK_ACCOUNTS_FILE 失败: %s" % redact_sensitive_text(str(error))[:100]
            )

    multi = os.getenv("DOUBAOWORK_COOKIES", "").strip()
    if multi:
        for index, line in enumerate(multi.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                name, cookie = line.split("|", 1)
            else:
                name, cookie = "账号%d" % index, line
            try:
                accounts.append(_account_from_cookie(name.strip(), cookie.strip()))
            except DoubaoError as error:
                safe_name = redact_sensitive_text(name.strip() or "账号%d" % index)
                log("⚠️ %s Cookie 无效: %s" % (safe_name, redact_sensitive_text(error)))

    single = os.getenv("DOUBAOWORK_COOKIE", "").strip()
    if single:
        try:
            accounts.append(_account_from_cookie("单账号", single))
        except DoubaoError as error:
            log("⚠️ DOUBAOWORK_COOKIE 无效: %s" % redact_sensitive_text(error))
    return accounts


class DoubaoClient:
    def __init__(
        self, account: Account, session: Optional[requests.Session] = None, base_url: str = BASE_URL
    ):
        self.account = account
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.last_diagnostic: Dict[str, Any] = {}
        self.session.trust_env = False
        if account.proxy:
            self.session.proxies.update({"http": account.proxy, "https": account.proxy})

    def query_params(self) -> List[Tuple[str, str]]:
        params = [
            ("aid", "1044603"),
            ("real_aid", "1044603"),
            ("device_platform", "web"),
            ("version_code", "20800"),
            ("samantha_web", "1"),
            ("web_platform", "desktop"),
            ("doubao_device_platform", "desktop"),
            ("client_platform", "pc_client"),
            ("pkg_type", "release_version"),
            ("runtime", "web"),
            ("runtime_version", RUNTIME_VERSION),
            ("pc_version", self.account.client_version),
            ("doubao_pc_version", self.account.client_version),
            ("use-olympus-account", "1"),
            ("language", "zh"),
            ("region", "CN"),
            ("sys_region", "CN"),
        ]
        if self.account.device_id:
            params.append(("device_id", self.account.device_id))
        if self.account.web_id:
            params.append(("web_id", self.account.web_id))
        if self.account.device_id:
            params.append(("fp", "verify_" + self.account.device_id))
        elif self.account.fingerprint:
            params.append(("fp", self.account.fingerprint))
        return params

    def _headers(self) -> Dict[str, str]:
        return {
            "Cookie": self.account.cookie,
            "Origin": self.base_url,
            "Referer": self.base_url + "/chat/",
            "User-Agent": self.account.user_agent,
            "Agw-Js-Conv": "str",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        }

    def _attach_diagnostic(self, error: DoubaoError) -> DoubaoError:
        error.diagnostic = dict(self.last_diagnostic)
        return error

    def set_checked_in_today(self, checked: Optional[bool]) -> None:
        self.last_diagnostic["checked_in_today"] = checked

    def post(self, path: str, body: Any, timeout: float = 30.0) -> Dict[str, Any]:
        self.last_diagnostic = {
            "request_path": path,
            "http_status": None,
            "business_code": None,
            "message": "",
            "checked_in_today": None,
        }
        try:
            response = self.session.post(
                self.base_url + path,
                params=self.query_params(),
                headers=self._headers(),
                json=body,
                timeout=timeout,
                verify=False,
            )
        except Exception as error:
            self.last_diagnostic["message"] = str(error)
            raise

        self.last_diagnostic["http_status"] = response.status_code
        try:
            payload = response.json()
        except Exception:
            message = "豆包工作未返回有效 JSON（HTTP %s）" % response.status_code
            self.last_diagnostic["message"] = message
            raise self._attach_diagnostic(DoubaoError(message, response.status_code))
        if not isinstance(payload, dict):
            message = "豆包工作返回的 JSON 不是对象"
            self.last_diagnostic["message"] = message
            raise self._attach_diagnostic(DoubaoError(message, response.status_code))
        code = integer(payload.get("code"))
        detail = payload.get("error_detail") or payload.get("error") or payload
        message = first_text(
            detail,
            ("message", "msg", "error_msg", "error_message", "detail"),
        )
        message = message or first_text(payload, ("msg", "message")) or ""
        self.last_diagnostic["business_code"] = code
        self.last_diagnostic["message"] = message
        ok_code = code == 0 or (code == 200 and path.startswith("/alice/ug/"))
        if not 200 <= response.status_code < 300 or not ok_code:
            message = message or "豆包工作接口失败"
            self.last_diagnostic["message"] = message
            if (
                response.status_code == 401
                or code == 710012001
                or "not logged in" in message.lower()
            ):
                raise self._attach_diagnostic(
                    DoubaoAuthError("豆包工作登录态已失效，请重新登录", response.status_code, code)
                )
            if response.status_code == 429 or code == 710022004:
                raise self._attach_diagnostic(
                    DoubaoRateLimitError("豆包工作触发限流，请稍后重试", response.status_code, code)
                )
            raise self._attach_diagnostic(
                DoubaoError("豆包工作：%s" % message, response.status_code, code)
            )
        return payload


def _walk_tasks(value: Any, group: str, output: List[Dict[str, Any]], depth: int = 0) -> None:
    if depth > 8 or not isinstance(value, dict):
        return
    current_group = first_text(value, ("campaign_group_code", "campaign_code")) or group
    for key in ("tasks", "campaigns", "milestones"):
        rows = value.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = first_text(row, ("campaign_code", "task_code", "code"))
            if not item:
                continue
            row_group = first_text(row, ("campaign_group_code",)) or current_group
            daily_info = row.get("daily_checkin")
            daily = isinstance(daily_info, dict) and isinstance(
                daily_info.get("checked_in_today"), bool
            )
            checked = bool(
                isinstance(daily_info, dict) and daily_info.get("checked_in_today") is True
            )
            state = integer(row.get("task_status")) or 0
            direct = integer(row.get("reward_mode")) == 2 or key == "milestones"
            body = None
            if state == 2 or (daily and direct and state in (1, 4)):
                if direct:
                    body = {
                        "task_id": "",
                        "campaign_group_code": row_group,
                        "campaign_item_code": item,
                    }
                else:
                    task_id = first_text(row, ("task_id",))
                    if task_id:
                        body = {"task_id": task_id}
            points = None
            if isinstance(daily_info, dict):
                reward = daily_info.get("reward")
                if isinstance(reward, dict):
                    points = number(reward.get("reward_amount"))
            if points is None:
                summaries = row.get("reward_summaries")
                if isinstance(summaries, list) and summaries and isinstance(summaries[0], dict):
                    points = number(summaries[0].get("reward_amount"))
            task = {
                "key": item,
                "title": first_text(row, ("title", "name")) or item,
                "group": row_group,
                "state": state,
                "daily": daily,
                "checked": checked,
                "body": body,
                "points": points,
                "streak": integer(daily_info.get("continuous_days"))
                if isinstance(daily_info, dict)
                else None,
            }
            if not any(
                old["key"] == task["key"] and old["group"] == task["group"] for old in output
            ):
                output.append(task)
    child = value.get("campaign_group")
    if isinstance(child, dict):
        _walk_tasks(child, current_group, output, depth + 1)
    children = value.get("campaign_groups")
    if isinstance(children, list):
        for child in children:
            _walk_tasks(child, current_group, output, depth + 1)


def collect_tasks(payload: Dict[str, Any], group: str) -> List[Dict[str, Any]]:
    root = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    output: List[Dict[str, Any]] = []
    _walk_tasks(root, group, output)
    return output


def _activity_group(payload: Dict[str, Any]) -> str:
    data = payload.get("data")
    if not isinstance(data, dict):
        return ""
    info = data.get("ug_campaign_info")
    if not isinstance(info, dict):
        return ""
    return first_text(info, ("campaign_group_code",))


def _detail_path(group: str) -> str:
    return "/alice/ug/campaign/v3/detail/" if group == V3_GROUP else "/alice/ug/campaign/list/"


def _campaign_detail(client: DoubaoClient, group: str, timeout: float = 30.0) -> Dict[str, Any]:
    value = client.post(
        _detail_path(group),
        {"campaign_group_code": group},
        timeout=timeout,
    )
    data = value.get("data")
    if isinstance(data, dict):
        campaign_code = first_text(data, ("campaign_code",))
        if group == V3_GROUP and campaign_code and campaign_code != group:
            raise DoubaoError("豆包工作返回了不匹配的活动组", 502)
    daily_tasks = [row for row in collect_tasks(value, group) if row["daily"]]
    client.set_checked_in_today(daily_tasks[0]["checked"] if len(daily_tasks) == 1 else None)
    return value


def _validate_receipt(payload: Dict[str, Any]) -> bool:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DoubaoError("豆包工作未返回奖励领取回执")
    biz = data.get("biz_error")
    if biz is not None:
        if not isinstance(biz, dict):
            raise DoubaoError("豆包工作奖励领取回执的 biz_error 格式无效")
        code = exact_integer(biz.get("code"))
        if code != 0:
            raise DoubaoError(
                first_text(biz, ("message", "msg")) or "豆包工作签到回执返回业务错误",
                code=code,
            )
    checked = data.get("checked_in")
    if checked is True:
        return True
    if checked is False:
        raise DoubaoError("豆包工作未完成签到，稍后查询官方状态", 502)
    raise DoubaoError("豆包工作签到回执缺少 checked_in，稍后查询官方状态", 502)


def _daily_task(payload: Dict[str, Any], group: str) -> Tuple[Optional[Dict[str, Any]], str]:
    rows = [row for row in collect_tasks(payload, group) if row["daily"]]
    if not rows:
        return None, "当前没有豆包工作每日签到任务"
    if len(rows) != 1:
        return None, "当前活动未提供可确认的唯一每日签到任务"
    return rows[0], ""


def _pending_task(payload: Dict[str, Any], attempt: PendingAttempt) -> Dict[str, Any]:
    for row in collect_tasks(payload, attempt.group):
        if row["daily"] and row["key"] == attempt.item and row["group"] == attempt.group:
            return row
    raise DoubaoError(
        "豆包工作回查未返回原签到任务，尚未确认到账；再次执行只查询结果",
        502,
    )


def _is_explicit_reject_error(error: DoubaoError) -> bool:
    business_code = exact_integer(error.code)
    return (
        error.code == "reward_rejected"
        or isinstance(error, (DoubaoAuthError, DoubaoRateLimitError))
        or error.status in DIRECT_REJECT_STATUSES
        or business_code in EXPLICIT_REJECT_BUSINESS_CODES
    )


def _is_confirming_error(error: DoubaoError) -> bool:
    if _is_explicit_reject_error(error):
        return False
    message = str(error).strip()
    prefix = "豆包工作："
    if message.startswith(prefix):
        message = message[len(prefix) :]
    return any(marker in message for marker in CONFIRMING_MARKERS)


def _is_rejected_error(error: DoubaoError) -> bool:
    if _is_explicit_reject_error(error):
        return True
    return error.status in CONDITIONAL_REJECT_STATUSES and not _is_confirming_error(error)


def _ensure_ledger_day(entry: LedgerEntry, now_ms_fn: Callable[[], int]) -> None:
    if beijing_date_key(now_ms_fn()) != entry.day:
        raise DoubaoError(
            "签到确认已跨过北京时间零点，未将昨日结果计为今日签到，请重新查询今日活动",
            409,
        )


def _clear_pending(store: CheckinLedgerStore, entry: LedgerEntry) -> None:
    previous = entry.pending
    entry.pending = None
    try:
        store.save(entry)
    except (DoubaoError, OSError) as error:
        entry.pending = previous
        log("⚠️ 清除豆包工作待确认签到记录失败: %s" % error)


def _completed_result(
    task: Dict[str, Any],
    submitted_now: bool,
    points: Optional[float],
) -> Dict[str, Any]:
    if submitted_now:
        return {
            "status": "claimed",
            "message": "豆包工作签到奖励已领取，已回查确认",
            "points": task["points"] if points is None else points,
            "streak": task["streak"],
            "completed": True,
            "query_only": False,
            "retry_at": None,
            "checked_in_today": True,
        }
    return {
        "status": "done",
        "message": "今日已领取豆包工作签到奖励，已由官方确认",
        "points": None,
        "streak": task["streak"],
        "completed": True,
        "query_only": False,
        "retry_at": None,
        "checked_in_today": True,
    }


def _reconcile_pending(
    client: DoubaoClient,
    store: CheckinLedgerStore,
    entry: LedgerEntry,
    submitted_now: bool,
    now_ms_fn: Callable[[], int],
    monotonic_fn: Callable[[], float],
    sleep_fn: Callable[[float], None],
    upstream_diagnostic: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    attempt = entry.pending
    if attempt is None:
        raise DoubaoError("豆包工作缺少待确认任务，未提交领取", 500)
    if attempt.upstream_failure == OFFICIAL_SYSTEM_ERROR_CODE:
        _ensure_ledger_day(entry, now_ms_fn)
        payload = _campaign_detail(client, attempt.group)
        task = _pending_task(payload, attempt)
        if task["checked"] is True:
            result = _completed_result(task, False, attempt.points)
            _clear_pending(store, entry)
            return result
        failure = DoubaoError(
            "710010702：当前 landing/checkin 需要官方活动页 SDK 生成的 "
            "biz_params/AgwCommonParam，纯 HTTP 无法可靠完成。"
            "请在官方客户端点击“立即签到”，然后再次运行脚本；"
            "pending 已保留，后续只会回读状态，不会重复提交。",
            502,
            OFFICIAL_SYSTEM_ERROR_CODE,
        )
        failure.diagnostic = dict(upstream_diagnostic or {})
        if not failure.diagnostic:
            current = getattr(client, "last_diagnostic", {})
            failure.diagnostic = dict(current) if isinstance(current, dict) else {}
        failure.diagnostic["checked_in_today"] = False
        raise failure
    deadline = monotonic_fn() + CONFIRM_BUDGET_SECONDS
    queried = False
    for delay in CONFIRM_POLL_DELAYS:
        if delay > 0:
            sleep_fn(delay)
        remaining = deadline - monotonic_fn()
        if remaining <= 0:
            raise DoubaoError(
                "豆包工作签到结果查询超时；领取记录已保留，再次执行只查询结果",
                504,
            )
        _ensure_ledger_day(entry, now_ms_fn)
        payload = _campaign_detail(client, attempt.group, timeout=max(0.1, remaining))
        if monotonic_fn() > deadline:
            raise DoubaoError(
                "豆包工作签到结果查询超时；领取记录已保留，再次执行只查询结果",
                504,
            )
        _ensure_ledger_day(entry, now_ms_fn)
        task = _pending_task(payload, attempt)
        queried = True
        if task["checked"] is True:
            result = _completed_result(task, submitted_now, attempt.points)
            _clear_pending(store, entry)
            return result
        if attempt.retry_at(now_ms_fn()) is None:
            break
    retry_at = attempt.retry_at(now_ms_fn())
    message = (
        "豆包工作领取结果待确认，稍后只查询结果，不会重复提交领取"
        if retry_at is not None
        else "豆包工作今日领取仍未确认，请前往官方客户端查看；再次执行仅查询结果，不会重复领取"
    )
    return {
        "status": "confirming",
        "message": message,
        "points": None,
        "streak": None,
        "completed": False,
        "query_only": True,
        "retry_at": retry_at if queried else None,
        "checked_in_today": False if queried else None,
    }


def claim_daily(
    client: DoubaoClient,
    state_path: Optional[str] = None,
    lock_path: Optional[str] = None,
    account_key: Optional[str] = None,
    now_ms_fn: Callable[[], int] = now_ms,
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    key = account_key or account_ledger_key(client.account)
    ledger_path = state_path or STATE_FILE
    with _ledger_lock(lock_path or ledger_lock_path(ledger_path)):
        store = CheckinLedgerStore(ledger_path, key, now_ms_fn)
        entry = store.load()
        return _claim_daily_locked(
            client,
            store,
            entry,
            now_ms_fn,
            monotonic_fn,
            sleep_fn,
        )


def _claim_daily_locked(
    client: DoubaoClient,
    store: CheckinLedgerStore,
    entry: LedgerEntry,
    now_ms_fn: Callable[[], int],
    monotonic_fn: Callable[[], float],
    sleep_fn: Callable[[float], None],
) -> Dict[str, Any]:
    if entry.pending is not None:
        entry.pending.rounds = min(MAX_ROUNDS, entry.pending.rounds + 1)
        if entry.pending.endpoint == CLAIM_ENDPOINT_ITEM_REWARD:
            _ensure_ledger_day(entry, now_ms_fn)
            payload = _campaign_detail(client, entry.pending.group)
            task = _pending_task(payload, entry.pending)
            if task["checked"] is True:
                result = _completed_result(task, False, entry.pending.points)
                _clear_pending(store, entry)
                return result
            # 旧版只提交过任务领奖，不能证明每日签到已生效；官方详情仍未勾选时
            # 清除旧 pending，再走 landing/checkin。
            _clear_pending(store, entry)
        else:
            store.save(entry)
            return _reconcile_pending(
                client,
                store,
                entry,
                False,
                now_ms_fn,
                monotonic_fn,
                sleep_fn,
            )

    launch = client.post("/alice/user/launch", {})
    group = _activity_group(launch)
    if not group:
        return {
            "status": "inactive",
            "message": "当前没有豆包工作签到活动",
            "points": None,
            "streak": None,
            "completed": False,
            "query_only": False,
            "retry_at": None,
            "checked_in_today": None,
        }
    detail = _campaign_detail(client, group)
    daily_tasks = [row for row in collect_tasks(detail, group) if row["daily"]]
    if len(daily_tasks) > 1:
        raise DoubaoError(
            "豆包工作返回了多个每日签到任务，无法确定领取对象，未提交领取",
            502,
        )
    if not daily_tasks:
        return {
            "status": "inactive",
            "message": "当前活动未提供每日签到任务",
            "points": None,
            "streak": None,
            "completed": False,
            "query_only": False,
            "retry_at": None,
            "checked_in_today": None,
        }
    task = daily_tasks[0]
    _ensure_ledger_day(entry, now_ms_fn)
    if task["checked"] is True:
        return {
            "status": "already",
            "message": "今日已领取豆包工作签到奖励",
            "points": task["points"],
            "streak": task["streak"],
            "completed": True,
            "query_only": False,
            "retry_at": None,
            "checked_in_today": True,
        }
    entry.pending = PendingAttempt(
        group=task["group"],
        item=task["key"],
        submitted_at=now_ms_fn(),
        rounds=1,
        points=task["points"],
        endpoint=CLAIM_ENDPOINT_LANDING_CHECKIN,
    )
    store.save(entry)
    _ensure_ledger_day(entry, now_ms_fn)

    try:
        response = client.post(CLAIM_PATH, {"scene": task["group"]})
    except DoubaoError as error:
        if exact_integer(error.code) == OFFICIAL_SYSTEM_ERROR_CODE:
            if entry.pending is not None:
                entry.pending.upstream_failure = OFFICIAL_SYSTEM_ERROR_CODE
                store.save(entry)
            return _reconcile_pending(
                client,
                store,
                entry,
                False,
                now_ms_fn,
                monotonic_fn,
                sleep_fn,
                dict(error.diagnostic),
            )
        if not _is_confirming_error(error):
            if _is_rejected_error(error):
                _clear_pending(store, entry)
            raise
        response = None
    try:
        if response is not None:
            _validate_receipt(response)
    except DoubaoError as error:
        if exact_integer(error.code) == OFFICIAL_SYSTEM_ERROR_CODE:
            if entry.pending is not None:
                entry.pending.upstream_failure = OFFICIAL_SYSTEM_ERROR_CODE
                store.save(entry)
            return _reconcile_pending(
                client,
                store,
                entry,
                False,
                now_ms_fn,
                monotonic_fn,
                sleep_fn,
                dict(client.last_diagnostic),
            )
        if _is_rejected_error(error):
            _clear_pending(store, entry)
        raise
    if response is not None:
        reward = response.get("data")
        received_points = number(reward.get("reward_amount")) if isinstance(reward, dict) else None
        if received_points is not None and entry.pending is not None:
            entry.pending.points = received_points
            store.save(entry)
    return _reconcile_pending(
        client,
        store,
        entry,
        True,
        now_ms_fn,
        monotonic_fn,
        sleep_fn,
    )


def query_daily(client: DoubaoClient) -> Dict[str, Any]:
    launch = client.post("/alice/user/launch", {})
    group = _activity_group(launch)
    if not group:
        return {
            "status": "inactive",
            "message": "当前没有豆包工作签到活动",
            "checked_in_today": None,
        }
    detail = _campaign_detail(client, group)
    task, error = _daily_task(detail, group)
    if error:
        return {
            "status": "inactive",
            "message": error,
            "checked_in_today": None,
        }
    checked = task["checked"] is True
    return {
        "status": "done" if checked else "available",
        "message": "今日已领取" if checked else "今日尚未确认领取",
        "points": task["points"],
        "streak": task["streak"],
        "title": task["title"],
        "completed": checked,
        "query_only": True,
        "retry_at": None,
        "checked_in_today": checked,
    }


def notify(title: str, content: str) -> None:
    if os.getenv("DOUBAOWORK_NO_NOTIFY", "").strip() == "1":
        return
    token = os.getenv("PUSHPLUS_TOKEN", "").strip()
    if token:
        try:
            response = (
                requests.Session()
                .post(
                    "https://www.pushplus.plus/send",
                    json={"token": token, "title": title, "content": content, "template": "txt"},
                    timeout=15,
                )
                .json()
            )
            log(
                "📢 PushPlus: %s"
                % (
                    "成功"
                    if response.get("code") == 200
                    else redact_sensitive_text(response.get("msg", ""))[:60]
                )
            )
        except Exception as error:
            log("📢 PushPlus 异常: %s" % redact_sensitive_text(error)[:60])
    bark = os.getenv("BARK_URL", "").strip().rstrip("/")
    if bark:
        try:
            requests.Session().post(bark, json={"title": title, "body": content}, timeout=15)
            log("📢 Bark: 已发送")
        except Exception as error:
            log("📢 Bark 异常: %s" % redact_sensitive_text(error)[:60])
    wecom = os.getenv("WECOM_WEBHOOK", "").strip()
    if wecom:
        try:
            if not wecom.startswith("http"):
                wecom = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=" + wecom
            requests.Session().post(
                wecom,
                json={"msgtype": "text", "text": {"content": title + "\n" + content}},
                timeout=15,
            )
            log("📢 企业微信: 已发送")
        except Exception as error:
            log("📢 企业微信异常: %s" % redact_sensitive_text(error)[:60])


def main() -> int:
    parser = argparse.ArgumentParser(description="豆包工作每日奖励")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    parser.add_argument("--query", action="store_true", help="只查询，不领取")
    parser.add_argument("--only", type=int, default=0, help="只跑第 N 个账号")
    parser.add_argument("--no-notify", action="store_true", help="关闭通知")
    args = parser.parse_args()
    if args.no_notify:
        os.environ["DOUBAOWORK_NO_NOTIFY"] = "1"

    accounts = load_accounts()
    if not accounts:
        log("❌ 未找到账号：请设置 DOUBAOWORK_COOKIES 或 DOUBAOWORK_COOKIE")
        log("   格式：备注|sessionid=...; sessionid_ss=...")
        return 1
    if args.only:
        accounts = accounts[max(0, args.only - 1) : args.only]
    if not accounts:
        log("❌ --only 超出账号范围")
        return 1

    lines = ["🫘 豆包工作每日奖励", ""]
    failed = 0
    action = "query" if args.query else "claim"
    for index, account in enumerate(accounts, 1):
        client: Optional[DoubaoClient] = None
        result: Optional[Dict[str, Any]] = None
        failure: Optional[BaseException] = None
        secrets = account_secret_values(account)
        safe_name = redact_sensitive_text(account.name, secrets)
        log("")
        log("╭─ 👤 账号%d  %s" % (index, safe_name))
        try:
            client = DoubaoClient(account)
            result = query_daily(client) if args.query else claim_daily(client)
            status = result.get("status", "")
            message = redact_sensitive_text(result.get("message", ""), secrets)
            log("   %s: %s" % (status, message))
            if result.get("points") is not None:
                log("   🎁 奖励额度: %s" % result["points"])
            if result.get("streak") is not None:
                log("   🔥 连签: %s 天" % result["streak"])
            lines.append(
                "%s: %s%s"
                % (
                    safe_name,
                    message,
                    "（%s 额度）" % result["points"] if result.get("points") is not None else "",
                )
            )
            if status in ("error", "auth"):
                failed += 1
        except DoubaoAuthError as error:
            failure = error
            failed += 1
            safe_error = redact_sensitive_text(error, secrets)
            log("   ⛔ 登录态失效: %s" % safe_error)
            lines.append("%s: ⛔ %s" % (safe_name, safe_error))
        except DoubaoRateLimitError as error:
            failure = error
            failed += 1
            safe_error = redact_sensitive_text(error, secrets)
            log("   ⏳ 限流: %s" % safe_error)
            lines.append("%s: ⏳ %s" % (safe_name, safe_error))
        except Exception as error:
            failure = error
            failed += 1
            safe_error = redact_sensitive_text(error, secrets)
            log("   ❌ %s" % safe_error[:160])
            lines.append("%s: ❌ %s" % (safe_name, safe_error[:100]))
        try:
            pending = ledger_pending_state(account_ledger_key(account), STATE_FILE)
        except DoubaoError:
            pending = "unreadable"
        log_diagnostic(account, action, client, pending, result, failure)
        time.sleep(1)

    lines.extend(["", "🕐 %s" % time.strftime("%Y-%m-%d %H:%M")])
    content = "\n".join(lines)
    log("")
    log(content)
    notify("🫘 豆包工作每日奖励", content)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
