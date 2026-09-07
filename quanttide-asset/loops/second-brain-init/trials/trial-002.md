# 第二大脑创建配置 0.2.0 测试记录

## 本轮结论

2026-09-06 实际运行本地 Git 测试。最终 17 项自动化测试全部通过；通过资产登记入口完成一轮新建演示，27 项操作完成、16 项检查通过。演示产生 7 个领域与配套仓库，加上 1 个测试根仓库，8 个工作副本与各自本地 bare 远端 HEAD 一致且工作区干净。

确认由自动化脚本模拟，明确记录为 simulated。没有真实非技术用户参与本轮验收，没有创建或修改真实 GitHub 仓库，没有上线资产云网页功能。

## 实际环境与证据

| 项目 | 实际值 |
|---|---|
| 时间 | 2026-09-06 14:14:48—14:15:24 UTC |
| 操作系统 | Linux 6.18.35，x86_64 |
| Python | 3.12.13 |
| PyYAML | 6.0.3 |
| Git | 2.51.1 |
| 执行方式 | Python 子进程调用真实 Git，provider 为 local |
| 最终测试用时 | 17 项测试 31.619 秒 |

Linux 是本次运行测试的实际系统。环境信息由程序读取并保存，见 [environment.json](evidence-003/environment.json)，不是对用户电脑系统的假设。

最终证据包含：

- [summary.json](evidence-003/summary.json)：时间、每条命令、退出码和验证范围；
- [unit-tests.stderr.txt](evidence-003/unit-tests.stderr.txt)：17 项测试的原始输出；
- [result.md](evidence-003/demo/result.md)：完整演示的实际结果；
- [verification-report.json](evidence-003/demo/verification-report.json)：16 项逐项检查；
- [approval-record.json](evidence-003/demo/approval-record.json)：明确标注模拟确认；
- [execution-log.json](evidence-003/demo/execution-log.json)：27 项实际操作与最后检查点；
- [final-inventory.json](evidence-003/final-inventory.json)：8 个仓库的本地与远端提交、生成文档和子模块配置快照；
- [source-sha256.json](evidence-003/source-sha256.json)：本轮执行器、规格、技能、接入入口和测试源码指纹。

演示使用的临时仓库在测试结束后自动清理；这些是历史证据，不能对归档计划直接继续 apply。重现请使用下面的脚本生成新工作区与计划。

## 自动化覆盖

| 测试组 | 实际验证内容 | 结果 |
|---|---|---|
| 新建 | 7 个最小仓库、6 个领域子模块、根仓库登记、工作区与远端一致 | 通过 |
| 补全 | 保留人工正文、人工概述和已有许可证，不重复概述标题 | 通过 |
| 追加 | 将空坐标替换为实际 report 子模块 | 通过 |
| 产品与聚合 | 挂载已有产品，建立 journal 容器并注册根仓库 | 通过 |
| 更名 | 配套资产改英文后缀，更新领域和根仓库的引用及指针 | 通过 |
| 发布 | 实际更新 CHANGELOG，创建并推送版本标签到本地远端 | 通过 |
| 确认与输入 | 无确认、计划内容变化、路径越界、缺少必填输入时拒绝执行 | 通过 |
| 状态保护 | 未提交修改、批准后漂移、挂载目录有人工内容时暂停并保留内容 | 通过 |
| 中断与恢复 | 第 005 项操作前注入故障，保留前 4 项；恢复不重复已完成步骤 | 通过 |
| 重复执行 | 新计划重复执行不制造多余提交 | 通过 |
| 并发保护 | 已有工作区执行锁时另一轮不能写入，也不移除对方的锁 | 通过 |
| 便携性 | 技能复制到其他目录后独立生成计划并完成包校验 | 通过 |
| 资产接入 | 加载 6 项登记路径，调用实际入口生成计划，另完成全流程演示 | 通过 |

17 是独立测试方法数量；表格按目标合并展示。这里“远端”指工作区内真实的本地 bare Git 仓库，未使用 GitHub 网络服务。

## 资产云原生 CLI

前一轮从 `qtcloud-asset@519b4e01c5f7c35f83c2311d093ac4d19ae6f338` 实际编译 CLI，运行 config 返回 6 个登记资产、1 个 second-brain-init v0.2.0 技能；validate --json 对扫描到的 5 个一级目录全部通过。两个数字分别表示登记条目与实际一级目录，统计口径不同。

该观察依据实际工具输出转录至 [native-prior-observation.json](native-prior-observation.json)，不冒充新运行生成的原始日志。最终归档时临时可执行文件已清理，未能重新运行原生 CLI；原生独立 scan 输出与缺失分类反例未完成，最终脚本如实将 native 标为 not-tested。

完整接入事实和原生 run 的归档限制见 [INTEGRATION.md](../INTEGRATION.md)。

## 发现的问题与处理

| 问题 | 处理与最终状态 |
|---|---|
| 0.1.0 仅能生成计划，不能执行完整流程 | 0.2.0 已提供实际执行、确认、恢复和验证；旧记录明确标为历史预演 |
| 重复执行产生不必要的根索引变化 | 统一文档管理区块，提交数量不变测试通过 |
| 追加子模块时空坐标已有占位文件 | 只替换纯占位坐标；人工内容一律保留并暂停 |
| 独立试用发现旧包校验依赖源项目外部文件 | 改为包内校验，复制独立执行测试通过 |
| 试用结果报告未标注模拟确认 | result、执行日志和验证报告均补充标记，最终演示已核实 |
| 同一工作区可能被不同运行目录同时操作 | 增加工作区锁，阻止第二轮写入 |
| 归档脚本指定的 CLI 二进制已不存在 | 首次归档明确失败，保留 evidence-002；最终 evidence-003 成功完成本地部分，native 不计通过 |

[evidence-002/summary.json](evidence-002/summary.json) 保留了失败原因：其 17 项测试和演示本身通过，但随后找不到 `/tmp/second-brain-asset-cli-build/debug/qtcloud-asset`，因此整体状态为 failed。没有删除失败记录，也没有把它改写成成功。

曾由独立 AI 在早期副本进行正向试用，发现上述便携校验和报告标记问题。修订后的独立复验因额度限制未执行；最终证据来自当前环境自动化复验。独立 AI 试用不等于真实非技术用户验收。

## 如何重现

安装依赖后，在项目根目录运行，输出目录必须是尚不存在的新目录：

```bash
python quanttide-asset/loops/second-brain-init/tests/run_acceptance.py --output ../second-brain-test-evidence
```

如果维护者已有编译完成的资产云 CLI，可加入 `--native-cli /绝对路径/qtcloud-asset`。脚本还会运行原生配置读取、扫描、验证及缺失分类反例；必须以实际生成的结果为准。

只运行自动化测试：

```bash
python -m unittest discover -s quanttide-asset/loops/second-brain-init/tests -p test_implementation.py -v
```

## 尚待实际验收

真实 GitHub 组织权限、HTTPS Git 登录、建仓、更名和 GitHub Release 均未联调；Windows 和 macOS 未测试。专业领域边界和原始资料适用性仍需人工审阅。多仓库写入非事务式，操作中途发生部分写入时可能需要人工处理后重新规划。

用户验收时，可按使用说明发起一个本地示例，检查计划是否看得懂、名称和范围是否正确、结果是否能找到，并记录实际体验及问题。完成这一轮后再决定是否在授权的 GitHub 测试组织联调。
