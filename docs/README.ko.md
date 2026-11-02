<div align="center">

<sub><strong>L0NE-6 · DAILY SIGNAL</strong></sub>

# Doubao Work Daily

**Doubao Work 일일 체크인을 위한 단일 파일 스크립트입니다. 캠페인을 찾고 보상을 수령한 뒤, 캠페인 상세를 다시 읽어 결과를 확인합니다.**

[简体中文](../README.md) | [English](README.en.md) | [繁體中文](README.zh-Hant.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Português (BR)](README.pt-BR.md)

<img src="https://img.shields.io/github/v/release/L0NE-6/DoubaoWork-Daily?style=for-the-badge&label=Release&color=2ea44f&logo=github" />
<img src="https://img.shields.io/github/stars/L0NE-6/DoubaoWork-Daily?style=for-the-badge&label=Stars&color=FFC75F&logo=github" />
<img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" />

</div>

> 전체 중국어 문서는 [../README.md](../README.md)에서 확인하세요.

## ✨ 핵심 기능

- `/alice/user/launch`로 현재 캠페인 그룹을 확인합니다.
- v3 detail 또는 일반 campaign list 엔드포인트를 선택합니다.
- 상세 정보에 `daily_checkin` 작업이 정확히 하나 있을 때만 진행합니다.
- 이미 수령, 캠페인 미배포, 조건 미충족은 중립 상태로 처리합니다.
- 수령 후 상세를 다시 조회해 `checked_in_today=true` 또는 `task_status=3`을 확인합니다.
- 다중 계정, `--query`, `--only`, PushPlus, Bark, WeCom 알림을 지원합니다.

> 상류 Agent2Providers `v3.3.0-beta.6` provider는 “구현됨, 실계정 미검증”으로 표시되어 있습니다. 이 프로젝트는 동일한 Cookie + campaign + reward 프로토콜을 clean-room 방식으로 구현했습니다. 처음에는 `--query`부터 실행하세요.

## 🚀 최단 설정

```bash
python -m pip install -r requirements.txt
```

`https://www.doubao.com/chat/`에 로그인한 뒤 F12 → Network에서 전체 Cookie를 복사합니다. `sessionid` 또는 `sessionid_ss`가 포함되어야 합니다.

단일 계정:

```text
DOUBAOWORK_COOKIE=sessionid=...; sessionid_ss=...
```

다중 계정:

```text
DOUBAOWORK_COOKIES=
메인|sessionid=...; sessionid_ss=...
서브|sessionid=...; sessionid_ss=...
```

실행:

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

`DOUBAOWORK_COOKIES`를 설정하고 작업을 만듭니다.

```text
15 9 * * * python3 doubaowork_daily.py
```

처음에는 `--query`를 수동 실행해 계정과 캠페인 상태를 확인한 뒤 정기 실행을 켜세요.

## ☁️ GitHub Actions

워크플로는 [../.github/workflows/daily.yml](../.github/workflows/daily.yml)입니다. 수동 실행이 활성화되어 있고 일정 부분은 주석 처리되어 있습니다.

| Secret | 필수 | 용도 |
| :--- | :---: | :--- |
| `DOUBAOWORK_COOKIES` | 둘 중 하나 | 다중 계정 Cookie |
| `DOUBAOWORK_COOKIE` | 둘 중 하나 | 단일 계정 Cookie |
| `DOUBAOWORK_DEVICE_ID` | 선택 | Device ID |
| `DOUBAOWORK_WEB_ID` | 선택 | Web ID |
| `DOUBAOWORK_FINGERPRINT` | 선택 | Fingerprint |
| `DOUBAOWORK_PROXY` | 선택 | 프록시 |
| `PUSHPLUS_TOKEN` / `BARK_URL` / `WECOM_WEBHOOK` | 선택 | 알림 |

정기 실행을 사용하려면 주석을 해제하세요. `15 1 * * *`는 UTC 기준이며 베이징 시간 09:15입니다.

## 🔧 주요 환경 변수

| 변수 | 설명 |
| :--- | :--- |
| `DOUBAOWORK_COOKIES` | 다중 계정: `이름\|cookie` |
| `DOUBAOWORK_COOKIE` | 단일 계정 Cookie |
| `DOUBAOWORK_ACCOUNTS_FILE` | JSON 계정 파일 |
| `DOUBAOWORK_DEVICE_ID` | 선택 Device ID |
| `DOUBAOWORK_WEB_ID` | 선택 Web ID |
| `DOUBAOWORK_FINGERPRINT` | 선택 Fingerprint |
| `DOUBAOWORK_USER_AGENT` | 선택 User-Agent |
| `DOUBAOWORK_CLIENT_VERSION` | 선택 클라이언트 버전, 기본 `2.33.5` |
| `DOUBAOWORK_PROXY` | HTTP(S) / SOCKS5 프록시 |
| `DOUBAOWORK_NO_NOTIFY` | `1`이면 알림 비활성화 |

## 📊 성공 기준

수령 API 응답만으로 성공을 판단하지 않습니다. 수령 후 캠페인 상세를 다시 조회해 `checked_in_today=true` 또는 `task_status=3`을 확인해야 합니다. 상세 조회로 확인되지 않으면 미확인으로 보고합니다.

## 🔒 개인정보

- Cookie는 로그인 자격 증명입니다.
- 환경 변수, GitHub Secrets, 임시 로컬 shell에만 보관하세요.
- 공개 Issue, README, Release, 채팅에 Cookie를 붙여 넣지 마세요.
- 로그에서는 Cookie를 마스킹하며 계정 데이터를 저장소에 기록하지 않습니다.
- Cookie가 노출되었다면 세션을 다시 로그인해 갱신하세요.

## 🔗 링크

- [Releases](https://github.com/L0NE-6/DoubaoWork-Daily/releases)
- [Issues](https://github.com/L0NE-6/DoubaoWork-Daily/issues)
- [Changelog](../CHANGELOG.md)
- [License](../LICENSE)
