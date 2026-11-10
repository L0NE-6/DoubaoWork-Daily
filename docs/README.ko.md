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
- 실제 checkin 직전에 best-effort `landing/report` 작업 이벤트를 전송합니다.
- `710010702`는 공식 페이지 SDK 컨텍스트가 필요하다는 뜻입니다. 공식 클라이언트에서 체크인한 뒤 다시 실행하세요.
- 수령 후 상세를 다시 조회하며 `checked_in_today=true`만 완료 조건으로 사용합니다. `task_status=3`은 명시적인 false를 덮어쓰지 않습니다.
- 다중 계정, `--query`, `--only`, PushPlus, Bark, WeCom 알림을 지원합니다.

> 체크인 상태 머신은 Agent2Providers `v3.4.2`의 `doubaowork/checkin`, `checkin_state`, `rewards` 의미 체계를 따릅니다. 이 프로젝트는 동일한 Cookie + campaign + reward 프로토콜을 clean-room 방식으로 구현했습니다. 처음에는 `--query`부터 실행하세요.

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

수령 API 응답만으로 성공을 판단하지 않습니다. 수령 후 캠페인 상세를 다시 조회하며 `checked_in_today=true`만 완료 조건으로 사용합니다. `task_status=3`은 명시적인 false를 덮어쓰지 않습니다. 미확인 작업은 원자적으로 교체되는 pending 원장에 저장되고 고정 스레드/프로세스 잠금 파일로 보호됩니다.

## 🔒 개인정보

- Cookie는 로그인 자격 증명입니다.
- 환경 변수, GitHub Secrets, 임시 로컬 shell에만 보관하세요.
- 공개 Issue, README, Release, 채팅에 Cookie를 붙여 넣지 마세요.
- 로그에서는 Cookie를 마스킹하며 계정 데이터를 저장소에 기록하지 않습니다.
- Cookie가 노출되었다면 세션을 다시 로그인해 갱신하세요.

## 사용 범위 및 재배포 안내

공식 저장소, 스크립트, 배포 설명 및 Release 다운로드는 무료입니다. 유료 패키징, 유료 배포 대행, 회원 전용화, 재판매, 저작자 표시 삭제, 저작자 사칭, 저작자의 신원이나 QR 코드를 보증처럼 사용하는 행위, 무관한 계정·그룹·채널로 옮겨 트래픽을 유도하는 행위는 허용되지 않습니다. 위반 콘텐츠는 삭제 요청될 수 있으며, 저작자는 업데이트를 중단하거나 저장소를 보관 또는 삭제할 수 있습니다. 전체 규칙은 [../NOTICE.md](../NOTICE.md)를 참고하세요.

## 🔗 링크

- [Releases](https://github.com/L0NE-6/DoubaoWork-Daily/releases)
- [Issues](https://github.com/L0NE-6/DoubaoWork-Daily/issues)
- [Changelog](../CHANGELOG.md)
- [License](../LICENSE)
