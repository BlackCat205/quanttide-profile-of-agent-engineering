# 量潮资产管理

本目录保存第二大脑创建流程的原始材料与可复用配置。当前中文向导为 0.3.0，复用 0.2.0 Git 执行器。

## 从哪里开始

普通用户先阅读 [双击启动与中文向导](../START_HERE.md)。首次配置后，日常创建在浏览器中完成。

维护者可阅读 [使用说明](loops/second-brain-init/USER_GUIDE.md)。程序可以实际创建本地 Git 仓库、注册子模块、提交推送到本地远端；公开 GitHub 操作需要已授权的账号和具体计划确认。

| 内容 | 位置 | 用途 |
|---|---|---|
| 原始对话 | `sessions/second-brain-init.jsonl` | 原始导出，共 395 条记录、37 个用户回合 |
| 已整理流程 | `contexts/second-brain-init.md` | 从对话提取的命名、目录和操作规则 |
| 给 AI 的技能 | `skills/second-brain-init/` | 理解需求、讨论方案、调用程序 |
| 运行与安装资料 | `loops/second-brain-init/` | 示例配置、入口、使用说明、测试 |
| 资产登记 | `.quanttide/asset/contract.yaml` | 告诉资产云资料的位置和插件入口 |
| 接入程序 | `asset-entry.py` | 读取登记文件并调用已登记执行器 |

## 试运行

在本仓库根目录执行：

```bash
python -m pip install -r quanttide-asset/loops/second-brain-init/requirements.txt
python quanttide-asset/asset-entry.py check
python quanttide-asset/asset-entry.py run plan --config quanttide-asset/loops/second-brain-init/configs/new-domain.yaml --workspace ../second-brain-demo-work --run-dir ../second-brain-demo-run
```

这一阶段只调查并生成计划。实际执行、七类场景和问题处理见使用说明。

接入实现见 [资产云接入说明](loops/second-brain-init/INTEGRATION.md)，实际验证见 [0.2.0 测试记录](loops/second-brain-init/trials/trial-002.md)。

中文向导的浏览器与回归测试见 [0.3.0 测试记录](loops/second-brain-init/trials/trial-003.md)。
