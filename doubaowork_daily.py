#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
豆包工作每日奖励 - 青龙 / GitHub Actions 单文件脚本

协议依据：Agent2API Agent2Providers v3.3.0-beta.6 的 doubaowork provider。
本脚本是独立的 clean-room 实现，不依赖 3.3 插件进程，也不复制其源码。

流程：
  Cookie -> POST /alice/user/launch
         -> POST /alice/ug/campaign/v3/detail/（或 /campaign/list/）
         -> 找唯一 daily_checkin 任务
         -> POST /alice/ug/campaign/item/reward/claim/
         -> 重新拉 detail，确认 checked_in_today=true / task_status=3

环境变量：
  DOUBAOWORK_COOKIES    多账号，每行一个：备注|sessionid=...; sessionid_ss=...
  DOUBAOWORK_COOKIE     单账号 Cookie
  DOUBAOWORK_ACCOUNTS_FILE  可选 JSON 账号文件
  DOUBAOWORK_DEVICE_ID / WEB_ID / FINGERPRINT  可选，Cookie 里没有时补充
  DOUBAOWORK_USER_AGENT / CLIENT_VERSION        可选
  DOUBAOWORK_PROXY      可选代理
  DOUBAOWORK_NO_NOTIFY=1  关闭通知

命令：
  python doubaowork_daily.py
  python doubaowork_daily.py --query
  python doubaowork_daily.py --only 1
  python doubaowork_daily.py --no-notify

