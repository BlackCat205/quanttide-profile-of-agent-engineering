---
name: second-brain-init
description: 根据量潮公开资产章程创建或维护领域第二大脑，支持新建、补全、追加资产、聚合容器、挂载产品、配套资产英文更名与版本发布，生成可审阅计划并在确认后执行 Git 操作。
---

# 第二大脑创建

先理解用户目标，再把用户认可的名称、概述、边界和相邻领域分工写入 YAML 请求。使用本技能内的程序调查、规划和执行；不要把程序输出的检查通过描述为人工验收通过。

## 入口

可运行入口是 `scripts/engine.py`，配置定义在 `assets/specification.yaml`，两者与本文件放在同一技能目录内即可复制使用。运行环境为 Python 3.10 或以上、PyYAML 6 和 Git。GitHub 模式另需已认证的 GitHub CLI，以及可用于 Git 的账号权限。

## 执行步骤

1. 根据 [请求配置](references/request-schema.md) 选择场景，结合 [场景规则](references/scenarios.md) 和 [契约规则](references/contract-rules.md) 理解用户意图。不要仅凭关键字或 `data/`、`docs/` 目录存在就判定领域类型。
2. 读取工作区内各目标仓库的 AGENTS 和契约。将现有原文、领域边界、名称先例纳入判断；规则冲突时列出冲突再处理。自然语言请求不直接作为命令执行。
3. 写出请求 YAML，运行 `python scripts/engine.py plan --config request.yaml --workspace <工作区> --run-dir <记录目录>`。两目录必须分开。默认 local 模式创建本地 bare 仓库；需要操作公开 GitHub 时显式指定 `--provider github --organization <已获准的账号或组织>`。
4. 展示 `execution-plan.md` 与 JSON 内的调查结果、文档输入、操作范围和计划编号。用户修订时生成新计划；不能沿用旧确认。
5. 用户已经明确认可具体计划后，运行 `approve --run-dir <记录目录> --reviewer <审阅者> --accept <完整计划编号>`；也可以让用户在终端交互确认。没有针对具体内容的确认，不代用户写入确认记录。测试用 `--simulated` 必须如实标为模拟反馈，且只能用于 local 模式。
6. 运行 `apply --run-dir <记录目录>`，由执行器完成已确认的动作、分层提交推送和结果验证。没有确认记录时程序拒绝执行。执行失败会暂停。
7. 查看 `result.md`、`execution-log.json` 和 `verification-report.json`。相同版本、同一计划且状态未漂移时，再次 apply 可恢复；检查点不匹配或进程崩溃留下锁时，先检查原因再重新规划，不强制覆盖。

## 完成判断

程序会检查仓库与远端 HEAD、子模块 URL 与指针、目录、必要文档和 Markdown 基本格式。领域边界是否准确、人工资料是否适当、变更是否符合当前组织章程仍由人和 AI 审阅。报告分别写明程序验证、模拟反馈、真实用户验收及真实 GitHub 验证结果。

此技能的更名场景接受明确的配套资产仓库映射及按子仓库到根仓库排序的引用仓库清单。先搜索影响范围，避免遗漏清单外的引用。发布操作按请求的目标仓库发布版本，生产域名和前台页面建设不属于发布标签的动作。
