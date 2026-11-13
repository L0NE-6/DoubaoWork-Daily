<div align="center">

<sub><strong>L0NE-6 · DAILY SIGNAL</strong></sub>

# Doubao Work Daily

**Doubao Work のデイリーチェックイン用単一ファイルスクリプトです。キャンペーンを検出し、報酬を受け取り、キャンペーン詳細の再取得で結果を確認します。**

[简体中文](../README.md) | [English](README.en.md) | [繁體中文](README.zh-Hant.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Português (BR)](README.pt-BR.md)

<img src="https://img.shields.io/github/v/release/L0NE-6/DoubaoWork-Daily?style=for-the-badge&label=Release&color=2ea44f&logo=github" />
<img src="https://img.shields.io/github/stars/L0NE-6/DoubaoWork-Daily?style=for-the-badge&label=Stars&color=FFC75F&logo=github" />
<img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" />

</div>

> 完全な中国語ドキュメントは [../README.md](../README.md) を参照してください。

## ✨ 主な機能

- `/alice/user/launch` で現在のキャンペーン グループを検出します。
- v3 detail または通常の campaign list エンドポイントを選択します。
- 詳細内に `daily_checkin` がちょうど 1 件ある場合だけ処理します。
- 受領済み、未配信、条件未達は中立状態として扱います。
- 合成した `landing/report` イベントは送信しません。checkin 状態を書き換えるのは文書化された `landing/checkin` のみです。
- `710010702` は公式ページ SDK のコンテキストが必要です。公式クライアントでチェックインしてから再実行してください。
- 受領後に詳細を再取得し、`checked_in_today=true` のみを完了条件にします。`task_status=3` は明示的な false を上書きしません。
- 複数アカウント、`--query`、`--only`、PushPlus、Bark、WeCom 通知に対応します。

> チェックイン状態機械は Agent2Providers `v3.4.2` の `doubaowork/checkin`、`checkin_state`、`rewards` に合わせています。本プロジェクトは同じ Cookie + campaign + reward プロトコルを clean-room で実装しています。初回は `--query` から開始してください。

## 🚀 最短セットアップ

```bash
python -m pip install -r requirements.txt
```

`https://www.doubao.com/chat/` にログインし、F12 → Network で完全な Cookie をコピーします。`sessionid` または `sessionid_ss` が必要です。

単一アカウント：

```text
DOUBAOWORK_COOKIE=sessionid=...; sessionid_ss=...
```

複数アカウント：

```text
DOUBAOWORK_COOKIES=
メイン|sessionid=...; sessionid_ss=...
サブ|sessionid=...; sessionid_ss=...
```

実行：

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

`DOUBAOWORK_COOKIES` を設定し、タスクを作成します。

```text
15 9 * * * python3 doubaowork_daily.py
```

初回は `--query` を手動実行し、アカウントとキャンペーンの状態を確認してください。

## ☁️ GitHub Actions

ワークフローは [../.github/workflows/daily.yml](../.github/workflows/daily.yml) です。手動実行が有効で、スケジュールはコメントアウトされています。通常は読み取り専用の `query` で実行し、`workflow_dispatch` で明示的に `mode=claim` を選んだ場合だけ checkin を送信します。スケジュールを有効にしても `query` のみです。

| Secret | 必須 | 用途 |
| :--- | :---: | :--- |
| `DOUBAOWORK_COOKIES` | いずれか | 複数アカウントの Cookie |
| `DOUBAOWORK_COOKIE` | いずれか | 単一アカウントの Cookie |
| `DOUBAOWORK_DEVICE_ID` | 任意 | Device ID |
| `DOUBAOWORK_WEB_ID` | 任意 | Web ID |
| `DOUBAOWORK_FINGERPRINT` | 任意 | Fingerprint |
| `DOUBAOWORK_PROXY` | 任意 | プロキシ |
| `PUSHPLUS_TOKEN` / `BARK_URL` / `WECOM_WEBHOOK` | 任意 | 通知 |

定時実行を有効にする場合はコメントを外します。`15 1 * * *` は UTC で、北京時間 09:15 に相当します。

## 🔧 主な環境変数

| 変数 | 説明 |
| :--- | :--- |
| `DOUBAOWORK_COOKIES` | 複数アカウント：`名前\|cookie` |
| `DOUBAOWORK_COOKIE` | 単一アカウントの Cookie |
| `DOUBAOWORK_ACCOUNTS_FILE` | JSON アカウントファイル |
| `DOUBAOWORK_DEVICE_ID` | 任意の Device ID |
| `DOUBAOWORK_WEB_ID` | 任意の Web ID |
| `DOUBAOWORK_FINGERPRINT` | 任意の Fingerprint |
| `DOUBAOWORK_USER_AGENT` | 任意の User-Agent |
| `DOUBAOWORK_CLIENT_VERSION` | 任意のクライアント版。既定 `2.33.5` |
| `DOUBAOWORK_PROXY` | HTTP(S) / SOCKS5 プロキシ |
| `DOUBAOWORK_NO_NOTIFY` | `1` で通知を無効化 |

## 📊 成功条件

受領 API の応答だけでは成功としません。受領後にキャンペーン詳細を再取得し、`checked_in_today=true` のみを完了条件にします。`task_status=3` は明示的な false を上書きしません。未確認タスクは原子的に置換される pending 台帳に保存され、固定のスレッド／プロセスロックファイルで保護されます。

## 🔒 プライバシー

- Cookie はログイン資格情報です。
- 環境変数、GitHub Secrets、一時的なローカル shell にだけ保存してください。
- 公開 Issue、README、Release、チャットに Cookie を貼らないでください。
- ログでは Cookie をマスクし、アカウント情報をリポジトリへ書き込みません。
- Cookie が漏れた場合はセッションを再ログインで更新してください。

## 利用範囲と再配布について

公式リポジトリ、スクリプト、導入説明、Release ダウンロードは無料です。有料パッケージ化、有料デプロイ、会員限定化、転売、著作者表示の削除、作者のなりすまし、作者の身元や QR コードを推奨・保証として使用すること、無関係なアカウント・グループ・チャンネルへの転載による集客は認められません。違反内容は削除を求められる場合があり、作者は更新の停止、リポジトリのアーカイブまたは削除を行うことがあります。詳細は [../NOTICE.md](../NOTICE.md) を参照してください。

## 🔗 リンク

- [Releases](https://github.com/L0NE-6/DoubaoWork-Daily/releases)
- [Issues](https://github.com/L0NE-6/DoubaoWork-Daily/issues)
- [Changelog](../CHANGELOG.md)
- [License](../LICENSE)
