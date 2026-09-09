# 量潮智能体工程档案

本仓库是**跨 Agent 系统配置层**。它集中管理各个 AI 编程工具（Zed、OpenCode、Hermes）的系统级规则、命令、插件，目标是一处维护、多机复用。


## 第二大脑创建工具（本地测试通过版）

直接下载：[完整试用版 ZIP](https://github.com/BlackCat205/quanttide-profile-of-agent-engineering/archive/refs/heads/second-brain-ui-0.8.1.zip)。解压后先打开 START_HERE.md；Windows 用户双击首次配置.bat，再双击启动向导.bat。

本分支提供中文本机向导，入口见 [快速上手](START_HERE.md)。UI 0.8.1 将 GitHub API 用于身份与版本核验，仅在克隆、推送等必要传输时使用 Git 网络；可核对并接续 0.8.0 留下的本地阶段凭证。真实 Windows 完整创建及组织创建验收仍待完成。资产云按 `.quanttide` 契约登记接入，不要求额外在线接口。详见 [提交评审说明](quanttide-asset/loops/second-brain-init/提交评审说明.md)。

## 目录结构

仓库按**领域**为一级文件夹组织，未归入领域的通用内容存于 `default/`：

```
profile/
├── AGENTS.md          # 本文件
├── README.md          # 仓库定位与目录说明
├── default/           # 未分类的通用内容
│   ├── agents/        # 各 Agent 系统配置
│   │   ├── zed/               # → ~/.config/zed/
│   │   ├── opencode/          # → ~/.config/opencode/
│   │   ├── hermes/            # → ~/.hermes/
│   │   └── dsh/               # → DeepSeek Harness
│   ├── loops/         # 从实践日志提取的循环范式
│   │   ├── README.md
│   │   ├── devops-code/
│   │   └── devops-plan/
│   └── skills/        # 可安装技能（SKILL.md）
│       └── docs-format/
└── <domain>/          # 领域一级文件夹
    └── contexts/      # 该领域从实践对话提取的场景上下文
        └── README.md
```

## 维护规范

1. **以实际配置为准** — 本仓库的内容从机器上工作配置采集，而不是凭空设计
2. **cp 即用** — 文件放到目标路径就能恢复配置，不做变量替换或格式转换

本版新增中断阶段记录、下载残留隔离、推送响应丢失核对及旧版初始仓库接续。见 [断网后如何继续](quanttide-asset/loops/second-brain-init/断网恢复说明.md)。
