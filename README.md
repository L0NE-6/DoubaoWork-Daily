# 🫘 Doubao Work Daily

豆包工作（doubao.com）每日奖励签到单文件脚本，支持多账号、查询/领取模式、领取后回查、PushPlus / Bark / 企业微信通知。

> 上游 Agent2Providers v3.3.0-beta.6 的 doubaowork provider 标注为「已实现，待实测」。本脚本按同一条 Cookie + campaign + reward 协议做 clean-room 实现；首次使用建议先 `--query`，确认账号能看到每日任务后再领取。

## 功能

- 读取豆包工作网页 Cookie，调用 `/alice/user/launch`
- 自动识别活动组 `pc_incentive_task_mvp_v3`
- 读取 campaign detail，找到唯一的 `daily_checkin` 每日任务
- 领取 `/alice/ug/campaign/item/reward/claim/`
- **领取后重新拉 detail**，确认 `checked_in_today=true` 或 `task_status=3`
- 已领取、活动未投放、任务未满足条件都按中性结果处理
- 多账号、`--query`、`--only`、通知

## 环境变量

| 变量 | 说明 |
|---|---|
| `DOUBAOWORK_COOKIES` | 多账号，每行一个：`备注\|sessionid=...; sessionid_ss=...` |
| `DOUBAOWORK_COOKIE` | 单账号 Cookie |
| `DOUBAOWORK_ACCOUNTS_FILE` | 可选 JSON 账号文件 |
| `DOUBAOWORK_DEVICE_ID` | 可选，Cookie 没有 `device_id` 时补充 |
| `DOUBAOWORK_WEB_ID` | 可选 |
| `DOUBAOWORK_FINGERPRINT` | 可选，默认取 Cookie 的 `s_v_web_id` / `fp` |
| `DOUBAOWORK_USER_AGENT` | 可选 |
| `DOUBAOWORK_CLIENT_VERSION` | 可选，默认 `2.33.5` |
| `DOUBAOWORK_PROXY` | 可选 HTTP/SOCKS5 代理 |
| `DOUBAOWORK_NO_NOTIFY=1` | 关闭通知 |
| `PUSHPLUS_TOKEN` / `BARK_URL` / `WECOM_WEBHOOK` | 可选通知渠道 |

## 获取 Cookie

1. 浏览器打开并登录 `https://www.doubao.com/chat/`
2. F12 → Network → 复制任意请求的完整 Cookie
3. 必须包含 `sessionid` 或 `sessionid_ss`
4. 不要提交 Cookie 到 GitHub、Issue 或聊天

## 使用

```bash
pip install requests
export DOUBAOWORK_COOKIE='sessionid=...; sessionid_ss=...'
python doubaowork_daily.py --query
python doubaowork_daily.py
```

多账号：

```bash
export DOUBAOWORK_COOKIES=$'账号一|sessionid=...\n账号二|sessionid=...'
python doubaowork_daily.py
```

## 命令

```text
python doubaowork_daily.py              # 查询并领取
python doubaowork_daily.py --query      # 只查询
python doubaowork_daily.py --only 1     # 只跑第 1 个账号
python doubaowork_daily.py --no-notify  # 不推送
```

## 协议边界

- 只处理 `https://www.doubao.com` 国内站
- 只认 Cookie 里的 `sessionid` / `sessionid_ss`
- 每日任务必须是活动详情里唯一带 `daily_checkin.checked_in_today` 的任务
- 领取后必须回查确认；没有确认不会伪报成功
- 没有任何账号数据写入仓库

## 安全

Cookie 等同于登录态。请只放在青龙环境变量、GitHub Secrets 或本地临时 shell 中，不要粘到公开 Issue、README、Release 或聊天。

## License

MIT
