import unittest
from types import SimpleNamespace

import doubaowork_daily as wb


class FakeClient:
    def __init__(self, details, claim_payload=None):
        self.details = list(details)
        self.claim_payload = claim_payload or {}
        self.calls = []

    def post(self, path, body):
        self.calls.append((path, body))
        if path == "/alice/user/launch":
            return {"code": 0, "data": {"ug_campaign_info": {"campaign_group_code": wb.V3_GROUP}}}
        if path.startswith("/alice/ug/campaign/") and path != wb.CLAIM_PATH:
            return self.details.pop(0)
        if path == wb.CLAIM_PATH:
            return self.claim_payload
        raise AssertionError("unexpected path %s" % path)


def detail(checked=False, state=2):
    return {
        "code": 0,
        "data": {
            "campaign_group_code": wb.V3_GROUP,
            "tasks": [{
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
            }],
        },
    }


class DoubaoWorkTests(unittest.TestCase):
    def test_parse_cookie_requires_session_and_normalizes(self):
        pairs = wb.parse_cookie("sessionid=abc; sessionid_ss=def; device_id=dev-1")
        self.assertEqual("abc", pairs["sessionid"])
        self.assertEqual("def", pairs["sessionid_ss"])
        self.assertEqual("dev-1", pairs["device_id"])
        with self.assertRaises(wb.DoubaoAuthError):
            wb.parse_cookie("foo=bar")

    def test_collect_tasks_finds_unique_daily_task_and_body(self):
        rows = wb.collect_tasks(detail(), wb.V3_GROUP)
        self.assertEqual(1, len(rows))
        self.assertTrue(rows[0]["daily"])
        self.assertEqual("daily-checkin", rows[0]["key"])
        self.assertEqual({
            "task_id": "",
            "campaign_group_code": wb.V3_GROUP,
            "campaign_item_code": "daily-checkin",
        }, rows[0]["body"])

    def test_query_params_use_official_device_fingerprint_shape(self):
        account = wb.Account(
            "账号", "sessionid=x", {"sessionid": "x"},
            device_id="dev-1", web_id="web-1", fingerprint="fp-cookie",
        )
        session = SimpleNamespace(trust_env=True)
        client = wb.DoubaoClient(account, session=session)
        params = dict(client.query_params())
        self.assertEqual("1044603", params["aid"])
        self.assertEqual("verify_dev-1", params["fp"])
        self.assertEqual("2.33.5", params["pc_version"])

    def test_already_claimed_is_neutral(self):
        result = wb.claim_daily(FakeClient([detail(checked=True, state=3)]))
        self.assertEqual("already", result["status"])
        self.assertIn("已领取", result["message"])

    def test_claim_is_confirmed_by_fresh_detail(self):
        client = FakeClient(
            [detail(), detail(checked=True, state=3)],
            {"code": 0, "data": {"task_status": 3, "reward_amount": 10}},
        )
        result = wb.claim_daily(client)
        self.assertEqual("claimed", result["status"])
        self.assertEqual(10, result["points"])
        self.assertEqual(wb.CLAIM_PATH, client.calls[-2][0])

    def test_claim_without_fresh_confirmation_is_error(self):
        client = FakeClient(
            [detail(), detail(checked=False, state=2)],
            {"code": 0, "data": {"task_status": 3}},
        )
        with self.assertRaises(wb.DoubaoError):
            wb.claim_daily(client)

    def test_no_activity_is_inactive(self):
        class NoActivity:
            def post(self, path, body):
                return {"code": 0, "data": {}}
        result = wb.claim_daily(NoActivity())
        self.assertEqual("inactive", result["status"])

    def test_query_does_not_claim(self):
        client = FakeClient([detail()])
        result = wb.query_daily(client)
        self.assertEqual("available", result["status"])
        self.assertFalse(any(path == wb.CLAIM_PATH for path, _ in client.calls))


if __name__ == "__main__":
    unittest.main()
