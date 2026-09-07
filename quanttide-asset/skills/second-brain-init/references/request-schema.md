# 请求配置

## 通用字段

`schema_version` 固定为 1，`scenario` 必须明确选择。`target_repo` 仅写仓库名，不带组织或 URL。`root_repo` 默认为 quanttide，`register_root` 默认 true。工作区包含 repositories 和 remotes 两个子目录；GitHub 模式使用 repositories 保存工作副本。

新建、补全和追加场景的 domain 需包含 chinese_name、short_name、english_name、overview、boundary、neighbors 六个字段。命名由 AI 根据实际先例提出建议并经用户认可，程序只检查字段格式，不臆测领域语义。

## 新建领域

```yaml
schema_version: 1
scenario: new-domain
domain:
  chinese_name: 示例工程
  short_name: sample
  english_name: sample-engineering
  overview: 验证知识资产管理的示例领域。
  boundary: 包含示例资料的组织与验证。
  neighbors: 生产数据归属具体业务领域。
register_root: true
```

标准新建含领域、应用云、工具集、实验室、Context、Journal 和 Intention 七个仓库。local 模式若没有总入口，还会创建第八个根仓库作为测试环境；GitHub 模式要求总入口已经存在。

## 其他场景

以下配置都包含 `schema_version: 1`。

| 场景 | 必填输入 | 行为 |
|:--|:--|:--|
| complete-existing | target_repo、domain | 保留原 README 和许可证，追加受管理的领域说明并补缺口 |
| append-assets | target_repo、domain、assets | 按标准资产类型创建并挂载缺少的子仓库 |
| mount-product | target_repo、mounts | 挂载已经存在的产品仓库 |
| aggregate-container | asset_type、mounts | 按 default 和 domains 聚合同类型的已有资产 |
| rename | renames、reference_repos | 改名、更新给定范围内引用、刷新指针 |
| release | target_repo、version、notes | 固化 Unreleased、提交推送、创建并推送标签；GitHub 模式发布 Release |

assets 是列表，如 `[report, context, journal]`。可用类型见 `assets/specification.yaml`，支持章程的二十类资产。

mounts 是明确的挂载列表：

```yaml
schema_version: 1
scenario: mount-product
target_repo: quanttide-sample
mounts:
  - repo: qtsample
    path: apps/qtsample
```

容器使用 `scenario: aggregate-container` 和 `asset_type: journal`；mounts 中的仓库形如 `quanttide-journal-of-sample-engineering`，路径形如 `domains/sample`。程序不根据简称自动猜测不同领域的挂载名。

英文更名使用完整的配套仓库名，并列出所有引用仓库，按层级从低到高排列：

```yaml
schema_version: 1
scenario: rename
renames:
  quanttide-context-of-sample-engineering: quanttide-context-of-example-engineering
reference_repos:
  - quanttide-sample
  - quanttide
```

更名不等于允许覆盖已存在的同名仓库。目录挂载坐标保持稳定；需要改变领域简称或移动整个领域路径时，另行审阅迁移计划。

## 执行记录

- execution-plan.json 和 execution-plan.md 保存操作内容、源版本和调查结果。
- approval-record.json 保存审阅者、计划编号、时间和是否为模拟反馈。
- execution-log.json 保存已完成动作和最近成功检查点。
- verification-report.json 保存逐项验证结果。
- result.md 给出完成、暂停或失败的概要。

确认记录用于本地工作流审阅，不代替 GitHub 权限。程序不会取得或提升账号权限。调用方必须提供真实的人类反馈，自动测试的模拟反馈不得当作人工验收。
