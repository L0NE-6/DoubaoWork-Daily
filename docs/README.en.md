<div align="center">

<sub><strong>L0NE-6 · DAILY SIGNAL</strong></sub>

# Doubao Work Daily

**A single-file script for the Doubao Work daily check-in: discover the campaign, claim the reward, and confirm the result by reading the campaign detail again.**

[简体中文](../README.md) | [English](README.en.md) | [繁體中文](README.zh-Hant.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Português (BR)](README.pt-BR.md)

<img src="https://img.shields.io/github/v/release/L0NE-6/DoubaoWork-Daily?style=for-the-badge&label=Release&color=2ea44f&logo=github" />
<img src="https://img.shields.io/github/stars/L0NE-6/DoubaoWork-Daily?style=for-the-badge&label=Stars&color=FFC75F&logo=github" />
<img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" />

</div>

> The complete Chinese documentation is available in [../README.md](../README.md).

## ✨ Core capabilities

- Calls `/alice/user/launch` to identify the active campaign group.
- Chooses the v3 campaign detail endpoint or the regular campaign list endpoint.
- Continues only when exactly one `daily_checkin` task is present.
- Treats already claimed, campaign not deployed, and conditions not met as neutral states.
- Sends a best-effort `landing/report` operation event immediately before an actual check-in claim.
- `710010702` means the official page SDK context is required; click the official check-in button, then rerun for a read-only confirmation.
- Re-reads the campaign detail after claiming and accepts only `checked_in_today=true`; `task_status=3` never overrides an explicit false.
- Supports multiple accounts, query-only mode, single-account selection, and PushPlus, Bark, and WeCom notifications.

> The check-in state machine follows Agent2Providers `v3.4.2` `doubaowork/checkin`, `checkin_state`, and `rewards`. This project is a clean-room implementation of the same Cookie + campaign + reward protocol. Start with `--query`.

## 🚀 Quick start

Install dependencies from the repository root:

```bash
python -m pip install -r requirements.txt
```

Sign in at `https://www.doubao.com/chat/`, open Developer Tools → Network, and copy a complete request Cookie. It must contain `sessionid` or `sessionid_ss`.

Single account:

```text
DOUBAOWORK_COOKIE=sessionid=...; sessionid_ss=...
```

Multiple accounts:

```text
DOUBAOWORK_COOKIES=
Main|sessionid=...; sessionid_ss=...
Alt|sessionid=...; sessionid_ss=...
```

Validate the account before claiming:

```bash
python doubaowork_daily.py --query
python doubaowork_daily.py
python doubaowork_daily.py --only 1
python doubaowork_daily.py --no-notify
```

## 🐧 Qinglong

```bash
pip3 install requests
```

Set `DOUBAOWORK_COOKIES` in the panel and create:

```text
15 9 * * * python3 doubaowork_daily.py
```

This matches the 09:15 Beijing-time rhythm of the workflow example `15 1 * * *`. Run `--query` manually before enabling the schedule.

## ☁️ GitHub Actions

The workflow is [../.github/workflows/daily.yml](../.github/workflows/daily.yml). Manual execution is enabled; the schedule block is commented out.

| Secret | Required | Purpose |
| :--- | :---: | :--- |
| `DOUBAOWORK_COOKIES` | One of two | Multi-account cookies |
| `DOUBAOWORK_COOKIE` | One of two | Single-account cookie |
| `DOUBAOWORK_DEVICE_ID` | Optional | Device ID fallback |
| `DOUBAOWORK_WEB_ID` | Optional | Web ID |
| `DOUBAOWORK_FINGERPRINT` | Optional | Fingerprint fallback |
| `DOUBAOWORK_PROXY` | Optional | HTTP(S) / SOCKS5 proxy |
| `PUSHPLUS_TOKEN`, `BARK_URL`, `WECOM_WEBHOOK` | Optional | Notifications |

To enable the schedule, uncomment its two lines. `15 1 * * *` is UTC and corresponds to 09:15 Beijing time.

## 🔧 Key environment variables

| Variable | Required | Description |
| :--- | :---: | :--- |
| `DOUBAOWORK_COOKIES` | One of two | Records in `name\|cookie` format |
| `DOUBAOWORK_COOKIE` | One of two | Single-account cookie |
| `DOUBAOWORK_ACCOUNTS_FILE` | Optional | JSON account file |
| `DOUBAOWORK_DEVICE_ID` | Optional | Device ID when missing from the cookie |
| `DOUBAOWORK_WEB_ID` | Optional | Web ID |
| `DOUBAOWORK_FINGERPRINT` | Optional | Fingerprint; falls back to `s_v_web_id` or `fp` |
| `DOUBAOWORK_USER_AGENT` | Optional | Custom User-Agent |
| `DOUBAOWORK_CLIENT_VERSION` | Optional | Client version; default `2.33.5` |
| `DOUBAOWORK_PROXY` | Optional | HTTP(S) / SOCKS5 proxy |
| `DOUBAOWORK_NO_NOTIFY` | Optional | Set to `1` to disable notifications |
| `DOUBAOWORK_BASE_URL` | Advanced | Defaults to `https://www.doubao.com` |

## 📊 Success criteria

The claim endpoint alone is not the final proof. After submitting the reward request, the script reads the campaign detail again and accepts only `checked_in_today=true`. A `task_status=3` value does not override an explicit false result. Pending work is kept in an atomically replaced ledger protected by a fixed thread/process lock file.

## 🔒 Privacy

- A Cookie is a login credential.
- Store it only in environment variables, GitHub Secrets, or a temporary local shell.
- Do not paste cookies into public issues, README files, releases, or chat.
- The script masks cookies in logs and never writes cookie plaintext. It only persists a minimal hashed pending ledger.
- Rotate the session if a cookie was exposed.

## Usage and redistribution

The official repository, scripts, deployment instructions, and Release downloads are free. Paid packaging, paid deployment, membership gating, resale, removal of attribution, impersonation of the author, use of the author's identity or QR codes as endorsement, and reposting to unrelated accounts, groups, or channels for traffic diversion are not permitted. Violations may require removal of the content; the author may pause updates, archive the repository, or delete it. See [../NOTICE.md](../NOTICE.md) for the complete rules.

## 🔗 Project links

- [Releases](https://github.com/L0NE-6/DoubaoWork-Daily/releases)
- [Issues](https://github.com/L0NE-6/DoubaoWork-Daily/issues)
- [Changelog](../CHANGELOG.md)
- [License](../LICENSE)
