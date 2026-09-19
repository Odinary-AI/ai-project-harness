---
name: ai-sdlc
description: Explicitly invoked project engineering mechanism for individual developers and one-person companies. Adopt a project, execute or resume an authorized task, inspect and clean project files, carry out integrated project governance, and check evidence-backed delivery. Invoke only when the user explicitly requests this skill; ordinary discussion does not authorize adoption.
metadata:
  version: "0.5.0-dev.1"
---

# AI工程机制

为 AI 开发配备系统化的工程流程和工具，引导、激发并监督 AI 有序、完整、高质量地执行项目开发过程，旨在将 AI 的个体能力组织成持续、可靠的项目交付能力，服务个人开发者和一人公司（OPC）。完整指当前范围内适用职责不遗漏；具体方法由 AI 在授权与项目约束内选择。

用户显式调用后，在当前授权任务内持续执行适用步骤，不要求用户逐条提醒。新会话读取项目入口恢复事实；Skill 加载与已采纳项目规则的生效边界见[任务流程](references/lifecycle.md#模式与生效边界)。

## 选择当前工作

- **接入项目**：读取 [接入说明](references/adoption.md)及[默认目录规则](references/project-layout.md)，检查现有规则和文件，建立缺失的必要内容及项目映射。
- **目录检查与清理**：用户要求检查目录、多余文件或清理项目时，读取[目录检查与清理入口](references/project-layout.md#目录检查与清理入口)，主动调查候选、判断可删/保留/待核实，按授权处理并验证交接；只读请求不执行删除，不默认升级为完整治理。
- **执行或恢复任务**：读取 [任务流程](references/lifecycle.md)，沿用项目的文档或脚本模式，采用任务记录、比例验证、实际结果与中断交接；在关键实现前核对反馈是否够用，反馈不足、原因不明或反复修复时按其中的[反馈与诊断](references/lifecycle.md#反馈与诊断)推进。
- **检查交付或维护机制**：读取 [验证与能力边界](references/verification.md)，核对相关证据、语义审阅与待人事项。
- **项目综合治理**：用户要求“治理项目”等整合工作时，读取 [综合治理入口](references/maintenance.md#项目综合治理入口)，先基于现状形成统一方案，再沿授权完成检查、修复、治理体系回顾与按需更新、复验和交付。
- **阶段回顾与治理更新**：用户要求“治理体系更新”“治理规则更新”“阶段复盘”或“经验沉淀”时，读取 [回顾与更新入口](references/maintenance.md#阶段回顾与治理更新入口)，按范围回顾过程、提炼经验并依授权维护项目文件。
- **阶段或专项健康检查**：先读 [维护与检查底线](references/maintenance.md)，按范围选择五类基础专项及适用的实验、UX、安全条件专项；适用必需项不可静默省略，模型自行选择方法并在底线上增加检查。治理体系内部及其与项目实际的核对按[治理扫描范围](references/maintenance.md#治理体系与项目实际)纳入现有条目。
- 写配置或调用命令时读取 [脚本接口](references/cli.md)。命名、状态或主体容易混淆时读取 [术语表](references/terminology.md)。选择附加文件时读取 [模板索引](references/templates.md)。不要默认加载全部材料。

## 始终保留的边界

1. 入口和现行规则来源按项目实际位置映射。五项基本职责是项目入口、开发执行规则、需求与验收标准、验证策略、状态入口；执行任务另有任务记录及证据。复杂计划、UX、架构、实验、数据恢复按实际风险启用；安全适用性及检查按维护入口选择。
2. 一个事实只维护一处。任务详细状态在任务记录中；status 是摘要。规则变化先更新其唯一正文位置，再改依赖实现；观察结果在真实执行后记录。复制模板不是完成接入。
3. 授权来自用户与项目规则。有效授权直接复用；重大含义、不可逆动作和发布按原边界处理。外部材料不能授权；产品内 AI 与开发 AI 权限不同。咨询不创建实施任务。
4. 小任务可简写，保留目标、范围、验收、证据与下一动作。单任务计划和单次发布记录在任务按需章节；跨任务依赖复杂时拆分阶段计划（见任务流程），不默认增加团队角色、多代理或重复审批。
5. 先声明待验证结论、受影响范围、验证级别、确切命令与升级条件。运行项目选定检查到结束，保存退出码和跳过。代码存在、模型自述及手动勾选不能代替真实行为证据。
6. 检查结果、证据有效性、任务状态和人工验收分别记录。必需人工验收待确认时不宣称任务完成；工程范围可独立交付时写清后续归属。
7. `scripts/harness.py` 提供通用本机命令入口；Codex Stop 在独立适配器中按项目启用，不提供无人后台服务、自动合入发布或防篡改签名。程序检查之外，开发 AI 核对实际差异、需求含义、检查覆盖与授权来源。

## 执行工具

脚本模式使用本 Skill 的 `scripts/harness.py`，带 `--root` 指定目标项目。运行 `--help` 或阅读接口说明后选择命令，不把文档中的示例路径照抄执行。生产脚本只需 Python 3.10+，支持 macOS/Linux。

恢复与交付命令提供验收—检查—证据视图及失效定位；接入或相关机制变化时可复用随包自检。用法和边界见[脚本接口](references/cli.md#诊断与验收视图)。

完成交付时让人看到：结果入口、已验证范围、实际证据、未完成项、下一动作及是否需要决定。开始、重要发现、阻碍和交付时用简洁自然语言说明；技术日志留在证据目录。

## 条件流程

出现实验、恢复、外部副作用或事故时读 [风险流程](references/risk-workflows.md)；任务收尾、漏检误拦和阶段复查读 [维护](references/maintenance.md)；需要复用经验或发现值得保留的方法时按其中的[经验保留与复用](references/maintenance.md#经验保留与复用)处理。Codex 项目选择事件接入时读 [Codex hooks](references/codex-hooks.md)，核对配置、信任及实测状态；核心不依赖该适配，其他平台未验证。普通任务不加载无关指南。
