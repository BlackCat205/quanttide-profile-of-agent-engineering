# 第二大脑初始化契约规则

## 事实源

规则以以下公开材料为准：

- `quanttide-bylaw-of-asset-management/contract/public-second-brain.md`；
- `quanttide-profile-of-agent-engineering/quanttide-asset/contexts/second-brain-init.md`；
- 目标仓库自己的 `AGENTS.md` 与 `.quanttide/` 契约。

插件保留来源地址和提交版本，不复制整份章程。规则冲突时列明冲突，依据用户既有授权与目标仓库规则处理。不能声称程序会自动解释所有契约文字或实时追踪最新章程；规格升级需要维护者审阅。

## 双轴结构

- 领域第二大脑命名为 `quanttide-{领域短名}`；
- 资产第二大脑命名为 `quanttide-{资产类型}`；
- 双轴交点命名为 `quanttide-{资产类型}-of-{领域英文名}`；
- 产品平台使用 `qt{产品名}`，云平台使用 `qtcloud-{产品名}`；
- 工具集使用 `quanttide-{领域短名}-toolkit`；
- 实验室使用 `quanttide-laboratory-of-{领域英文名}`。

## 命名规则

- 中文名优先使用四字结构；
- 以人为主要对象的领域优先采用「管理」；
- 以机器、系统或工程对象为主的领域优先采用「工程」；
- 英文名使用单数形式，并根据领域性质选择 `-management` 或 `-engineering`；
- 英文名超过八个字母时才考虑缩写；
- 优先复用体系内已经存在的简称和命名风格；
- 不确定时生成候选方案，等待用户确认。

## 领域目录

领域仓库使用以下标准坐标：

| 顶级目录 | 标准坐标 |
|---|---|
| apps | 应用云与已有产品 |
| packages | 工具集 |
| examples | default 实验室 |
| data | context、archive、report、library、history、journal、profile、brochure、roadmap、insight、intention |
| docs | bylaw、specification、handbook、gallery、tutorial、essay |

目录是资产坐标，不代表初始化时必须创建二十个独立仓库。只有已经存在或本次明确创建的资产才注册为子模块。

## 文档与许可证

- 领域 README 包含概述、领域边界、相邻领域分工、子模块现状与规划；
- 用户可见变更同步更新 CHANGELOG；
- 全新领域仓库默认采用 CC BY 4.0；
- 资产聚合容器参照同类容器，当前先例采用 Apache 2.0；
- 成熟应用保留原许可证；
- Markdown 最多三级标题，代码块标注语言，文件名小写，目录名使用复数形式。

## Git 与安全

- 动手前检查远端同名仓库和本地工作区；
- 仅暂存本任务的具体路径，禁止 `git add -A`；
- 按子仓库、领域仓库、根仓库顺序提交；
- 推送被拒时先调查远端变化，再决定是否 `git pull --rebase`；
- 要写入的工作仓库必须在明确分支上；父仓库内只读挂载副本可保持 detached HEAD，以准确记录子模块提交；
- 创建、改名、推送、修改契约和生产发布都需要明确授权；
- 凭证、个人信息和未脱敏内部材料不得进入公开仓库或执行日志。
