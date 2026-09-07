# 中文创建向导 0.3.0 测试记录

## 验证结果

2026-09-07，在 Linux 6.18.35、Python 3.12.13、Git 2.51.1 上完成实际测试。中文向导复用 0.2.0 执行器，没有把页面模拟动画当作 Git 执行。

- 23 项回归测试通过，耗时 356.760 秒：原有 17 项执行器测试与新增 6 项 UI/HTTP 测试。
- 补充的“最终验证失败仍可显示中文报告”测试单独通过，耗时 29.635 秒。当前测试源码共有 24 项方法；本轮证据是 23 项回归加 1 项补测，不能写成一次运行 24 项。
- Chromium 151.0.7922.34 完成 14 项浏览器检查，JavaScript 运行错误为 0。
- 实际浏览器点击产生 8 个本地仓库，完成 27 项操作、16 项底层检查，页面按 7 条人话标准汇总结果。
- 桌面 1440 像素与手机 390 像素宽度均检查了横向溢出；最终截图已人工查看，中文显示正常。

全部自动化反馈明确标注 simulated。没有真实非技术成员参与本轮 GUI 验收；没有在 Windows 系统中执行双击脚本；没有操作真实 GitHub 或部署资产云在线页面。

## 实际证据

| 内容 | 保存位置 |
|---|---|
| 23 项回归的原始输出 | [tests.stderr.txt](ui-tests-003/tests.stderr.txt) |
| 运行环境、命令与退出码 | [result.json](ui-tests-003/result.json) |
| 失败报告场景补测 | [failed-verification-test.txt](ui-tests-003/failed-verification-test.txt) |
| 最终源码指纹 | [final-source-sha256.json](ui-tests-003/final-source-sha256.json) |
| 14 项浏览器检查结果 | [browser-result.json](ui-browser-005/browser-result.json) |
| 底层实际执行日志 | [execution-log.json](ui-browser-005/execution-log.json) |
| 原始技术验证结果 | [verification-report.json](ui-browser-005/verification-report.json) |
| 中文标准与实际证据 | [ui-report.json](ui-browser-005/ui-report.json) |
| 独立的人工意见记录 | [human-acceptance.json](ui-browser-005/human-acceptance.json) |
| 实际下载的 HTML 报告 | [acceptance-export.html](ui-browser-005/acceptance-export.html) |

浏览器测试的临时工作空间仅供本次自动化使用，归档日志不是用户自己电脑的验收结果。

## 浏览器如何测试

依次点击“使用示例体验”“生成创建方案”，确认页面显示 8 个仓库与中文用途；检查生成计划时目标工作区尚未建立。填写“浏览器自动化测试”作为审阅者并勾选同意后，才点击实际创建。

执行完成后查看七条中文检查，打开领域首页并检查“相邻领域分工”正文。此时页面仍显示待本人验收，不自动填入“人工通过”。测试随后为内容和导航选择通过，为使用体验选择需要改进，并保存一条模拟意见。

实际下载的 HTML 报告保留了“模拟反馈”和“需改进”，没有把技术通过改写为全部验收通过。刷新浏览器后，运行记录及已保存意见仍然存在。另在 390 像素宽度检查表单与报告不产生横向溢出。

## HTTP 与状态保护

UI 测试实际验证：

- 无会话标识、来自其他 Origin 或错误 Host 的请求被拒绝，未创建任务；
- 缺字段、越界名称、未启用的真实 GitHub 模式被拒绝；
- 未勾选确认或计划编号不匹配时，不建立目标仓库；
- 重复点击已经完成任务的执行入口被拒绝；
- 文档只能从当前计划中的允许文件读取，不能读取其他目录或 Git 内部配置；
- 包含 HTML 标签的用户文字在页面按文本处理，导出报告进行转义；
- 产物变动后重新验证，旧验收意见失效，失败任务不能继续登记为人工通过；
- 服务重启时，不把此前 running 状态误当作仍有进程执行；
- 最后技术验证失败时，保留逐项报告和失败原因，用户不必只收到 JSON 文件名。

## 发现的问题与处理

| 问题 | 处理 |
|---|---|
| 原界面没有保存真实验收意见的独立位置 | 增加内容、导航、使用体验三项；状态独立于技术检查 |
| 最终技术检查失败时可能只有“查看 JSON”提示 | 在异常分支生成中文报告，并在页面显示实际失败原因；补测通过 |
| 自动测试首次浏览器启动遇到可执行权限丢失 | 在测试脚本中准备测试浏览器权限；保留 [首次失败记录](ui-browser-003/browser-result.json) |
| 初次截图中中文为方框 | 测试环境缺少中文字体，加入测试用 Noto CJK 字体后重新完成浏览器测试并检查截图；不向用户包捆绑测试浏览器或字体 |
| 浏览器测试关闭父启动进程后子服务可能残留 | 测试脚本按进程组清理自己的服务，不影响用户进程 |

前一轮 ui-browser-004 功能检查通过但截图缺中文字体，最终视觉证据以 ui-browser-005 为准。

## 界面截图

- [填写需求](ui-browser-005/01-create.png)
- [手机宽度](ui-browser-005/02-mobile.png)
- [审阅方案](ui-browser-005/03-review.png)
- [阅读领域首页](ui-browser-005/04-home.png)
- [中文验收与意见记录](ui-browser-005/05-acceptance.png)

截图顶部的“自动化试用模式”属于测试标记。正常启动时不启用 test-mode，不会显示该条测试提示。

## 复现与交付范围

维护者可运行：

```bash
python -m unittest discover -s quanttide-asset/loops/second-brain-init/tests -p 'test_*.py' -v
```

浏览器测试另需 Node、Playwright 与已安装的 Chromium。运行 `tests/test_ui_browser.cjs` 并传入一个新的证据目录；测试会启动专用 local 服务，自动启用 test-mode。此依赖只用于开发测试，普通用户运行向导不需要 Node 或 Playwright。

Windows 用户通过“首次配置.bat”和“启动向导.bat”使用。首次配置仍需 Python、Git 和联网安装 PyYAML；当前交付不是捆绑运行环境的免安装 EXE。Windows 实际安装与双击体验需要用户继续验证。

本界面支持新建领域。补全、聚合、更名、追加和发布等原有维护能力仍使用配置入口。资产云对接仍为契约登记与调用已登记执行器，未声明完成在线宿主页面接入。
