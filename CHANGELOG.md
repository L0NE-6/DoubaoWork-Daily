# 更新日志

## v1.0.1（2026-11-04）

- 文档发行版：同步首屏使用边界、反收费/反搬运声明、`NOTICE.md`、微信/支付宝赞赏码防诈骗提醒与六语导航。
- Release 完整包现在包含最新 README、NOTICE、docs 与图片资产；签到/领取主逻辑未变更，脚本版本仍为 `v1.0.0`。
- 验证：Markdown 渲染、相对链接、二维码资产与发布包清单检查通过；本版未使用真实账号执行签到。

## v1.0.0（2026-11-02）

- 首个版本：豆包工作每日奖励签到。
- 支持 Cookie / Cookie JSON、多账号、`--query`、`--only`。
- 协议链路：`/alice/user/launch` → campaign detail → `reward/claim` → detail 回查。
- 每日任务必须唯一；`checked_in_today=true` / `task_status=3` 才算确认。
- 已领取、活动未投放、未满足条件按中性结果处理。
- 支持 PushPlus / Bark / 企业微信通知。
