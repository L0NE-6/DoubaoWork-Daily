# 更新日志

## v1.0.0（2026-11-02）

- 首个版本：豆包工作每日奖励签到。
- 支持 Cookie / Cookie JSON、多账号、`--query`、`--only`。
- 协议链路：`/alice/user/launch` → campaign detail → `reward/claim` → detail 回查。
- 每日任务必须唯一；`checked_in_today=true` / `task_status=3` 才算确认。
- 已领取、活动未投放、未满足条件按中性结果处理。
- 支持 PushPlus / Bark / 企业微信通知。
