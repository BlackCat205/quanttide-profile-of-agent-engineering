# 第二大脑创建插件使用说明

非技术用户使用 UI 0.8.3，请先阅读仓库根目录 [START_HERE.md](../../../START_HERE.md)，按按钮完成个人账号登录、创建和验收。下文为维护者配置入口说明；真实 Windows/GitHub/资产云验收状态见 [上线与联调说明](上线与联调说明.md)。

## 推荐从中文界面开始

0.3.0 已增加中文创建向导，复用 0.2.0 执行器。日常新建不再需要复制本页命令：按照 [从这里开始](../../../START_HERE.md) 完成首次配置，之后双击“启动向导.bat”，在页面填写需求、审阅、执行并记录验收意见。下文命令保留给维护者和其他维护场景。

界面支持本地新建，并提供需维护者启用的真实 GitHub 表单；真实 GitHub 和 Windows 图形流程尚未完成联调。

## 你会得到什么

这个插件把量潮已有的对话流程变成可重复运行的配置：先整理你的需求，展示要建立或修改的仓库，确认后执行，最后检查结果。

当前版本为 0.2.0。已完成 Linux 环境下的实际本地 Git 测试和资产云 CLI 读取测试；真实 GitHub 组织操作、Windows、macOS 和真实非技术用户验收尚未验证。这里的 Linux 是执行测试的计算机系统，不要求你的电脑必须使用 Linux。

## 先看懂原始资料

GitHub 的“仓库”可以理解为带修改历史的项目文件夹。资料分放在两个项目里：

| 项目或文件 | 通俗解释 | 你需要关注什么 |
|---|---|---|
| `quanttide-profile-of-agent-engineering` | 实践资料文件夹 | 打开其中的 `quanttide-asset` |
| `sessions/second-brain-init.jsonl` | 原始聊天导出 | 留作追溯，平时不用直接读 |
| `contexts/second-brain-init.md` | 已整理的操作流程 | 说明名称、仓库关系和创建步骤 |
| `quanttide-bylaw-of-asset-management` | 管理规则文件夹 | `contract/public-second-brain.md` 是本次主要依据 |
| `skills/second-brain-init` | 给 AI 的操作手册和执行程序 | 由维护者接入 AI 工作环境 |
| `loops/second-brain-init` | 运行配套资料 | 使用说明、示例配置、测试记录都在这里 |

新增的 `.quanttide/asset/contract.yaml` 就是一张“资料登记表”：列出原始会话、上下文、技能、运行配置、说明和测试记录各在哪里。添加它是本次接入资产云的本地改动；它本身不会上传资料、改公司章程或创建 GitHub 仓库。资产云读取它后可以识别这些资料，执行入口另见接入说明。

## 如何验收

运行后按 [非技术用户验收表](ACCEPTANCE.md) 检查。表中将原始规范翻译为可观察的标准，区分程序检查与本人判断；命令运行成功不等于使用体验验收通过。

## 日常使用：你只需要说明目标和审阅结果

请先让维护者完成下面的安装。然后在加载了本技能、能够运行 Python 和 Git 的 AI 工作环境中发送：

> 请用第二大脑创建插件，为“示例工程”建立第二大脑。英文名 sample-engineering，简称 sample。用于整理团队工程实践；范围包括实践记录、工具和实验；与文档工程协作管理文档规范。先展示计划，使用本地试运行模式。

AI 会和你核对领域名称、作用、边界与相邻领域分工；遇到已有资料会先调查，然后展示仓库清单及修改内容。

新建流程建立 7 个仓库：领域主仓库，以及应用云、工具集、实验室、语境、日志、意图 6 个配套仓库。配套仓库先提供 README 骨架，业务内容随后填写。领域主仓库会有标准目录、概述、边界、相邻领域分工、资产目录、LICENSE 和变更记录。本地演示额外建立 1 个根仓库作为测试环境，所以测试中会看到 8 个仓库。

看计划时，你主要核对三件事：

1. 名称、领域范围和介绍是否符合你的意图；
2. 是否列出了应当复用或修改的已有仓库；
3. 本次是在本地试用，还是要操作公开 GitHub 仓库。

确认无误后，可以回复“确认执行这份计划”。如果需要修改，直接说明，AI 会重新生成计划。执行完后查看 `result.md`：应显示 completed，并核对是否标为模拟确认。程序检查通过之后，还需要你检查内容是否合用。

## 维护者首次安装

需要 Python 3.10 或以上、Git，以及 PyYAML 6。下载本项目后在仓库根目录安装依赖：

```bash
python -m pip install -r quanttide-asset/loops/second-brain-init/requirements.txt
python quanttide-asset/asset-entry.py check
python quanttide-asset/skills/second-brain-init/scripts/validate_outputs.py
```

可以直接在当前项目使用。也可以复制完整技能到支持 `SKILL.md` 的宿主技能目录；以下命令复制到一个明确指定的新目录，不覆盖已有安装：

