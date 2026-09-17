# Codex Stop 适配

仅在用户选择 Codex 事件接入时读取。通用 harness.py 无 Codex 依赖；其他平台需自己的适配和实际验证。

`A` 表示包内 scripts/codex_stop.py 的真实路径。命令先加 `--root PROJECT`。在授权项目中用 `python3 A --root PROJECT config` 生成配置建议，审阅后合并到项目 `.codex/hooks.json`，保留已有事件。配置包含本机解释器与适配器绝对路径；移动包后重新生成。不得将项目生成配置当可移植模板。

Codex 需要项目及具体 hook 的信任。由平台提供的审阅入口处理，不修改信任库、不使用绕过参数代替确认。尚未信任／实测时只能声明适配器可用，不能声明事件已生效。

## 绑定与每轮处置

显式 Skill 调用且有实施授权后，开发 AI 使用平台真实 session/turn ID；不能猜测编号或解析聊天里的完成关键词。

```sh
python3 A --root PROJECT bind --session SESSION --task TASK-003
python3 A --root PROJECT turn --session SESSION --turn TURN --mode progress --reason '已完成局部修改，继续验证'
```

mode 为 progress、completion、waiting_human、interrupted。完成候选先运行通用 close --complete；等待人要在任务 human_items 写具体问题、建议、材料；中断先 pause。每轮结束前维护当前处置，默认不扩大权限。绑定保存在 .harness/codex；换任务先显式 unbind，再 bind。关闭适配或任务切换后 unbind 不删除原始事件。

waiting_human在记录处置及收到Stop时均复用核心待人事项校验：每项有非空id、问题、建议和非空材料路径数组，材料存在且非空，所引用验收ID有效。草稿可保存，但不能作为有效等待理由；事项或材料随后变化时重新核对。该分支只检查待人事项，尚未执行测试或未完成文档同步等其他任务缺口不阻止正常等待人。

## 自动事件

`event` 从 stdin 接收真实 Stop JSON，检查 cwd、session/turn 与绑定。无绑定则报告未启用，不主动接入；过期处置要求一次补救。completion 重算当前证据与文档处置并核对 completed。正常进度、等待人与中断可以结束本轮，任务无需完成。

返回 decision=block 请求 Codex 续轮，不拒绝原 turn。相同缺口或 stop_hook_active 触发有界退出，报告缺口；不会自动跑测试、付费调用或修改人工验收。事件记录在 .harness/codex/events，绑定任务快照与适配器指纹。程序可被有项目写入权限的主体绕过，不是安全隔离。

异常输出明确警告“保障状态未知”；未触发、进程被杀死、超时或其他 hook 冲突需要平台事件记录核对，不能由本脚本证明已拦截。修改配置后重新检查信任。参考 [官方 Stop 行为与信任约定](https://learn.chatgpt.com/docs/hooks)，实际版本差异应重新核实。

验收分别执行：输入夹具、实际平台触发、缺口自动续轮、通过、等待人、中断、未信任、超时、冲突和禁用。只运行 event 子命令不代表平台已经触发。完成报告写清实测范围，不能声称最终回复不可绕过。

## 已知平台边界与接入诊断

本机0.154.0-alpha.6.2的真实引擎事件试验表明：项目未信任会跳过整个项目配置层；hook定义还需单独信任。项目已打开不等于配置已加载。先看 hooks/list 及启动错误，再通过原生审阅入口处理，不能把空列表当不存在hook能力。用户已授权代办接入时可代为操作原生审阅流程，记录具体定义；不直接改写内部信任库或使用绕过参数。

Stop检查前，助手消息可能已经产生；block会注入hookPrompt后继续模型采样，本机观察到可发生在同一turn ID内。超时与退出1记录failed但未强制阻止轮次结束；其他hook的continue=false可终止续轮。未信任／禁用不会执行相应hook。将这些情况报告为保障降级，不承诺不可绕过。

平台事件测试可使用固定本地模型响应作为传输夹具，但必须让真实Codex引擎执行hook，并保存hook/started、hook/completed、hookPrompt及turn结果；直接调用event脚本仍只是适配器测试。固定响应不能证明线上模型连接、模型语义或实际桌面消息可见性。
