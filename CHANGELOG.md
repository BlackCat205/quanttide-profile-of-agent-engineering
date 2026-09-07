# CHANGELOG

## Unreleased

### 新增

- 第二大脑中文向导 0.3.0：表单、具体计划确认、真实执行进度、逐条中文检查、产物阅读、独立人工验收和 HTML 报告导出；提供 Windows 首次配置与双击启动入口

- 第二大脑创建配置 0.2.0：可确认、恢复和验证的七类 Git 操作，资产云契约与适配入口，便携安装、使用说明及真实本地测试证据

- 新增 `contexts/` 目录：场景上下文记录（与 loops 互补）
- 新增 `contexts/second-brain-init.md`：领域第二大脑初始化场景（新建领域第二大脑、聚合容器、已有仓库补全）
- 新增 `quanttide-asset/skills/second-brain-init/`：第二大脑初始化技能、契约规则和文档模板
- 新增 `quanttide-asset/loops/second-brain-init/`：七类场景计划生成器、循环配置、非技术使用说明和自动化测试
- 同步更新 README / AGENTS 目录结构

### 变更

- 扩充 `contexts/second-brain-init.md`：合并脱敏对话内容，新增「背景与体系」「对话流程总览」「格式规范与契约」「关键决策记录」章节，并强化命名惯例（命名规则、仓库命名模式、领域统一结构）
- 仓库按领域一级文件夹重构：`asset-init` 更名 `second-brain-init`，归入 `quanttide-asset/contexts/`，原始对话移至 `quanttide-asset/sessions/`；未归领域内容存 `default/`

## 0.1.0 — 2026-06-22

- 初始化智能体工程工作档案仓库
