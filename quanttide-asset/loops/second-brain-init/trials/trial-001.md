# 第二大脑初始化插件历史预演记录

> 本文对应历史提交 `9914930` 的 0.1.0 计划生成器，保留当时记录。没有执行建仓、子模块提交或远端推送；文中的旧命令不适用于 0.2.0。当前实际执行证据见 [trial-002.md](trial-002.md)。

## 测试信息

- 日期：2026-09-04；
- 环境：Linux、Python 3.12、PyYAML 6.0.3；
- 插件版本：0.1.0；
- 测试模式：本地 `dry-run`，未连接或修改量潮 GitHub 组织；
- 原始语境版本：`quanttide-profile-of-agent-engineering@2b5666c`；
- 资产章程版本：`quanttide-bylaw-of-asset-management@0301294`。

## 测试目标

验证插件能把真实对话中的“创建领域第二大脑 quanttide-secret”转换为可审查计划，正确列出七个公开仓库，并在远程操作前停在人工确认点。

## 测试输入

```text
请求：创建领域第二大脑 quanttide-secret
中文名：密码管理
英文名：secret-management
领域短名：secret
```

## 执行命令

```bash
python quanttide-asset/loops/second-brain-init/implementation.py \
  --request "创建领域第二大脑 quanttide-secret" \
  --chinese-name "密码管理" \
  --english-name secret-management \
  --short-name secret \
  --output-dir <临时目录>

python quanttide-asset/loops/second-brain-init/implementation.py \
  --check <临时目录>/execution-plan.json

python quanttide-asset/skills/second-brain-init/scripts/validate_outputs.py \
  --plan <临时目录>/execution-plan.json
```

## 测试结果

- 单元测试：9 项通过，0 项失败；
- Skill Creator 结构校验：通过；
- 插件包校验：通过；
- 执行计划校验：通过；
- 场景识别结果：`new-domain`；
- 计划状态：`ready-for-confirmation`；
- 仓库数量：7；
- 操作阶段数量：7；
- 默认模式：`dry-run`；
- 人工确认：需要，尚未授予；
- 远程写操作：0 项实际执行。

计划包含领域仓库、应用云、工具集、实验室、Context、Journal 和 Intention。远程创建与推送均标记为需要确认，计划生成器没有执行任何命令。

## 测试中发现的问题

第一次单元测试对简称推断的预期不正确。请求中已经包含 `quanttide-security` 时，插件会自动得到简称 `security`，因此不应再次向用户索取简称。测试预期已修正。

复查时发现，挂载、补全等变体场景缺少必填输入时仍可能生成后续写操作。实现已调整为：存在未决输入或配置错误时，只保留只读调查步骤。新增回归测试后通过。

## 未验证项

- 未创建或修改真实 GitHub 仓库；
- 未验证 GitHub 组织权限和 `gh` 登录状态；
- 未执行子模块分层提交和远端推送；
- 未修改资产云 `.quanttide/asset/contract.yaml` 进行正式登记；
- 未验证生产发布流程。

以上为当时未验证事项。0.2.0 已在本次获准的实现范围内增加本地登记文件并执行本地 Git 测试；真实 GitHub 联调另行记录。

## 结论

本轮本地试运行通过。插件已经具备可安装 Skill、七类场景路由、可运行计划生成器、确认门禁、非技术使用说明和自动化校验。当前结论只证明预演链路可用，不代表真实远程创建和发布已经通过。
