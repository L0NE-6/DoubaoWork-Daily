# 更新日志

## v1.1.0（2026-11-05）

- 对齐 Agent2Providers `v3.4.2`：领取前原子写入 pending，同日重跑只回查原 `group/item`，不会重复提交领取。
- 新增线程锁与跨进程固定锁文件（Windows `msvcrt`、Linux `flock`）；持锁重读台账并完成 pending 检查、占用、保存和后续清除。
- 实现 18 秒确认预算、`0/2/4` 秒回查、10 分钟重试间隔、30 分钟窗口和最多 4 轮。
- 完成只认 `checked_in_today=true`；`task_status=3` 不再覆盖明确的 false。
- `401/403/429` 始终视为不可确认并清除；HTTP 200 的鉴权码 `710012001` 与限流码 `710022004` 按异常类型/业务码优先清除；`400/404/405/422` 在正文含“领取结果确认中 / 确认中 / 稍后重试”时保留 pending，其余明确拒绝才清除。
- `success:false` 优先于 `biz_error`；有效业务码必须是严格整数 `0/4/6`，缺码、小数或非整数文本均不接受。
- 新增 30 项离线回归，其中包含双进程屏障测试；双进程同时启动时仅一个进程提交 claim，后进进程只回查相同任务。
- 验证：`unittest`、双进程测试、`py_compile`、`ruff check/format`、YAML/actionlint、`git diff --check` 与敏感扫描；本版未使用真实账号执行签到。

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
