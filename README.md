<div align="center">

<sub><strong>L0NE-6 · DAILY SIGNAL</strong></sub>

# 🫘 Doubao Work Daily

**豆包工作每日签到单文件脚本：发现活动、领取奖励，并通过活动详情回查确认签到状态。**

[简体中文](README.md) | [English](docs/README.en.md) | [繁體中文](docs/README.zh-Hant.md) | [日本語](docs/README.ja.md) | [한국어](docs/README.ko.md) | [Português (BR)](docs/README.pt-BR.md)

<a href="https://github.com/L0NE-6/DoubaoWork-Daily/releases"><img src="https://img.shields.io/github/v/release/L0NE-6/DoubaoWork-Daily?style=for-the-badge&label=Release&color=2ea44f&logo=github" alt="Release" /></a>
<img src="https://img.shields.io/github/stars/L0NE-6/DoubaoWork-Daily?style=for-the-badge&label=Stars&color=FFC75F&logo=github" alt="Stars" />
<img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
<img src="https://img.shields.io/badge/%E9%9D%92%E9%BE%99-Ready-4EAA25?style=for-the-badge" alt="Qinglong" />
<a href="https://github.com/L0NE-6/DoubaoWork-Daily/actions/workflows/daily.yml"><img src="https://img.shields.io/github/actions/workflow/status/L0NE-6/DoubaoWork-Daily/daily.yml?branch=main&style=for-the-badge&label=Actions&logo=githubactions&logoColor=white" alt="GitHub Actions" /></a>
<img src="https://img.shields.io/github/license/L0NE-6/DoubaoWork-Daily?style=for-the-badge&label=License&color=F472B6" alt="License" />
<a href="https://github.com/L0NE-6/DoubaoWork-Daily/releases"><img src="https://img.shields.io/badge/%E2%AC%87%20Releases-%E4%B8%8B%E8%BD%BD-2ea44f?style=for-the-badge&logo=github&logoColor=white" alt="Releases Download" /></a>

