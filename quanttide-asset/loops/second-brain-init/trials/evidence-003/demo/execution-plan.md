# 第二大脑执行计划

状态：等待人工确认。

计划编号：3bbaa5a37e5a772d85b552ce446db201f88a478b91d586cfbac256a8a73881fb

执行环境：local

## 已确认的输入

```yaml
schema_version: 1
scenario: new-domain
domain:
  chinese_name: 示例工程
  english_name: sample-engineering
  short_name: sample
  overview: 用于验证第二大脑创建流程的本地示例领域。
  boundary: 包含示例资料的组织、验证与维护。
  neighbors: 正式生产领域沿用各自知识仓库；这里仅记录演示材料。
root_repo: quanttide
register_root: true
```

## 操作清单

- 001 ensure-repo：qtcloud-sample。
- 002 finish：qtcloud-sample。
- 003 ensure-repo：quanttide-sample-toolkit。
- 004 finish：quanttide-sample-toolkit。
- 005 ensure-repo：quanttide-laboratory-of-sample-engineering。
- 006 finish：quanttide-laboratory-of-sample-engineering。
- 007 ensure-repo：quanttide-context-of-sample-engineering。
- 008 finish：quanttide-context-of-sample-engineering。
- 009 ensure-repo：quanttide-journal-of-sample-engineering。
- 010 finish：quanttide-journal-of-sample-engineering。
- 011 ensure-repo：quanttide-intention-of-sample-engineering。
- 012 finish：quanttide-intention-of-sample-engineering。
- 013 ensure-repo：quanttide-sample。
- 014 mount：quanttide-sample → apps/qtcloud-sample。
- 015 mount：quanttide-sample → packages/quanttide-sample-toolkit。
- 016 mount：quanttide-sample → examples/default。
- 017 mount：quanttide-sample → data/context。
- 018 mount：quanttide-sample → data/journal。
- 019 mount：quanttide-sample → data/intention。
- 020 domain-docs：quanttide-sample。
- 021 catalog：quanttide-sample。
- 022 finish：quanttide-sample。
- 023 ensure-repo：quanttide。
- 024 mount：quanttide → domains/quanttide-sample。
- 025 catalog：quanttide。
- 026 root-index：quanttide。
- 027 finish：quanttide。

## 执行与审阅

本计划包含建仓、文件写入、提交与推送。local 模式仅操作指定工作区内的本地仓库；github 模式将操作公开 GitHub 仓库。

请检查 execution-plan.json 的 inspection 中的原有契约及 config 中的名称、边界和挂载目标。确认后运行 approve，修改输入则新建一份计划。
