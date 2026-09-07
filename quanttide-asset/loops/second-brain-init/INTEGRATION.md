# 第二大脑创建插件资产云接入

## 中文入口 0.3.0

新增 `ui/app.py`，通过原有资产契约检查后调用已登记的 0.2.0 执行器。契约 params 新增 ui_entrypoint 和 ui_version，维护者可据此发现中文入口。原生 CLI 不会因此自动增加网页插件调度功能。

界面使用本机 HTTP 服务，绑定 127.0.0.1；API 验证会话标识、Host 和 Origin，不对其他网页开放跨域调用。它不是资产云在线部署。新建页面直接提供表单，维护场景仍保留配置入口。

## 接入结果

交付形态是“可复用 Skill + 专用执行器 + 资产云契约”，位于资料原所属的 `quanttide-asset` 目录。没有修改原始对话或资产管理章程，没有把此交付描述成已上线的 Studio 功能。

资产云源码核对版本为 `quanttide/qtcloud-asset@519b4e01c5f7c35f83c2311d093ac4d19ae6f338`。本轮从该源码实际编译 Rust CLI，并实际运行配置读取和结构验证。最终归档复验时临时编译程序已清理，未重新运行原生 CLI；前一轮观察与最终脚本结果分开记录。

## 为什么增加登记文件

`.quanttide/asset/contract.yaml` 登记 6 类资产和 1 个技能。通用字段保留 Context 所列的 title、type、category、audience、path、description；同时在 `metadata.path` 提供 CLI 可读取的位置，并由适配入口检查两个 path 一致。

| 登记项 | 相对于 quanttide-asset 的路径 |
|---|---|
| contexts | contexts |
| sessions | sessions |
| skills | skills/second-brain-init |
| loops | loops/second-brain-init |
| user_docs | loops/second-brain-init/USER_GUIDE.md |
| trials | loops/second-brain-init/trials |

登记仅作用于本目录；它不等于向远端服务上传这些文件。入口是 `skills/second-brain-init/scripts/engine.py`，默认动作由用户明确选为 plan；不带动作只显示帮助。

## 原生能力与适配入口

| 部分 | 本版如何使用 | 已验证范围 |
|---|---|---|
| 原生 CLI config | 读取契约、列出资产与技能 | 识别 6 个登记项、second-brain-init v0.2.0 |
| 原生 CLI scan | 可扫描当前目录 | 本轮未单独保存扫描输出 |
| 原生 CLI validate | 验证目录分类策略 | 前一轮检查 5 个一级目录全部通过；缺失分类反例未完成 |
| Python asset-entry.py | 校验登记路径，调度确定的 Python 入口 | 6 个路径检查及完整 local 执行 |
| Studio / OSS Provider | 现有云端浏览与存储能力 | 未部署、未接入真实账号，不声明网页可安装 |

原生 CLI 的 `run` 是归档工作流。它虽然读取 skills 配置，但没有按照任意 entrypoint 执行本插件的通用调度能力。因此本版用 `python quanttide-asset/asset-entry.py run ...` 加载已登记入口。不能使用 `qtcloud-asset run` 替代该命令。

CLI `validate --json` 统计的是扫描出的一级目录，不等于逐项验证 6 个登记路径；所以还需要 `asset-entry.py check`。两个检查的数量不同是统计口径不同。

## 维护与复验

循环规则的唯一内容源是技能内的 `assets/specification.yaml`；Loop 下的同名文件仅作导航，不是通用 DAG 引擎可直接执行的承诺。修改规则或执行器后，旧计划会因版本指纹不符而失效。

在资产目录中可以运行原生检查：

```bash
qtcloud-asset config
qtcloud-asset scan --json
qtcloud-asset validate --json
```

注意查看 JSON 的 failed_assets，不能只依赖 CLI 的退出码。完整复验脚本和保存证据见 [测试记录](trials/trial-002.md)。