[✨ 30 秒速览](#-30-秒速览) · [🚀 快速开始](#-快速开始) · [🐧 青龙部署](#-青龙部署) · [☁️ GitHub Actions](#-github-actions) · [🔧 环境变量](#-环境变量) · [❓ 常见问题](#-常见问题) · [🚫 使用边界](#usage-policy) · [✦ 星轨](#-星轨-star-trail)

</div>

---

<a id="usage-policy"></a>
## 🚫 使用边界与转载声明

> [!IMPORTANT]
> **官方版本永久免费。** 未经作者书面许可，禁止付费包装、搬运引流、冒充作者，或使用作者身份与二维码制造官方授权假象。违规内容可能被要求下架；作者可暂停更新、归档或删除仓库及相关 Release。

本项目仓库、脚本、部署说明和 Release 下载始终免费公开。未经作者明确书面许可，禁止将本项目包装为付费资源、内部版、独家版、会员权益、收费课程、付费部署或包更新服务；禁止搬运到其他账号、群组、频道、网盘、电商或付费平台进行涨粉、截流、倒卖和引流；禁止删除作者与版权信息后冒充原创；禁止使用作者昵称、头像、二维码和项目名称制造官方授权假象。

> 如需商业合作、品牌授权、联合分发或使用作者名义提供付费服务，请先取得作者明确书面授权。完整规则、收款码防诈骗说明和违规处理方式见 **[NOTICE.md](NOTICE.md)**。

> 官方仓库和 Release 始终免费。第三方以“下载费 / 激活费 / 内部版 / 代部署 / 会员门槛”等名义收费，均与作者无关，请停止付款并保留证据。

> 对上述违规行为，作者有权要求立即停止传播、删除内容并下架相关商品或页面；并可视情况暂停更新、归档或删除本仓库及相关 Release、向平台投诉或采取进一步必要措施。

---

## ✨ 30 秒速览

| 维度 | 说明 |
| :--- | :--- |
| **用途** | 读取豆包工作活动，定位唯一 `daily_checkin` 任务并领取每日奖励。 |
| **输入** | 豆包网页登录 Cookie，必须包含 `sessionid` 或 `sessionid_ss`；支持多账号。 |
| **输出** | 今日已领、可领取、活动未投放、条件未满足、奖励额度和连续天数。 |
| **部署** | 青龙面板、GitHub Actions、Windows / Linux 本地运行。 |
| **依赖** | Python 3 + `requests`；仓库 Actions 使用 Python 3.11。 |
| **成功判据** | landing 回执要求 `checked_in=true`，最终仍以官方详情 `checked_in_today=true` 为唯一完成依据。 |

**核心能力**

- 调用 `/alice/user/launch` 识别当前活动组。
- 自动选择 `pc_incentive_task_mvp_v3` 的 v3 详情接口或普通活动列表接口。
- 只在详情中存在唯一 `daily_checkin` 任务时继续领取。
- 已领取、活动未投放和任务未满足条件均按中性状态处理。
- 领取后强制回查，不把单个业务 `code=0` 当作最终成功。
- pending 台账在写请求前原子落盘，同日重跑只回查同一 `group/item`，不重复提交领取。
- 台账使用进程线程锁和 Windows `msvcrt` / Linux `flock` 固定锁文件，跨线程、跨进程串行。
- GitHub Actions 默认只执行 `--query`；只有手动选择 `mode=claim` 才提交领取。
- 每个账号输出一行脱敏诊断：请求路径、HTTP 状态、业务码、消息、`checked_in_today` 和 pending 状态；不输出 Cookie、Token、手机号或设备值。
- 支持多账号、`--query`、`--only` 和 PushPlus / Bark / 企业微信通知。

> 协议语义对齐 Agent2Providers `v3.4.2` 的 `doubaowork/checkin`、`checkin_state` 与 `rewards`。本脚本按同一条 Cookie + campaign + reward 协议做 clean-room 实现；首次使用建议先执行 `--query`。

## 🧭 工作方式

```text
Cookie
  → POST /alice/user/launch
  → campaign detail / list
  → 找唯一 daily_checkin
  → 固定锁内重读 pending 台账
  → 无 pending 时原子占用并保存
  → POST /alice/ug/campaign/landing/checkin  {"scene": 活动组}
  → 0 / 2 / 4 秒回查同一 group/item
  → 回执 checked_in=true 后继续回查，仅 checked_in_today=true 才算确认
```

脚本只处理 `https://www.doubao.com` 国内站。每日任务必须唯一；活动结构异常或出现多个候选时，脚本会报告无法确认，而不是猜测领取对象。确认预算为 18 秒，未确认任务按 10 分钟间隔、30 分钟窗口和最多 4 轮安排后续只读回查。

> [!IMPORTANT]
> 若 `landing/checkin` 返回 `710010702`，当前页面通常要求 SDK 运行时生成 `biz_params` 与 `AgwCommonParam`。脚本不会伪造这两个风控字段；请在官方客户端点击“立即签到”，然后再次运行脚本。pending 会保留，后续只回读状态，不重复提交。

## 🚀 快速开始

**1. 安装依赖**

```bash
python -m pip install -r requirements.txt
```

**2. 获取 Cookie**

1. 浏览器打开并登录 `https://www.doubao.com/chat/`；
2. 按 F12 打开开发者工具，进入 Network；
3. 复制任意请求的完整 Cookie；
4. Cookie 必须包含 `sessionid` 或 `sessionid_ss`；
5. 不要提交 Cookie 到 GitHub、Issue、Release 或聊天。

**3. 配置单账号**

```text
DOUBAOWORK_COOKIE=sessionid=...; sessionid_ss=...
```

**4. 配置多账号**

```text
DOUBAOWORK_COOKIES=
主账号|sessionid=...; sessionid_ss=...
小号|sessionid=...; sessionid_ss=...
```

**5. 先查询，再领取**

```bash
python doubaowork_daily.py --query
python doubaowork_daily.py
```

## ⌨️ 命令行

| 命令 | 作用 |
| :--- | :--- |
| `python doubaowork_daily.py` | 查询并领取每日奖励 |
| `python doubaowork_daily.py --query` | 只查询，不提交领取请求 |
| `python doubaowork_daily.py --only 1` | 只处理第 1 个账号 |
| `python doubaowork_daily.py --no-notify` | 本轮不发送通知 |
| `python doubaowork_daily.py --version` | 显示脚本版本 |

退出码：`0` 表示本轮没有账号级失败；已领取、活动未投放、条件未满足也属于可解释的中性结果。`1` 表示缺少账号、Cookie 失效、触发限流或至少一个账号发生异常。

## 🐧 青龙部署

```bash
pip3 install requests
```

在青龙环境变量中填写 `DOUBAOWORK_COOKIES`，再创建定时任务：

```text
15 9 * * * python3 doubaowork_daily.py
```

该时间对应仓库 Actions 示例 `15 1 * * *` 的北京时间节奏，青龙使用面板本地时区。首次接入建议先手动执行一次 `--query`，确认活动结构和账号状态后再开启定时。

## ☁️ GitHub Actions

工作流位于 [`.github/workflows/daily.yml`](.github/workflows/daily.yml)。**默认只有手动触发，且默认使用只读 `query` 模式**；定时段目前被注释。

在仓库 `Settings → Secrets and variables → Actions` 中配置：

| Secret | 必填 | 说明 |
| :--- | :---: | :--- |
| `DOUBAOWORK_COOKIES` | 二选一 | 多账号 Cookie |
| `DOUBAOWORK_COOKIE` | 二选一 | 单账号 Cookie |
| `DOUBAOWORK_DEVICE_ID` | 否 | Cookie 缺少设备信息时补充 |
| `DOUBAOWORK_WEB_ID` | 否 | Web ID |
| `DOUBAOWORK_FINGERPRINT` | 否 | 指纹；缺省读取 Cookie 中的 `s_v_web_id` / `fp` |
| `DOUBAOWORK_PROXY` | 否 | HTTP(S) / SOCKS5 代理 |
| `PUSHPLUS_TOKEN` | 否 | PushPlus 推送令牌 |
| `BARK_URL` | 否 | Bark 推送地址 |
| `WECOM_WEBHOOK` | 否 | 企业微信机器人 webhook |

手动执行时选择 `mode=query` 只读取活动详情；只有明确选择 `mode=claim` 才会运行不带 `--query` 的领取命令。以后取消 workflow 中 schedule 两行注释时，定时事件也固定走 `--query`，不会自动提交领取。

同一 Cookie 不要同时在本地和其他云端工作流执行 `claim`。需要切换执行端时，先在一个端点完成状态确认，另一个端点只运行 `query`。仓库内用 `concurrency` 串行同仓运行，但 Git 仓库的并发组无法协调本机进程，因此跨设备互斥仍靠这条操作约束。

工作流没有默认透传 `DOUBAOWORK_ACCOUNTS_FILE`、`DOUBAOWORK_USER_AGENT`、`DOUBAOWORK_CLIENT_VERSION` 和 `DOUBAOWORK_NO_NOTIFY`；这些变量可在本地或青龙中使用，或自行在 workflow 中显式添加映射。

工作流使用 `actions/cache/restore` / `actions/cache/save` 保留最小化 pending 台账；只有显式 `claim` 才保存台账。Actions 级串行不替代脚本内的固定锁文件。

## 🔧 环境变量

### 账号

| 变量 | 必填 | 说明 |
| :--- | :---: | :--- |
| `DOUBAOWORK_COOKIES` | 二选一 | 多账号，每行 `备注\|sessionid=...; sessionid_ss=...` |
| `DOUBAOWORK_COOKIE` | 二选一 | 单账号 Cookie |
| `DOUBAOWORK_ACCOUNTS_FILE` | 否 | 账号 JSON 文件 |

账号 JSON 支持数组或包含 `accounts` 的对象：

```json
{
  "accounts": [
    {
      "name": "主账号",
      "cookie": "sessionid=...; sessionid_ss=...",
      "user_agent": "OPTIONAL_UA",
      "client_version": "2.33.5",
      "device_id": "OPTIONAL_DEVICE_ID",
      "web_id": "OPTIONAL_WEB_ID",
      "fingerprint": "OPTIONAL_FINGERPRINT",
      "proxy": "http://127.0.0.1:7890"
    }
  ]
}
```

### 请求与通知

| 变量 | 说明 |
| :--- | :--- |
| `DOUBAOWORK_DEVICE_ID` | 可选设备 ID |
| `DOUBAOWORK_WEB_ID` | 可选 Web ID |
| `DOUBAOWORK_FINGERPRINT` | 可选指纹；缺省读取 Cookie |
| `DOUBAOWORK_USER_AGENT` | 可选 User-Agent |
| `DOUBAOWORK_CLIENT_VERSION` | 可选客户端版本，默认 `2.33.5` |
| `DOUBAOWORK_PROXY` | HTTP(S) / SOCKS5 代理 |
| `DOUBAOWORK_NO_NOTIFY` | 设为 `1` 时关闭通知 |
| `DOUBAOWORK_BASE_URL` | 高级；默认 `https://www.doubao.com` |
| `DOUBAOWORK_STATE_FILE` | pending 台账路径；默认脚本目录下 `doubaowork_state.json` |
| `DOUBAOWORK_LOCK_FILE` | 固定锁文件路径；默认 `<DOUBAOWORK_STATE_FILE>.lock` |
| `PUSHPLUS_TOKEN` | PushPlus 令牌 |
| `BARK_URL` | Bark 服务地址 |
| `WECOM_WEBHOOK` | 企业微信机器人 webhook，或仅填 key |

## 📊 状态与判定

| 状态 | 含义 |
| :--- | :--- |
| `claimed` | 已提交领取，并在详情回查中确认今日已完成 |
| `already` | 今日此前已领取 |
| `confirming` | 领取结果尚未由详情确认，pending 已保留，后续只查询不重提 |
| `inactive` | 活动未投放、没有唯一每日任务，或尚未满足领取条件 |
| `available` / `done` | `--query` 下的可领取 / 已领取状态 |
| 异常 | Cookie 失效、限流、明确拒绝或领取回执损坏 |

脚本只持久化最小化签到台账：账号 Cookie 哈希、`group/item`、提交时间、轮数和奖励提示，不保存 Cookie 明文、device_id、web_id 或完整账号信息。台账更新使用原子替换，并由固定锁文件串行化。

## ❓ 常见问题

<details>
<summary><b>Cookie 失效是什么表现？</b></summary>

通常返回 HTTP 401、业务码 `710012001` 或 `not logged in`。重新登录豆包网页并复制新的完整 Cookie。
</details>

<details>
<summary><b>为什么显示活动未投放？</b></summary>

当前账号可能没有活动组、活动尚未开放，或上游返回的每日任务不唯一。脚本不会猜测领取对象。
</details>

<details>
<summary><b>领取后为什么还会显示未确认？</b></summary>

领取接口可能先接受请求，活动详情异步刷新。脚本以详情回查为准；稍后重试不会重复发奖。
</details>

<details>
<summary><b>Actions 为什么没有按计划自动运行？</b></summary>

仓库默认保留 `workflow_dispatch`，而 schedule 两行是注释状态。需要定时运行时手动取消注释，并确认 fork 仓库已启用 Actions。
</details>

<details>
<summary><b>`sessionid` 与 `sessionid_ss` 相同正常吗？</b></summary>

脚本不要求两者不同：至少有一个非空值即可；同时存在时会原样发送，台账身份优先使用 `sessionid`，缺失时回退到 `sessionid_ss`。相等值不会改变领取分支，因此不能单凭这一点判定脚本异常。平台是否接受当前登录态仍以请求返回的 HTTP 状态、业务码和官方详情为准。
</details>

## 🔒 隐私与安全

- Cookie 等同于登录态，必须只放在环境变量、GitHub Secrets 或本地临时 shell 中；
- 不把 Cookie 粘贴到公开 Issue、README、Release 或聊天；
- 诊断日志只输出 Cookie 形态、设备上下文类型、HTTP 状态、业务码、接口消息、`checked_in_today` 和 pending 状态，不输出 Cookie、Token、手机号或设备值；
- 本仓库不写入 Cookie、设备标识或完整账号数据；仅写最小化 pending 台账；
- 如果 Cookie 曾公开，请立即退出对应会话或重新登录使旧 Cookie 失效。

## 📦 版本与发布

- 当前候选版本：`v1.3.2`（正式发布状态以 [Releases](https://github.com/L0NE-6/DoubaoWork-Daily/releases) 的 tag 为准）。

## ☕ 支持与反馈

| 支持方式 | 入口 |
| :--- | :--- |
| 追踪版本 | [Releases](https://github.com/L0NE-6/DoubaoWork-Daily/releases) |
| 反馈问题 | [Issues](https://github.com/L0NE-6/DoubaoWork-Daily/issues) |
| 支持项目 | [Star 仓库](https://github.com/L0NE-6/DoubaoWork-Daily) |

反馈时请附上脱敏后的运行状态和接口阶段，不要提交 Cookie、device_id、web_id 或完整账号信息。

### ☕ 赞赏支持

项目免费开放，赞赏完全自愿，不影响任何功能。如果它帮你省下了时间，可以扫码请我喝杯咖啡。

<p align="center">
  <img src="assets/donate-wechat.png" width="260" alt="微信赞赏码" />
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="assets/donate-alipay.jpg" width="260" alt="支付宝赞赏码" />
</p>
<p align="center"><sub>💚 微信支付（左） &nbsp;|&nbsp; 💙 支付宝（右，支持信用卡 / 花呗）</sub></p>

> ⚠️ 收款码仅用于向作者自愿赞赏。任何第三方以代下载、代部署、内部资源或会员群为由收费，均与作者无关，请停止付款并保留证据。

## ✦ 星轨 Star Trail

一条豆包信号穿过活动轨道，每一次 Star 都让下一次运行更容易被看见。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=L0NE-6/DoubaoWork-Daily&type=Date&theme=dark" />
  <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=L0NE-6/DoubaoWork-Daily&type=Date&theme=light" />
  <img alt="Doubao Work Daily Star Trail" src="https://api.star-history.com/svg?repos=L0NE-6/DoubaoWork-Daily&type=Date&theme=light" />
</picture>

<div align="center">

[Releases](https://github.com/L0NE-6/DoubaoWork-Daily/releases) · [Issues](https://github.com/L0NE-6/DoubaoWork-Daily/issues) · [⭐ Star](https://github.com/L0NE-6/DoubaoWork-Daily)

</div>
