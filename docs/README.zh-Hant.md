<div align="center">

<sub><strong>L0NE-6 · DAILY SIGNAL</strong></sub>

# Doubao Work Daily

**豆包工作每日簽到單檔腳本：發現活動、領取獎勵，並透過活動詳情回查確認簽到狀態。**

[简体中文](../README.md) | [English](README.en.md) | [繁體中文](README.zh-Hant.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Português (BR)](README.pt-BR.md)

<img src="https://img.shields.io/github/v/release/L0NE-6/DoubaoWork-Daily?style=for-the-badge&label=Release&color=2ea44f&logo=github" />
<img src="https://img.shields.io/github/stars/L0NE-6/DoubaoWork-Daily?style=for-the-badge&label=Stars&color=FFC75F&logo=github" />
<img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" />

</div>

> 完整中文文件請見 [../README.md](../README.md)。

## ✨ 核心能力

- 呼叫 `/alice/user/launch` 識別目前活動組。
- 依活動組選擇 v3 detail 或一般 campaign list 介面。
- 只有詳情中存在唯一 `daily_checkin` 任務時才繼續。
- 已領取、活動未投放、尚未滿足條件都按中性狀態處理。
- 真正提交 checkin 前先發送 best-effort `landing/report` 操作事件。
- 領取後重新讀取詳情，只接受 `checked_in_today=true`；`task_status=3` 不會覆蓋明確的 false。
- 支援多帳號、`--query`、`--only` 與 PushPlus、Bark、企業微信通知。

> 簽到狀態機對齊 Agent2Providers `v3.4.2` 的 `doubaowork/checkin`、`checkin_state` 與 `rewards`。本腳本依相同 Cookie + campaign + reward 協議進行 clean-room 實作，首次使用建議先執行 `--query`。

## 🚀 最短可行設定

```bash
python -m pip install -r requirements.txt
```

登入 `https://www.doubao.com/chat/`，以 F12 → Network 複製完整 Cookie，必須包含 `sessionid` 或 `sessionid_ss`。

單帳號：

```text
DOUBAOWORK_COOKIE=sessionid=...; sessionid_ss=...
```

多帳號：

```text
DOUBAOWORK_COOKIES=
主帳號|sessionid=...; sessionid_ss=...
小號|sessionid=...; sessionid_ss=...
```

執行：

```bash
python doubaowork_daily.py --query
python doubaowork_daily.py
python doubaowork_daily.py --only 1
python doubaowork_daily.py --no-notify
```

## 🐧 青龍面板

```bash
pip3 install requests
```

設定 `DOUBAOWORK_COOKIES`，建立任務：

```text
15 9 * * * python3 doubaowork_daily.py
```

首次接入請先手動執行 `--query`，確認帳號與活動狀態後再開啟定時。

## ☁️ GitHub Actions

工作流為 [../.github/workflows/daily.yml](../.github/workflows/daily.yml)。目前啟用手動觸發，排程區塊是註解狀態。

| Secret | 必填 | 用途 |
| :--- | :---: | :--- |
| `DOUBAOWORK_COOKIES` | 二選一 | 多帳號 Cookie |
| `DOUBAOWORK_COOKIE` | 二選一 | 單帳號 Cookie |
| `DOUBAOWORK_DEVICE_ID` | 否 | 設備 ID |
| `DOUBAOWORK_WEB_ID` | 否 | Web ID |
| `DOUBAOWORK_FINGERPRINT` | 否 | 指紋 |
| `DOUBAOWORK_PROXY` | 否 | 代理 |
| `PUSHPLUS_TOKEN` / `BARK_URL` / `WECOM_WEBHOOK` | 否 | 通知 |

若要啟用排程，取消兩行註解。`15 1 * * *` 使用 UTC，對應北京時間 09:15。

## 🔧 關鍵環境變數

| 變數 | 說明 |
| :--- | :--- |
| `DOUBAOWORK_COOKIES` | 多帳號：`備註\|cookie` |
| `DOUBAOWORK_COOKIE` | 單帳號 Cookie |
| `DOUBAOWORK_ACCOUNTS_FILE` | 帳號 JSON 檔案 |
| `DOUBAOWORK_DEVICE_ID` | 可選設備 ID |
| `DOUBAOWORK_WEB_ID` | 可選 Web ID |
| `DOUBAOWORK_FINGERPRINT` | 可選指紋；預設讀取 Cookie |
| `DOUBAOWORK_USER_AGENT` | 可選 User-Agent |
| `DOUBAOWORK_CLIENT_VERSION` | 可選版本，預設 `2.33.5` |
| `DOUBAOWORK_PROXY` | HTTP(S) / SOCKS5 代理 |
| `DOUBAOWORK_NO_NOTIFY` | `1` 關閉通知 |

## 📊 成功判據

領取介面回傳成功不是最終依據。送出領取後會重新讀取活動詳情，只接受 `checked_in_today=true`；`task_status=3` 不會覆蓋明確的 false。待確認任務保存在原子替換的 pending 台帳中，並由固定執行緒／跨程序鎖檔案保護。

## 🔒 隱私與安全

- Cookie 等同登入態。
- 只放在環境變數、GitHub Secrets 或本地暫存 shell。
- 不要把 Cookie 貼到公開 Issue、README、Release 或聊天。
- 日誌會遮罩 Cookie，不會寫入帳號資料。
- Cookie 若曾公開，請立即重新登入或使舊工作階段失效。

## 使用邊界與轉載聲明

官方版本免費。禁止付費包裝、付費部署、會員門檻、轉售、刪除署名、冒充作者、以作者身分或二維碼作背書，或搬運到無關帳號、群組與頻道引流。違規內容可能被要求下架；作者可暫停更新、封存或刪除倉庫。完整規則見 [../NOTICE.md](../NOTICE.md)。

## 🔗 專案連結

- [Releases](https://github.com/L0NE-6/DoubaoWork-Daily/releases)
- [Issues](https://github.com/L0NE-6/DoubaoWork-Daily/issues)
- [Changelog](../CHANGELOG.md)
- [License](../LICENSE)