依赖：requests
"""

import argparse
import json
import os
import re
import sys
import time
import urllib3
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

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
CLAIM_PATH = "/alice/ug/campaign/item/reward/claim/"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.getenv("DOUBAOWORK_STATE_FILE", "").strip() or os.path.join(
    SCRIPT_DIR, "doubaowork_state.json"
)


class DoubaoError(RuntimeError):
    def __init__(self, message: str, status: int = 0, code: Optional[int] = None):
        super().__init__(message)
        self.status = int(status or 0)
        self.code = code


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
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except (TypeError, ValueError):
            return None
    return None


def integer(value: Any) -> Optional[int]:
    parsed = number(value)
    if parsed is None:
        return None
    return int(parsed)


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
            if domain and domain not in ("doubao.com", ".doubao.com", "www.doubao.com", ".www.doubao.com"):
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
        raise DoubaoAuthError("Cookie 缺少 sessionid / sessionid_ss，请重新登录豆包工作后复制完整 Cookie")
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
            data = json.load(open(file_path, "r", encoding="utf-8"))
            rows = data if isinstance(data, list) else data.get("accounts", [])
            for index, row in enumerate(rows, 1):
                if not isinstance(row, dict):
                    continue
                cookie = first_text(row, ("cookie", "cookieHeader", "cookie_header"))
                if not cookie:
                    continue
                account = _account_from_cookie(first_text(row, ("name", "备注")) or "账号%d" % index, cookie)
                for key in ("userAgent", "user_agent", "clientVersion", "client_version",
                            "deviceId", "device_id", "webId", "web_id",
                            "fingerprint", "proxy"):
                    value = first_text(row, (key,))
                    if value:
                        setattr(account, {
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
                        }[key], value)
                accounts.append(account)
        except Exception as error:
            log("⚠️ 读取 DOUBAOWORK_ACCOUNTS_FILE 失败: %s" % str(error)[:100])

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
                log("⚠️ %s Cookie 无效: %s" % (name.strip() or "账号%d" % index, error))

    single = os.getenv("DOUBAOWORK_COOKIE", "").strip()
    if single:
        try:
            accounts.append(_account_from_cookie("单账号", single))
        except DoubaoError as error:
            log("⚠️ DOUBAOWORK_COOKIE 无效: %s" % error)
    return accounts


class DoubaoClient:
    def __init__(self, account: Account, session: Optional[requests.Session] = None,
                 base_url: str = BASE_URL):
        self.account = account
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
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

    def post(self, path: str, body: Any) -> Dict[str, Any]:
        response = self.session.post(
            self.base_url + path,
            params=self.query_params(),
            headers=self._headers(),
            json=body,
            timeout=30,
            verify=False,
        )
        try:
            payload = response.json()
        except Exception:
            raise DoubaoError(
                "豆包工作未返回有效 JSON（HTTP %s）" % response.status_code,
                response.status_code,
            )
        if not isinstance(payload, dict):
            raise DoubaoError("豆包工作返回的 JSON 不是对象", response.status_code)
        code = integer(payload.get("code"))
        ok_code = code == 0 or (code == 200 and path.startswith("/alice/ug/"))
        if not 200 <= response.status_code < 300 or not ok_code:
            detail = payload.get("error_detail") or payload.get("error") or payload
            message = first_text(detail, ("message", "msg", "error_msg", "error_message", "detail"))
            message = message or first_text(payload, ("msg", "message")) or "豆包工作接口失败"
            if response.status_code == 401 or code == 710012001 or "not logged in" in message.lower():
                raise DoubaoAuthError("豆包工作登录态已失效，请重新登录", response.status_code, code)
            if response.status_code == 429 or code == 710022004:
                raise DoubaoRateLimitError("豆包工作触发限流，请稍后重试", response.status_code, code)
            raise DoubaoError("豆包工作：%s" % message, response.status_code, code)
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
            daily = isinstance(daily_info, dict) and isinstance(daily_info.get("checked_in_today"), bool)
            checked = bool(isinstance(daily_info, dict) and daily_info.get("checked_in_today") is True)
            state = integer(row.get("task_status")) or 0
            direct = integer(row.get("reward_mode")) == 2 or key == "milestones"
            body = None
            if state == 2 or (daily and direct and state in (1, 4)):
                if direct:
                    body = {"task_id": "", "campaign_group_code": row_group, "campaign_item_code": item}
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
                "streak": integer(daily_info.get("continuous_days")) if isinstance(daily_info, dict) else None,
            }
            if not any(old["key"] == task["key"] and old["group"] == task["group"] for old in output):
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


def _receipt_confirmed(payload: Dict[str, Any]) -> bool:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DoubaoError("豆包工作未返回奖励领取回执")
    if data.get("success") is False:
        raise DoubaoError("豆包工作奖励领取被拒绝")
    biz = data.get("biz_error")
    if isinstance(biz, dict):
        code = integer(biz.get("code"))
        if code not in (0, 4, 6, None):
            raise DoubaoError(first_text(biz, ("message", "msg")) or "豆包工作奖励领取失败")
    return (
        integer(data.get("task_status")) == 3
        or data.get("checked_in_today") is True
        or (isinstance(data.get("daily_checkin"), dict)
            and data["daily_checkin"].get("checked_in_today") is True)
    )


def _daily_task(payload: Dict[str, Any], group: str) -> Tuple[Optional[Dict[str, Any]], str]:
    rows = [row for row in collect_tasks(payload, group) if row["daily"]]
    if not rows:
        return None, "当前没有豆包工作每日签到任务"
    if len(rows) != 1:
        return None, "当前活动未提供可确认的唯一每日签到任务"
    return rows[0], ""


def claim_daily(client: DoubaoClient) -> Dict[str, Any]:
    launch = client.post("/alice/user/launch", {})
    group = _activity_group(launch)
    if not group:
        return {"status": "inactive", "message": "当前没有豆包工作签到活动", "points": None, "streak": None}
    detail = client.post(_detail_path(group), {"campaign_group_code": group})
    task, error = _daily_task(detail, group)
    if error:
        return {"status": "inactive", "message": error, "points": None, "streak": None}
    if task["checked"] or task["state"] == 3:
        return {"status": "already", "message": "今日已领取豆包工作签到奖励",
                "points": task["points"], "streak": task["streak"]}
    if not task["body"]:
        return {"status": "inactive", "message": "今日签到任务尚未满足领取条件",
                "points": task["points"], "streak": task["streak"]}
    response = client.post(CLAIM_PATH, task["body"])
    confirmed = _receipt_confirmed(response)
    fresh = client.post(_detail_path(group), {"campaign_group_code": group})
    after_task, _ = _daily_task(fresh, group)
    if not after_task or not (after_task["checked"] or after_task["state"] == 3):
        if confirmed:
            raise DoubaoError("豆包工作已接受领取，但回查尚未确认今日签到；稍后重试不会重复发奖")
        raise DoubaoError("豆包工作未确认今日签到奖励，请稍后重试或前往官方活动页")
    points = number((response.get("data") or {}).get("reward_amount"))
    if points is None:
        points = after_task["points"] if after_task else task["points"]
    return {
        "status": "claimed",
        "message": "豆包工作签到奖励已领取，已回查确认",
        "points": points,
        "streak": after_task.get("streak") if after_task else task["streak"],
    }


def query_daily(client: DoubaoClient) -> Dict[str, Any]:
    launch = client.post("/alice/user/launch", {})
    group = _activity_group(launch)
    if not group:
        return {"status": "inactive", "message": "当前没有豆包工作签到活动"}
    detail = client.post(_detail_path(group), {"campaign_group_code": group})
    task, error = _daily_task(detail, group)
    if error:
        return {"status": "inactive", "message": error}
    return {
        "status": "done" if task["checked"] or task["state"] == 3 else "available",
        "message": "今日已领取" if task["checked"] or task["state"] == 3 else "今日可领取",
        "points": task["points"],
        "streak": task["streak"],
        "title": task["title"],
    }


def notify(title: str, content: str) -> None:
    if os.getenv("DOUBAOWORK_NO_NOTIFY", "").strip() == "1":
        return
    token = os.getenv("PUSHPLUS_TOKEN", "").strip()
    if token:
        try:
            response = requests.Session().post(
                "https://www.pushplus.plus/send",
                json={"token": token, "title": title, "content": content, "template": "txt"},
                timeout=15,
            ).json()
            log("📢 PushPlus: %s" % ("成功" if response.get("code") == 200 else str(response.get("msg", ""))[:60]))
        except Exception as error:
            log("📢 PushPlus 异常: %s" % str(error)[:60])
    bark = os.getenv("BARK_URL", "").strip().rstrip("/")
    if bark:
        try:
            requests.Session().post(bark, json={"title": title, "body": content}, timeout=15)
            log("📢 Bark: 已发送")
        except Exception as error:
            log("📢 Bark 异常: %s" % str(error)[:60])
    wecom = os.getenv("WECOM_WEBHOOK", "").strip()
    if wecom:
        try:
            if not wecom.startswith("http"):
                wecom = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=" + wecom
            requests.Session().post(wecom, json={"msgtype": "text", "text": {"content": title + "\n" + content}}, timeout=15)
            log("📢 企业微信: 已发送")
        except Exception as error:
            log("📢 企业微信异常: %s" % str(error)[:60])


def main() -> int:
    parser = argparse.ArgumentParser(description="豆包工作每日奖励")
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
        accounts = accounts[max(0, args.only - 1):args.only]
    if not accounts:
        log("❌ --only 超出账号范围")
        return 1

    lines = ["🫘 豆包工作每日奖励", ""]
    failed = 0
    for index, account in enumerate(accounts, 1):
        log("")
        log("╭─ 👤 账号%d  %s" % (index, account.name))
        try:
            client = DoubaoClient(account)
            result = query_daily(client) if args.query else claim_daily(client)
            status = result.get("status", "")
            message = result.get("message", "")
            log("   %s: %s" % (status, message))
            if result.get("points") is not None:
                log("   🎁 奖励额度: %s" % result["points"])
            if result.get("streak") is not None:
                log("   🔥 连签: %s 天" % result["streak"])
            lines.append("%s: %s%s" % (
                account.name,
                message,
                "（%s 额度）" % result["points"] if result.get("points") is not None else "",
            ))
            if status in ("error", "auth"):
                failed += 1
        except DoubaoAuthError as error:
            failed += 1
            log("   ⛔ 登录态失效: %s" % error)
            lines.append("%s: ⛔ %s" % (account.name, error))
        except DoubaoRateLimitError as error:
            failed += 1
            log("   ⏳ 限流: %s" % error)
            lines.append("%s: ⏳ %s" % (account.name, error))
        except Exception as error:
            failed += 1
            log("   ❌ %s" % str(error)[:160])
            lines.append("%s: ❌ %s" % (account.name, str(error)[:100]))
        time.sleep(1)

    lines.extend(["", "🕐 %s" % time.strftime("%Y-%m-%d %H:%M")])
    content = "\n".join(lines)
    log("")
    log(content)
    notify("🫘 豆包工作每日奖励", content)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
