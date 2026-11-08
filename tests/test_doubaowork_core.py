import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import requests

import doubaowork_daily as wb

NOW_MS = 1_793_851_200_000

LEDGER_PROCESS_WORKER = r"""
import importlib.util
import json
import socket
import sys

source, base_url, state_path, lock_path, user_agent, now_ms, barrier_host, barrier_port = sys.argv[1:]
spec = importlib.util.spec_from_file_location("doubaowork_daily", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
account = module.Account(
    name="lock-test",
    cookie="sessionid=lock-test",
    cookie_pairs={"sessionid": "lock-test"},
    user_agent=user_agent,
)
client = module.DoubaoClient(account, base_url=base_url)
with socket.create_connection((barrier_host, int(barrier_port)), timeout=10) as connection:
    connection.sendall(b"1")
    if connection.recv(1) != b"1":
        raise RuntimeError("barrier release missing")
result = module.claim_daily(
    client,
    state_path=state_path,
    lock_path=lock_path,
    account_key="shared-account",
    now_ms_fn=lambda: int(now_ms),
    sleep_fn=lambda _delay: None,
)
print(json.dumps(result, ensure_ascii=False))
"""


class LedgerBarrierHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        user_agent = self.headers.get("User-Agent", "")
        with self.server.record_lock:
            self.server.requests.append(
                {
                    "user_agent": user_agent,
                    "path": path,
                    "body": body,
                }
            )
            if path == wb.CLAIM_PATH:
                self.server.claim_count += 1
                response = {"code": 0, "data": {"checked_in": True}}
            elif path == "/alice/user/launch":
                response = {
                    "code": 0,
                    "data": {
                        "ug_campaign_info": {
                            "campaign_group_code": wb.V3_GROUP,
                        },
                    },
                }
            elif path == "/alice/ug/campaign/v3/detail/":
                self.server.detail_count += 1
                checked = self.server.detail_count > 4
                response = detail(checked=checked, state=3 if checked else 2)
            else:
                self.send_error(404)
                return
        payload = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        return


def account() -> wb.Account:
    return wb.Account("账号", "sessionid=x", {"sessionid": "x"})


class FakeClient:
    def __init__(
        self,
        details,
        claim_payload=None,
        claim_error=None,
        claim_hook=None,
        report_payload=None,
        report_error=None,
    ):
        self.details = list(details)
        self.claim_payload = claim_payload or {}
        self.claim_error = claim_error
        self.claim_hook = claim_hook
        self.report_payload = report_payload or {"code": 0, "data": {}}
        self.report_error = report_error
        self.account = account()
        self.calls = []
        self.claim_calls = 0
        self.report_calls = 0

    def post(self, path, body, timeout=30.0):
        self.calls.append((path, body, timeout))
        if path == "/alice/user/launch":
            return {"code": 0, "data": {"ug_campaign_info": {"campaign_group_code": wb.V3_GROUP}}}
        if path == wb.REPORT_PATH:
            self.report_calls += 1
            if self.report_error:
                raise self.report_error
            return self.report_payload
        if path in ("/alice/ug/campaign/v3/detail/", "/alice/ug/campaign/list/"):
            if len(self.details) > 1:
                return self.details.pop(0)
            return self.details[0]
        if path == wb.CLAIM_PATH:
            self.claim_calls += 1
            if self.claim_hook:
                self.claim_hook()
            if self.claim_error:
                raise self.claim_error
            return self.claim_payload
        raise AssertionError("unexpected path %s" % path)


def detail(checked=False, state=2):
    return {
        "code": 0,
        "data": {
            "campaign_group_code": wb.V3_GROUP,
            "tasks": [
                {
                    "campaign_code": "daily-checkin",
                    "campaign_group_code": wb.V3_GROUP,
                    "title": "每日签到",
                    "task_status": state,
                    "reward_mode": 2,
                    "daily_checkin": {
                        "checked_in_today": checked,
                        "continuous_days": 3,
                        "reward": {"reward_amount": 10},
                    },
                }
            ],
        },
    }


class DoubaoWorkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state_path = self.temp.name + "/doubaowork_state.json"

    def tearDown(self):
        self.temp.cleanup()

    def claim(self, client, **kwargs):
        return wb.claim_daily(
            client,
            state_path=self.state_path,
            account_key="account",
            now_ms_fn=lambda: NOW_MS,
            sleep_fn=kwargs.pop("sleep_fn", lambda _delay: None),
            **kwargs,
        )

    def ledger(self):
        return wb.CheckinLedgerStore(
            self.state_path,
            "account",
            now_ms_fn=lambda: NOW_MS,
        ).load()

    def reset_state(self):
        for path in (self.state_path, self.state_path + ".lock"):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def test_parse_cookie_requires_session_and_normalizes(self):
        pairs = wb.parse_cookie("sessionid=abc; sessionid_ss=def; device_id=dev-1")
        self.assertEqual("abc", pairs["sessionid"])
        self.assertEqual("def", pairs["sessionid_ss"])
        self.assertEqual("dev-1", pairs["device_id"])
        with self.assertRaises(wb.DoubaoAuthError):
            wb.parse_cookie("foo=bar")

    def test_collect_tasks_finds_unique_daily_task_and_generic_body(self):
        rows = wb.collect_tasks(detail(), wb.V3_GROUP)
        self.assertEqual(1, len(rows))
        self.assertTrue(rows[0]["daily"])
        self.assertEqual("daily-checkin", rows[0]["key"])
        self.assertEqual(
            {
                "task_id": "",
                "campaign_group_code": wb.V3_GROUP,
                "campaign_item_code": "daily-checkin",
            },
            rows[0]["body"],
        )

    def test_query_params_use_official_device_fingerprint_shape(self):
        client_account = wb.Account(
            "账号",
            "sessionid=x",
            {"sessionid": "x"},
            device_id="dev-1",
            web_id="web-1",
            fingerprint="fp-cookie",
        )
        session = SimpleNamespace(trust_env=True)
        client = wb.DoubaoClient(client_account, session=session)
        params = dict(client.query_params())
        self.assertEqual("1044603", params["aid"])
        self.assertEqual("verify_dev-1", params["fp"])
        self.assertEqual("2.33.5", params["pc_version"])

    def test_already_claimed_is_neutral(self):
        result = self.claim(FakeClient([detail(checked=True, state=3)]))
        self.assertEqual("already", result["status"])
        self.assertTrue(result["completed"])
        self.assertIn("已领取", result["message"])

    def test_pending_is_atomic_before_claim_and_claim_is_confirmed_by_detail(self):
        observed = {}

        def assert_pending_was_saved():
            with open(self.state_path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            observed["pending"] = stored["accounts"]["account"]["pending"]

        client = FakeClient(
            [detail(), detail(checked=True, state=3)],
            {"code": 0, "data": {"checked_in": True, "reward_amount": 10}},
            claim_hook=assert_pending_was_saved,
        )
        result = self.claim(client)
        self.assertEqual("claimed", result["status"])
        self.assertEqual(10, result["points"])
        self.assertEqual("daily-checkin", observed["pending"]["item"])
        self.assertEqual(wb.V3_GROUP, observed["pending"]["group"])
        self.assertEqual("landing_checkin", observed["pending"]["endpoint"])
        claim_call = next(call for call in client.calls if call[0] == wb.CLAIM_PATH)
        self.assertEqual({"scene": wb.V3_GROUP}, claim_call[1])
        report_call = next(call for call in client.calls if call[0] == wb.REPORT_PATH)
        self.assertEqual(
            {"event_type": "user_operate", "biz_event_name": "check_in"},
            report_call[1],
        )
        paths = [call[0] for call in client.calls]
        self.assertLess(paths.index(wb.REPORT_PATH), paths.index(wb.CLAIM_PATH))
        self.assertEqual(1, client.report_calls)
        self.assertIsNone(self.ledger().pending)

    def test_detail_task_status_does_not_override_checked_in_state(self):
        client = FakeClient(
            [detail(checked=False, state=3), detail(checked=True, state=3)],
            {"code": 0, "data": {"checked_in": True}},
        )
        result = self.claim(client)
        self.assertEqual("claimed", result["status"])
        self.assertTrue(result["completed"])
        self.assertEqual(1, client.claim_calls)

    def test_legacy_pending_is_rechecked_then_migrated_to_landing_endpoint(self):
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "version": wb.STATE_VERSION,
                    "accounts": {
                        "account": {
                            "day": wb.beijing_date_key(NOW_MS),
                            "pending": {
                                "group": wb.V3_GROUP,
                                "item": "daily-checkin",
                                "submitted_at": NOW_MS,
                                "rounds": 1,
                                "points": 10,
                            },
                        }
                    },
                },
                handle,
            )
        client = FakeClient(
            [detail(), detail(), detail(checked=True, state=3)],
            {"code": 0, "data": {"checked_in": True}},
        )

        result = self.claim(client)

        self.assertEqual("claimed", result["status"])
        self.assertEqual(1, client.claim_calls)
        claim_call = next(call for call in client.calls if call[0] == wb.CLAIM_PATH)
        self.assertEqual({"scene": wb.V3_GROUP}, claim_call[1])
        self.assertFalse(any(call[0] == wb.LEGACY_CLAIM_PATH for call in client.calls))
        self.assertIsNone(self.ledger().pending)

    def test_receipt_task_status_three_does_not_replace_checked_in(self):
        client = FakeClient(
            [detail()],
            {"code": 0, "data": {"task_status": 3}},
        )
        with self.assertRaises(wb.DoubaoError):
            self.claim(client)
        self.assertIsNotNone(self.ledger().pending)

    def test_confirming_result_is_returned_and_pending_is_retained(self):
        sleeps = []
        client = FakeClient(
            [detail(), detail(checked=False, state=2)],
            claim_error=wb.DoubaoError("豆包工作：领取结果确认中，请稍后重试", 200),
        )
        result = self.claim(client, sleep_fn=sleeps.append)
        self.assertEqual("confirming", result["status"])
        self.assertIsNotNone(result["retry_at"])
        self.assertEqual([2.0, 4.0], sleeps)
        pending = self.ledger().pending
        self.assertIsNotNone(pending)
        self.assertEqual("daily-checkin", pending.item)

    def test_rerun_with_pending_only_queries_same_task_and_never_reclaims(self):
        first = FakeClient(
            [detail(), detail(checked=False, state=2)],
            claim_error=wb.DoubaoError("豆包工作：领取结果确认中，请稍后重试", 200),
        )
        self.claim(first)
        self.assertEqual(1, first.claim_calls)

        second = FakeClient([detail(checked=True, state=3)])
        result = self.claim(second)
        self.assertEqual("done", result["status"])
        self.assertTrue(result["completed"])
        self.assertEqual(0, second.claim_calls)
        self.assertEqual(0, second.report_calls)
        self.assertFalse(any(path == "/alice/user/launch" for path, _, _ in second.calls))
        detail_calls = [
            call for call in second.calls
            if call[0] == "/alice/ug/campaign/v3/detail/"
        ]
        self.assertEqual(1, len(detail_calls))
        self.assertEqual({"campaign_group_code": wb.V3_GROUP}, detail_calls[0][1])
        self.assertIsNone(self.ledger().pending)

    def test_report_failure_does_not_block_or_fake_checkin_result(self):
        failures = (
            requests.Timeout("report timeout"),
            wb.DoubaoError("report business failure", 200, 123),
        )
        for report_error in failures:
            with self.subTest(report_error=type(report_error).__name__):
                self.reset_state()
                client = FakeClient(
                    [detail(), detail(checked=True, state=3)],
                    {"code": 0, "data": {"checked_in": True}},
                    report_error=report_error,
                )
                result = self.claim(client)
                self.assertEqual("claimed", result["status"])
                self.assertEqual(1, client.report_calls)
                self.assertEqual(1, client.claim_calls)
                self.assertIsNone(self.ledger().pending)

    def test_confirming_business_message_also_queries_instead_of_reposting(self):
        client = FakeClient(
            [detail(), detail(checked=False, state=2)],
            claim_error=wb.DoubaoError("豆包工作：领取结果确认中，请稍后重试", 200),
        )
        result = self.claim(client)
        self.assertEqual("confirming", result["status"])
        self.assertEqual(1, client.claim_calls)
        self.assertIsNotNone(self.ledger().pending)

    def test_401_clears_pending_after_rejected_submit(self):
        client = FakeClient(
            [detail()],
            claim_error=wb.DoubaoAuthError("登录态已失效", 401),
        )
        with self.assertRaises(wb.DoubaoAuthError):
            self.claim(client)
        self.assertIsNone(self.ledger().pending)

    def test_direct_reject_statuses_always_clear_pending(self):
        for status in wb.DIRECT_REJECT_STATUSES:
            with self.subTest(status=status):
                self.reset_state()
                client = FakeClient(
                    [detail()],
                    claim_error=wb.DoubaoError("领取结果确认中，请稍后重试", status),
                )
                with self.assertRaises(wb.DoubaoError):
                    self.claim(client)
                self.assertIsNone(self.ledger().pending)

    def test_http_200_auth_code_710012001_clears_pending_even_with_marker(self):
        client = FakeClient(
            [detail()],
            claim_error=wb.DoubaoAuthError(
                "豆包工作：领取结果确认中，稍后重试",
                200,
                710012001,
            ),
        )
        with self.assertRaises(wb.DoubaoAuthError):
            self.claim(client)
        self.assertIsNone(self.ledger().pending)

    def test_http_200_rate_limit_code_710022004_clears_pending_even_with_marker(self):
        client = FakeClient(
            [detail()],
            claim_error=wb.DoubaoRateLimitError(
                "豆包工作：领取结果确认中，稍后重试",
                200,
                710022004,
            ),
        )
        with self.assertRaises(wb.DoubaoRateLimitError):
            self.claim(client)
        self.assertIsNone(self.ledger().pending)

    def test_conditional_reject_confirmation_text_keeps_pending(self):
        for status in wb.CONDITIONAL_REJECT_STATUSES:
            for marker in wb.CONFIRMING_MARKERS:
                with self.subTest(status=status, marker=marker):
                    self.reset_state()
                    client = FakeClient(
                        [detail(), detail(checked=False, state=2)],
                        claim_error=wb.DoubaoError(
                            "豆包工作：%s" % marker,
                            status,
                        ),
                    )
                    result = self.claim(client)
                    self.assertEqual("confirming", result["status"])
                    self.assertIsNotNone(self.ledger().pending)

    def test_conditional_reject_without_confirmation_text_clears_pending(self):
        for status in wb.CONDITIONAL_REJECT_STATUSES:
            with self.subTest(status=status):
                self.reset_state()
                client = FakeClient(
                    [detail()],
                    claim_error=wb.DoubaoError("明确拒绝领取", status),
                )
                with self.assertRaises(wb.DoubaoError):
                    self.claim(client)
                self.assertIsNone(self.ledger().pending)

    def test_landing_success_false_does_not_override_checked_in(self):
        client = FakeClient(
            [detail(), detail(checked=True, state=3)],
            {"code": 0, "data": {"success": False, "checked_in": True}},
        )
        result = self.claim(client)
        self.assertEqual("claimed", result["status"])
        self.assertIsNone(self.ledger().pending)

    def test_invalid_landing_biz_error_keeps_pending(self):
        client = FakeClient(
            [detail()],
            {
                "code": 0,
                "data": {
                    "success": False,
                    "biz_error": "invalid",
                    "checked_in": True,
                },
            },
        )
        with self.assertRaises(wb.DoubaoError):
            self.claim(client)
        self.assertIsNotNone(self.ledger().pending)

    def test_reward_rejected_code_wins_over_confirmation_text(self):
        client = FakeClient(
            [detail()],
            claim_error=wb.DoubaoError(
                "领取结果确认中，请稍后重试",
                400,
                code="reward_rejected",
            ),
        )
        with self.assertRaises(wb.DoubaoError):
            self.claim(client)
        self.assertIsNone(self.ledger().pending)

    def test_receipt_biz_error_without_code_is_not_accepted(self):
        for biz_error in ({"message": "missing business code"}, "invalid", []):
            with self.subTest(biz_error=biz_error):
                self.reset_state()
                client = FakeClient(
                    [detail()],
                    {
                        "code": 0,
                        "data": {
                            "biz_error": biz_error,
                            "task_status": 3,
                        },
                    },
                )
                with self.assertRaises(wb.DoubaoError):
                    self.claim(client)
                self.assertIsNotNone(self.ledger().pending)

    def test_receipt_biz_error_only_zero_is_accepted(self):
        for code in (0, "0"):
            with self.subTest(code=code):
                self.reset_state()
                client = FakeClient(
                    [detail(), detail(checked=True, state=3)],
                    {
                        "code": 0,
                        "data": {
                            "biz_error": {"code": code},
                            "checked_in": True,
                        },
                    },
                )
                result = self.claim(client)
                self.assertEqual("claimed", result["status"])
                self.assertIsNone(self.ledger().pending)

    def test_receipt_biz_error_nonzero_or_fractional_codes_are_rejected(self):
        for code in (4, 6, "4", "6", 0.9, 4.9, 6.9, "0.9", "4.9", "6.9", "4.0"):
            with self.subTest(code=code):
                self.reset_state()
                client = FakeClient(
                    [detail()],
                    {
                        "code": 0,
                        "data": {
                            "biz_error": {"code": code},
                            "checked_in": True,
                        },
                    },
                )
                with self.assertRaises(wb.DoubaoError):
                    self.claim(client)
                self.assertIsNotNone(self.ledger().pending)

    def test_corrupt_receipt_keeps_pending(self):
        client = FakeClient([detail()], {"code": 0, "data": "invalid"})
        with self.assertRaises(wb.DoubaoError):
            self.claim(client)
        pending = self.ledger().pending
        self.assertIsNotNone(pending)
        self.assertEqual("daily-checkin", pending.item)

    def test_timeout_keeps_pending(self):
        client = FakeClient(
            [detail()],
            claim_error=requests.Timeout("timeout"),
        )
        with self.assertRaises(requests.Timeout):
            self.claim(client)
        self.assertIsNotNone(self.ledger().pending)

    def test_server_error_keeps_pending(self):
        client = FakeClient(
            [detail()],
            claim_error=wb.DoubaoError("upstream server error", 500),
        )
        with self.assertRaises(wb.DoubaoError):
            self.claim(client)
        self.assertIsNotNone(self.ledger().pending)

    def test_confirm_budget_timeout_keeps_pending(self):
        monotonic_values = iter((100.0, 118.1))
        client = FakeClient(
            [detail()],
            claim_error=wb.DoubaoError("豆包工作：领取结果确认中，请稍后重试", 200),
        )
        with self.assertRaises(wb.DoubaoError) as raised:
            self.claim(client, monotonic_fn=lambda: next(monotonic_values))
        self.assertEqual(504, raised.exception.status)
        self.assertIsNotNone(self.ledger().pending)

    def test_official_system_error_rechecks_then_clears_pending(self):
        client = FakeClient(
            [detail(), detail()],
            claim_error=wb.DoubaoError(
                "豆包工作：official system error",
                200,
                wb.OFFICIAL_SYSTEM_ERROR_CODE,
            ),
        )
        with self.assertRaises(wb.DoubaoError) as raised:
            self.claim(client)
        self.assertEqual(wb.OFFICIAL_SYSTEM_ERROR_CODE, raised.exception.code)
        self.assertIsNone(self.ledger().pending)
        self.assertEqual(1, client.claim_calls)

    def test_nested_official_system_error_rechecks_then_clears_pending(self):
        client = FakeClient(
            [detail(), detail()],
            {
                "code": 0,
                "data": {
                    "biz_error": {
                        "code": wb.OFFICIAL_SYSTEM_ERROR_CODE,
                        "message": "official system error",
                    },
                },
            },
        )
        with self.assertRaises(wb.DoubaoError) as raised:
            self.claim(client)
        self.assertEqual(wb.OFFICIAL_SYSTEM_ERROR_CODE, raised.exception.code)
        self.assertIsNone(self.ledger().pending)
        self.assertEqual(1, client.claim_calls)

    def test_landing_receipt_points_are_persisted_before_reconcile(self):
        client = FakeClient(
            [detail(), detail(checked=False, state=2)],
            {"code": 0, "data": {"checked_in": True, "reward_amount": 17}},
        )
        result = self.claim(client)
        self.assertEqual("confirming", result["status"])
        pending = self.ledger().pending
        self.assertIsNotNone(pending)
        self.assertEqual(17, pending.points)
        self.assertEqual("landing_checkin", pending.endpoint)

    def test_retry_window_and_round_limit_match_provider(self):
        attempt = wb.PendingAttempt(
            wb.V3_GROUP,
            "daily-checkin",
            NOW_MS,
            1,
            10,
        )
        self.assertEqual(NOW_MS + wb.RETRY_GAP_MS, attempt.retry_at(NOW_MS))
        self.assertIsNone(attempt.retry_at(NOW_MS + 25 * 60 * 1000))
        attempt.rounds = wb.MAX_ROUNDS
        self.assertIsNone(attempt.retry_at(NOW_MS))

    def test_ledger_lock_serializes_threads(self):
        events = []
        events_lock = threading.Lock()
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            with wb._ledger_lock(self.state_path + ".thread.lock"):
                with events_lock:
                    events.append("enter")
                time.sleep(0.05)
                with events_lock:
                    events.append("exit")

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(lambda _index: worker(), range(2)))

        self.assertEqual(["enter", "exit", "enter", "exit"], events)

    def test_two_process_barrier_claims_once_and_late_process_only_queries(self):
        worker_path = Path(self.temp.name) / "ledger_process_worker.py"
        worker_path.write_text(LEDGER_PROCESS_WORKER, encoding="utf-8")
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0),
            LedgerBarrierHandler,
        )
        server.daemon_threads = True
        server.record_lock = threading.Lock()
        server.requests = []
        server.claim_count = 0
        server.detail_count = 0
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        barrier_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        barrier_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        barrier_listener.bind(("127.0.0.1", 0))
        barrier_listener.listen(2)
        barrier_listener.settimeout(15)
        barrier_host, barrier_port = barrier_listener.getsockname()
        processes = []
        connections = []
        server_thread.start()
        try:
            base_url = "http://127.0.0.1:%d" % server.server_port
            for user_agent in ("ledger-process-a", "ledger-process-b"):
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            str(worker_path),
                            str(Path(wb.__file__).resolve()),
                            base_url,
                            self.state_path,
                            self.state_path + ".lock",
                            user_agent,
                            str(NOW_MS),
                            barrier_host,
                            str(barrier_port),
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                )
            for _index in range(2):
                connection, _address = barrier_listener.accept()
                connections.append(connection)
            for connection in connections:
                connection.sendall(b"1")

            outputs = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=20)
                self.assertEqual(
                    0,
                    process.returncode,
                    "worker failed:\nstdout=%s\nstderr=%s" % (stdout, stderr),
                )
                outputs.append(json.loads(stdout.strip().splitlines()[-1]))

            self.assertEqual(["confirming", "done"], sorted(result["status"] for result in outputs))
            with server.record_lock:
                requests = list(server.requests)
                claim_count = server.claim_count
            self.assertEqual(1, claim_count)
            claim_user_agent = next(
                request["user_agent"] for request in requests if request["path"] == wb.CLAIM_PATH
            )
            late_user_agent = (
                "ledger-process-b" if claim_user_agent == "ledger-process-a" else "ledger-process-a"
            )
            late_requests = [
                request for request in requests if request["user_agent"] == late_user_agent
            ]
            self.assertFalse(
                any(request["path"] == "/alice/user/launch" for request in late_requests)
            )
            self.assertFalse(any(request["path"] == wb.CLAIM_PATH for request in late_requests))
            detail_requests = [
                request
                for request in late_requests
                if request["path"] == "/alice/ug/campaign/v3/detail/"
            ]
            self.assertTrue(detail_requests)
            self.assertTrue(
                all(
                    request["body"] == {"campaign_group_code": wb.V3_GROUP}
                    for request in detail_requests
                )
            )
            self.assertIsNone(self.ledger().pending)
        finally:
            for connection in connections:
                connection.close()
            barrier_listener.close()
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=5)

    def test_no_activity_is_inactive(self):
        class NoActivity:
            account = account()

            def post(self, path, body, timeout=30.0):
                return {"code": 0, "data": {}}

        result = self.claim(NoActivity())
        self.assertEqual("inactive", result["status"])

    def test_query_does_not_claim_and_task_status_three_is_not_done(self):
        client = FakeClient([detail(checked=False, state=3)])
        result = wb.query_daily(client)
        self.assertEqual("available", result["status"])
        self.assertFalse(result["completed"])
        self.assertEqual(0, client.claim_calls)
        self.assertEqual(0, client.report_calls)


if __name__ == "__main__":
    unittest.main()
