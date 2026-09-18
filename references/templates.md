# 模板索引

目录采用、文件归属及小项目合并规则见[项目目录](project-layout.md)，不要求为每种模板单建目录。

共17个模板文件：15个Markdown文档、2个JSON。模板按职责选择，复制后填真实内容。五项基本职责缺载体时参考 core；optional 按实际风险启用；records 提供任务、决定和实验的记录结构；文档模式直接填写，脚本模式以唯一数据块维护任务状态，其余内容按需使用。automation/project.json 是可填写的接入映射，空检查和确认来源会在 doctor 报告未就绪；evidence-summary.json 只说明未执行状态，不作为真实证据。实际格式见 [脚本接口](cli.md)。

- [automation/evidence-summary.json](../assets/templates/automation/evidence-summary.json)
- [automation/project.json](../assets/templates/automation/project.json)
- [core/AGENTS.md](../assets/templates/core/AGENTS.md)
- [core/README.md](../assets/templates/core/README.md)
- [core/TESTING.md](../assets/templates/core/TESTING.md)
- [core/docs/requirements.md](../assets/templates/core/docs/requirements.md)
- [core/docs/status.md](../assets/templates/core/docs/status.md)
- [optional/CHANGELOG.md](../assets/templates/optional/CHANGELOG.md)
- [optional/docs/architecture.md](../assets/templates/optional/docs/architecture.md)
- [optional/docs/backlog.md](../assets/templates/optional/docs/backlog.md)
- [optional/docs/development.md](../assets/templates/optional/docs/development.md)
- [optional/docs/glossary.md](../assets/templates/optional/docs/glossary.md)
- [optional/docs/rules.md](../assets/templates/optional/docs/rules.md)
- [optional/docs/ux-guidelines.md](../assets/templates/optional/docs/ux-guidelines.md)
- [records/decision.md](../assets/templates/records/decision.md)
- [records/experiment.md](../assets/templates/records/experiment.md)
- [records/task.md](../assets/templates/records/task.md)

单任务实施计划与单次发布记录已纳入 task.md 的按需章节，每个实际任务仍为独立文件。跨任务阶段计划的拆分条件、示例与全局信息归属见 [任务流程](lifecycle.md#跨任务安排与发布信息归属)。默认没有总 plan 或 releases 文件，既有等效文件可以映射复用。

实验记录与UX规范分别承载项目事实和标准；检查时按范围读取 [experiment-review.md](experiment-review.md) 与 [ux-review.md](ux-review.md)，不把专项复制成第二份记录模板。两者是参考流程，模板总数不变。

读取与更新：接入、增加职责或模板升级时读取；更新定义后同步模板及受影响实例，按项目授权合并。实例的实际位置由 README 映射，不强制改名。