```bash
python quanttide-asset/loops/second-brain-init/install.py --destination ../my-ai-project/.agents/skills/second-brain-init
```

复制后应让宿主重新加载技能。技能副本自带执行器、规则和规格，可脱离源项目运行；宿主需要能够执行 Python 和 Git。复制文件不等于已在某个聊天产品中安装成功，具体加载方式由宿主决定。

## 维护者本地跑通一轮

以下命令从仓库根目录执行。若系统使用 `python3`，将 `python` 替换为 `python3`。两个演示目录必须是不同目录，不能相互包含；如果已经用过 `second-brain-demo-run`，请换新的记录目录。

生成计划：

```bash
python quanttide-asset/asset-entry.py run plan --config quanttide-asset/loops/second-brain-init/configs/new-domain.yaml --workspace ../second-brain-demo-work --run-dir ../second-brain-demo-run
```

打开 `../second-brain-demo-run/execution-plan.md` 审阅。在终端确认时，程序会再次显示计划，要求输入完整计划编号；直接回车会取消：

```bash
python quanttide-asset/asset-entry.py run approve --run-dir ../second-brain-demo-run --reviewer "你的名字"
python quanttide-asset/asset-entry.py run apply --run-dir ../second-brain-demo-run
python quanttide-asset/asset-entry.py run verify --run-dir ../second-brain-demo-run
```

查看 `../second-brain-demo-work/repositories/quanttide-sample/README.md` 即可看到生成的领域首页。本地“推送”实际推向同一演示工作区里的 `remotes`，不会写入 GitHub。

| 记录文件 | 用途 |
|---|---|
| `execution-plan.md` | 人工阅读的计划 |
| `execution-plan.json` | 具体配置、原有规则、操作列表和版本信息 |
| `approval-record.json` | 谁确认了哪份计划，是否为模拟确认 |
| `execution-log.json` | 已完成步骤、时间和检查点 |
| `verification-report.json` | 每项实际检查的结果及验证范围 |
| `result.md` | 最后结果与失败原因 |

## 已有资料与其他场景

告诉 AI 你的目标即可，由 AI 根据 [请求配置参考](../../skills/second-brain-init/references/request-schema.md) 填写 YAML：

| 目标 | 程序场景 | 主要输入与范围 |
|---|---|---|
| 新建领域 | new-domain | 名称、介绍、边界、相邻分工 |
| 补全已有领域 | complete-existing | 已有仓库及领域信息；保留人工正文和原许可证 |
| 追加资产 | append-assets | 已有领域与要追加的资产类型 |
| 挂载产品 | mount-product | 领域仓库、产品仓库及 apps 下路径 |
| 聚合同类资产 | aggregate-container | 资产类型和调查得到的挂载清单 |
| 修正英文后缀 | rename | 配套资产新旧完整仓库名及所有引用仓库；暂不自动修改领域简称或目录布局 |
| 发布版本 | release | 一个目标仓库、版本号、发布说明 |

一次有多个目标时，依赖顺序由 AI 明确后逐份规划。聚合与更名不会自动穷举整个 GitHub 组织；AI 要先调查并列全范围。发布只处理指定仓库的 CHANGELOG、标签和 GitHub Release，不包含官网建设、应用部署或其他父仓库指针更新。

## 操作真实 GitHub 前

维护者需要有目标组织的写入权限，安装并登录 GitHub CLI，同时让 Git 使用已授权账号。令牌交给账号登录工具管理，不写进请求文件。先调查真实仓库规则，再创建全新的记录目录，把 plan 命令增加 `--provider github --organization quanttide`；后续审阅与执行步骤相同。

GitHub 模式会创建公开仓库，并可执行推送、更名和发布。该模式的实际账号联调本轮尚未完成，应先在明确授权的测试组织验收。真实根仓库必须已经存在，本地演示的自动根仓库只用于测试。

资产云原生 CLI 的 `run` 目前是归档流程，不能把本插件当作它已支持的通用插件直接运行。请使用这里提供的 `asset-entry.py` 接入入口，具体说明见 [资产云接入说明](INTEGRATION.md)。

## 出错时怎么做

| 看到的情况 | 接下来做什么 |
|---|---|
| 缺少字段、名称不合规 | 补充请求配置后，用新的记录目录生成计划 |
| 尚未确认 | 阅读这份计划并由审阅者确认 |
| 已有未提交修改、远端不同步 | 让维护者处理现有工作，再重新规划 |
| 计划、程序或规格变化 | 重新生成计划，旧确认不再适用 |
| 操作中断且检查点未变 | 排除临时问题，再对同一记录目录运行 apply |
| 检查点后已有部分写入或执行锁残留 | 保留日志，先检查仓库状态和运行进程；不要盲目删锁或重复创建 |
| 挂载目录有人工文件 | 保留原文件，人工决定移动或合并方案，再规划 |

程序按步骤保存检查点，遇错暂停；多仓库操作不是一个整体事务，不会自动删除已创建仓库或回滚已经推送的提交。
