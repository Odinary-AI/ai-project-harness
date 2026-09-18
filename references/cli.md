# 脚本接口

Python 3.10+，macOS/Linux，标准库。以下 `H` 表示本 Skill 的 `scripts/harness.py` 实际路径；命令中用实际路径替换。本页只约束脚本模式；模式选择见 [lifecycle.md](lifecycle.md#模式与生效边界)。全局 `--root PROJECT` 放在子命令前。返回码：0 成功或预览，1 检查未满足，2 配置或操作错误。

| 命令 | 输入与作用 |
|---|---|
| `python3 H --root PROJECT adopt --mapping mapping.json` | 预览，不写文件 |
| `python3 H --root PROJECT adopt --mapping mapping.json --apply` | 创建缺失文件；不覆盖已有文件；输出接入缺口 |
| `python3 H --root PROJECT doctor` | 配置、必要文件、占位符和真实链接检查 |
| `python3 H --root PROJECT begin --spec task.json` | 创建 docs/tasks/任务ID.md 和状态入口摘要 |
| `python3 H --root PROJECT verify TASK-001 unit` | 执行该任务所需的 unit 检查，保存独立 RUN |
| `python3 H --root PROJECT pause TASK-001 --next '核对在途操作后继续'` | 记录中断与下一动作，不代表停止外部服务 |
| `python3 H --root PROJECT resume TASK-001` | 新进程读取任务、证据、缺口与下一动作；无命令重放 |
| `python3 H --root PROJECT resume TASK-001 --format text` | 中文摘要展示同一任务、证据及下一动作；默认仍为 JSON |
| `python3 H --root PROJECT resume TASK-001 --activate` | 核对现场后恢复为进行中 |
| `python3 H --root PROJECT reconcile-run TASK-001 RUN-ID --outcome stopped --source docs/recovery.md` | 核对现场后追加历史在途 RUN 处置，不改原件或提供通过证据 |
| `python3 H --root PROJECT close TASK-001` | 核对当前交付条件并保存检查结果，不自动标完成 |
| `python3 H --root PROJECT close TASK-001 --format text` | 用中文展示同一验收、检查和证据判定；仍保存交付回执 |
| `python3 H --root PROJECT close TASK-001 --complete --review-source docs/review.md` | 引用真实语义审阅，条件满足时完成，否则阻塞并列缺口 |

## 项目配置

接入映射示例；argv、输入和确认来源必须换成项目实际内容。所有路径相对 PROJECT，检查命令的 cwd 是 PROJECT。`authorities` 保留历史机器字段名，其含义是规则/入口路径映射，不是额外批准机构。

```json
{
  "authorities": {
    "entrypoint": "README.md",
    "agent_policy": "AGENTS.md",
    "requirements": "docs/requirements.md",
    "validation": "TESTING.md",
    "status": "docs/status.md"
  },
  "confirmation_source": "实际用户授权或项目已确认来源",
  "checks": {
    "unit": {
      "purpose": "验证受影响模块的具体行为",
      "argv": ["python3", "scripts/run_tests.py"],
      "kind": "tests",
      "inputs": ["src", "tests", "scripts/run_tests.py"],
      "environment": [],
      "timeout": 300
    }
  }
}
```

配置在 `.harness/project.json`，实际文件包含 schema_version=1、mechanism_version。mechanism_version记录接入时的执行器版本；doctor输出的是当前实际运行的执行器版本，两者可能不同，不表示安装或迁移已经完成。包版本见[Skill元数据](../SKILL.md)，与配置/任务数据格式版本分开。脚本不自动覆盖配置。doctor 诊断全部映射检查；任务命令只检查当前验收引用的检查配置和输入，共同规则及导航仍须就绪。目录输入包含目录内文件清单（忽略 __pycache__ 与 .DS_Store），新删文件也影响指纹；不要把自动变化的输出或整个项目目录当测试输入。选中的环境变量保存哈希，不保存原始值；日志内容由项目负责脱敏。

status不能与requirements、validation或agent_policy映射到同一实际文件（包含规范化路径、符号链接及现有文件的其他别名），接入预览及写入前均拒绝并指出冲突职责；状态写回会改变这些规则文件的整文件指纹。现有文件按实际身份判断，大小写敏感文件系统上的不同文件可分别映射；未建立的路径若仅大小写不同，先建立并核对实际文件再映射，预览不写探针文件来猜测。沿用分文件映射，不自动拆分已有文件。status仅与entrypoint共文件不受此限制。职责载体必须为非空文件；这些文件中的普通本地导航可以指向存在的文件或目录，缺失目标仍报错。

`kind=tests` 时检查程序必须将 JSON 写到环境变量 `AI_PROJECT_HARNESS_REPORT` 指定的新 RUN 路径：

```json
{"total": 12, "failed": 0, "errors": 0, "skipped": 0}
```

计数来自实际测试框架。零测试、任何必需测试跳过、缺报告不通过。`kind=probe` 用于非测试的真实检查命令，以退出码和日志为证；不可用于绕过测试报告要求。验证命令直接执行 argv，不经过 shell；需 shell 的项目显式配置 shell 程序，并审阅副作用。

## 任务编号与文件命名

新建任务统一使用递增数字 ID，从 `TASK-001` 开始，不足三位补零；超过 `999` 后自然增加位数，例如 `TASK-1000`。接入已有项目时核对已有任务和编号，避免重复或复用已使用的编号。任务文件名与 ID 一致，例如 `docs/tasks/TASK-001.md`；任务名称写在正文标题中，不追加到文件名。

历史四位数字或具名 ID 可继续读取和引用，原始 RUN、交付回执与会话绑定保留原 ID，不因新约定自动改写。需要迁移已有任务时，先核对并处理任务 ID、文件名、状态引用、证据路径和会话绑定，记录新旧对应与依据；没有完成迁移的历史任务继续使用原 ID。本约定由开发 AI 在新建任务时执行；当前 CLI 的字符校验兼容历史 ID，不提供三位编号的自动分配或强制拒绝保障。

## 任务输入及存储

```json
{
  "id": "TASK-001",
  "goal": "实现当前授权目标",
  "scope": "可修改范围和明确非目标",
  "authorization": "真实授权来源",
  "next_action": "实施并验证具体行为",
  "acceptance": [
    {"id": "AC-01", "text": "可观察的结果", "checks": ["unit"], "human_required": false}
  ]
}
```

begin 后唯一状态在 Markdown 的 `harness-task` 块。新任务使用 v2，并建立下述默认字段；未审阅状态不能通过 close。模板 records/task.md 的职责由同一数据块承载，正文仅补事实说明，不重复状态。脚本不会自动迁移非结构化历史。

人工验收字段见 verification.md。RUN 位于 `.harness/evidence/TASK/RUN/`，含 summary.json、summary.sha256、output.log 与适用的 test-report.json。交付检查结果在 `.harness/close/TASK/`。回执原样保留，不删除失败来取得通过。

超时/正常中断对本次子进程组先发SIGTERM，最多等待2秒；组仍存在时发送SIGKILL，再最多等待2秒确认，不因组长先退出而省略后代清理。确认组消失后记录interrupted及实际退出码；无法确认停止（包括清理被再次中断）时保留running、finished_at为空及停止状态未知的原因，后续成功不能消除此在途缺口，须现场核对后按reconcile-run追加处置。执行器被SIGKILL或机器断电时RUN也可能停在running。resume报告缺口，不能凭旧PID自动杀进程或重做。首版没有后台常驻服务；另建会话或进程组的外部操作不在本次进程组的清理范围内。

## unittest 计数适配器

标准 unittest 项目可复用本包 `scripts/unittest_report.py`。在项目检查的 argv 中配置 `["python3", "该适配器的实际路径", "--start", "tests", "--pattern", "test_*.py"]`，kind 为 tests。适配器从当前项目目录发现并真实运行测试，保存计数；沿用框架的成功判定，预期失败用例的意外成功（unexpected success）计入 failed，零测试和跳过也非通过。可在授权内将适配器复制到项目 scripts 并把它加入 inputs，便于脱离 Skill 安装目录继续运行。

doctor 的 ready 仅表示文件、配置和 README 导航检查就绪；接入任务完成还需真实规则审阅、适用检查及交付证据。

## 诊断与验收视图

`resume` 的 assessment 和 `close` 结果保留原有 conditions_met、gaps、runs 等字段，额外提供以下派生信息；不新增任务必填字段：

- `check_results`：按检查 ID 索引，含 run_id、execution_status、evidence_status、conditions_met、log 与 diagnostics。执行成功与证据仍有效分开；未执行、失败、在途、输入失效和损坏分别说明。log 是项目内日志路径，失败细节结合该 RUN 的 summary.json 与原始日志读取。
- `diagnostics` 中每项含 code、message、action，输入变化时另含 changes（kind、name、change）。按文件/目录、环境、检查定义、任务标准、授权来源和执行器定位；只显示环境变量名和变化，不输出变量值或其散列。旧 RUN 仅存检查定义整体摘要，因此该类差异只能定位到检查定义，不能追溯具体配置字段。执行结束时已检测到前后指纹不同并记为失效的 RUN，即使输入之后恢复，仍说明该 RUN 失效。执行期间改变但结束前恢复的输入无法由两次快照识别，执行器不提供持续变化监测。
- `acceptance_results`：按验收项展示 id、text、checks、human_status 与 conditions_met。人工状态 recorded 仅表示来源及标准指纹已记录，不证明确认真实；共同缺口存在时各项机械条件仍未满足。映射齐全不能证明测试语义充分。
- `global_gaps`：共同前置、历史无效/在途回执及审阅材料等缺口。存在无效回执时 runs 可能仍列可读取的旧 RUN，但不能据此当作最新通过，整体与验收项仍受共同缺口阻塞。

JSON 和文本复用同一次评估；默认仍输出 JSON，返回码与既有判定不变。`resume --format text` 只读，`close --format text` 沿用 close 的回执及显式 --complete 副作用。建议动作不是授权，不自动重放检查或改变范围；输入已变化时核对变化，只复验受影响范围。

## 可移植机制自检

接入或修改相关机制时，可运行 `python3 /实际位置/ai-project-harness/scripts/self_test.py`，也可将该命令映射为项目的 tests 检查。使用与 harness.py 一致的 Python 3.10+；脚本只依赖标准库及同包 harness.py/模板，复制整个 Skill 包后可直接运行。

自检在自动清理的临时项目内验证生命周期成功、中断恢复、缺验收/证据、最新失败、无关/相关/执行中输入变化、坏日志/回执、跳过/零测试/坏报告和超时。stdout 输出实际 unittest 计数，stderr 输出逐项结果；设置 AI_PROJECT_HARNESS_REPORT 时另写指定报告，其余情况下不在调用目录写文件。不通过、零测试或跳过返回非零。

这是一组可复用的机制检查，不是完整开发回归或项目适配证明。优先复用已有等效检查；按风险补查项目命令、输入映射和报告转换，产品测试及真实平台事件仍按项目要求执行。不要求每次业务修改都运行自检。

## v2任务处置与更新

purpose.user_outcome 未提供时复用 goal；显式空白或坏值仍是草稿缺口。purpose.stage_ref 有关联时引用项目内文件，无阶段可省略；stage_reason、next_reason 仅在需要额外解释时补充。document_sync 默认 reviewed=false。AI 每次形成决定、修改后反查与交付前主动维护，不要求用户逐项提醒。

最小无文档影响处置（用户结果沿用 goal，下一动作已能说明目的）：

```json
{"document_sync":{"reviewed":true,"no_change_reason":"本次修复恢复既有规则，规则正文不变","items":[]}}
```

这只是字段片段；update 需要完整任务快照。先从 resume 的 task 字段取得完整对象，修改后保存到临时 JSON，再运行 `python3 H --root PROJECT update TASK --spec snapshot.json`；保留 updated_at，防止覆盖其他执行者新内容。不能由 update 改 id、schema、状态、创建时间、迁移与完成审阅字段。人工确认只能按真实来源维护。

- decisions：每项 id、kind（confirmed/authorized/candidate/rejected/observation）、source、summary、rule_ref。已确认或授权内改变规则且有 rule_ref 时，关联同步处置；候选不能当正式依据。
- document_sync：reviewed、no_change_reason、items。items 每项 id、decision_ids数组、path、status（pending/updated/not_needed）、reason。updated 需文件存在且非空；not_needed 需理由；pending 阻止完成。
- changes：每项 path、summary；删除文件可记录路径，语义审阅核对实际差异。
- followups：每项 id、summary、owner、trigger、source。不能转移本次必需验收规避完成要求。
- human_items：每项 id、question、recommendation、materials项目内路径数组、acceptance_id或null。需要人判断与人已确认分开。
- risk_routes：每项 kind（experiment/recovery/side_effect/incident）、applicable布尔、reason、record_ref。适用时需记录文件；风险本身的结果要求加入验收检查。

未完整的v2处置可以保存为草稿，但不能通过交付检查。JSON与文本resume均显示可用信息及具体缺口；文本中必需展示字段的显式空白或未完整内容标“未填写”，可省略字段按上述复用约定展示；不把草稿缺口补成有效内容，也不改写任务或重放命令。

close --complete 的 review-source 在v2必须为项目内非空审阅材料，可引用当前任务文件。新记录的 review_kind=file 散列独立文件，task_body 散列当前任务去掉唯一 harness-task 块后的正文；review_record_sha256 另核对受审任务信息，排除状态、时间、下一动作及审阅管理字段。状态派生文件不能作审阅材料。正文、独立材料或受审记录改变后重新审阅并完成；旧记录无新字段时仍沿用原文件散列。reviewed/文件存在只证明处置可检查，不证明内容正确。下一动作或其原因变化不改变执行标准或受审记录；相关规则、源码和检查配置变化仍使旧证据失效。

`python3 H --root PROJECT migrate-task TASK` 预览旧v1任务；加 --apply 保存原件及散列再升级。未知版本拒绝；v1可只读resume及legacy close，继续verify/activate/pause前需迁移。旧RUN不修改，升级后的当前证据重新核对。TASK源JSON仅为创建历史，别当作当前状态。

## 历史在途执行处置

仅对留在 running 的 RUN 使用 reconcile-run；先核对实际进程、请求身份、目标状态及副作用结局，不能凭旧 PID、新一次成功或正文声明自动认定已结束。--outcome finished / stopped 表示已核对执行结束 / 停止；结局未知不调用解除。--source 指向包含核对事实的项目内材料，可用当前任务正文，不能用状态派生文件。

追加记录位于 .harness/reconciliations/TASK/RUN/，绑定任务、原 RUN 散列、材料散列和结局，不改原执行记录。最近处置损坏或材料、原件变化时不回退旧处置；重新核对后追加新记录。有效处置只解除该历史在途缺口，最新必需检查仍须真实通过。脚本不探测进程是否存活或替人证明材料真实，不停止进程、不重发副作用。
