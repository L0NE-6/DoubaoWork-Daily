# 更新日志

## v1.3.3（2026-11-14）

- `--query` 增加显式活动组详情探测：当 `/alice/user/launch` 返回 `code=0` 但缺少 `campaign_group_code`、同时配置了 `DOUBAOWORK_CAMPAIGN_GROUP` 时，继续只读请求活动详情确认 `checked_in_today`。
- GitHub Actions 的 query/claim 步骤默认传入 `DOUBAOWORK_CAMPAIGN_GROUP=pc_incentive_task_mvp_v3`；仓库变量可覆盖。
- claim 的写保护不变：launch 缺组时不会因为显式组而提交 `/landing/checkin`，必须先由 query 证据确认活动可见。
- 诊断新增 `launch_shape`、`launch_group_missing`、`detail_probe` 以及 `has_device_id` / `has_web_id` / `has_fp` 布尔值，不输出凭据或设备原值。
- 新增 launch 缺组 + 显式详情成功、无显式组保持 inactive、claim 不探测/不写请求的回归；全套 `45` 项测试通过。

## v1.3.2（2026-11-13）

- GitHub Actions 默认执行只读 `--query`；只有 `workflow_dispatch` 显式选择 `mode=claim` 才运行领取，schedule 即使启用也固定只读。
- 移除 `landing/report` 合成 `user_operate` 写请求。该事件没有参与成功判定，也不在当前 Agent2Providers doubaowork 签到实现中；它会增加云端风控面，不能替代官方页面 SDK 上下文。
- 每个账号新增单行脱敏诊断，记录请求路径、HTTP 状态、业务 `code`、消息、`checked_in_today`、pending 状态、session Cookie 形态和设备上下文类型，不输出 Cookie、Token、手机号或设备值。
- 明确 `sessionid==sessionid_ss` 不是脚本分支条件：两者至少有一个非空即可，同时存在时原样发送，台账身份优先使用 `sessionid`。
- 新增 Actions 默认只读、显式 claim、无额外 report 写请求、相等 session Cookie、诊断脱敏和 pending 状态回归；全套 `41` 项测试通过。

## v1.3.1（2026-11-10）

- `710010702` 重新归类为“需要官方活动页 SDK”：当前 landing/checkin 需要页面运行时生成的 `biz_params` 与 `AgwCommonParam`，纯 HTTP 不自行伪造。
- 收到该错误后不再执行 0/2/4 秒重复详情探测，也不清除 pending；只做一次状态回读后明确提示。
- pending 保留后，后续运行只回读状态，不会重复发送无效 claim；用户在官方客户端点击“立即签到”后再次运行即可确认并清除 pending。
- `landing/report` 继续作为 best-effort 操作事件，但不再暗示它能替代 SDK 风控上下文。
- 新增 SDK 错误保留 pending、官方点击后无重复 claim 的回归；全套 `37` 项测试通过。

## v1.3.0（2026-11-09）

- 在真实提交 `landing/checkin` 前补发 `landing/report` 操作事件：`event_type=user_operate`、`biz_event_name=check_in`。
- report 只在 pending 已原子落盘且本轮确实需要提交 claim 时发送；已有 pending 的只读回查、`--query` 和已签到状态都不发送 report。
- report 采用 best-effort：网络失败、HTTP 错误或业务错误只记录日志，不阻断 claim，也不参与签到成功判定。
- 最终成功仍要求 claim 回执 `checked_in=true`，并继续以官方详情 `checked_in_today=true` 为唯一完成依据。
- 新增 report 顺序、业务失败不阻断、pending 重跑不重复 report 等回归；全套 `36` 项测试通过。

## v1.2.0（2026-11-07）

- 每日签到接口迁移到 `POST /alice/ug/campaign/landing/checkin`，请求体改为 `{"scene": campaign_group_code}`；旧任务领奖接口不再用于每日签到。
- 即时回执只接受 `data.biz_error` 为空或业务码 `0`，并要求 `data.checked_in=true`；`task_status=3` 或单独 `success:false` 不再覆盖官方签到标记。
- 写入后继续回查同一活动与任务，只有详情 `daily_checkin.checked_in_today=true` 才返回已领取。
- `710010702` 按官方系统错误处理：先回查官方状态，仍未签到才清除待确认记录并返回错误。
- 待确认记录增加稳定端点语义与错误字段；旧记录缺少端点时按旧任务领奖接口回查，明确未签到后才迁移到 landing 签到。
- 回执积分立即持久化；新增 landing 回执、旧状态迁移、嵌套系统错误与积分落盘测试，全套 `35` 项测试通过。

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
