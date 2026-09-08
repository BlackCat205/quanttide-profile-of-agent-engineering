# 第二大脑工具 0.5.0 测试记录

## 范围与结论

日期：2026-09-08。UI 0.5.0，执行器 0.3.0。Linux、Python 3.12、Git 与 Chrome Headless 151.0.7922.34；精确环境和源文件 SHA256 见 [范围声明](ui-tests-050/source-and-scope.json)。

43 项 Python 自动化测试通过，耗时 236.711 秒；46 项本地流程浏览器检查及 11 项账号界面检查通过。测试记录真实本地提交、推送、子模块及中断恢复，但 GitHub 接口由测试替身提供。没有实际创建 GitHub 测试仓库，没有完成真实浏览器账号授权，也没有 Windows 真人或公司资产云宿主验收。

## 证据

- [Python 测试日志](ui-tests-050/python-tests.txt)：10 项 GitHub 相关测试、17 项原有执行器测试、8 项可靠性测试、8 项 UI 测试。
- [本地浏览器结果](ui-tests-050/browser-result.json)：命名、方案、确认、真实本地 Git 创建、逐步状态、报告、连续创建与历史记录。
- [账号浏览器结果](ui-tests-050/account-browser-result.json)：模拟官方授权响应、取消等待、大小写账号、自定义总入口、保留创建位置、手机布局。
- [安装包启动检查](ui-tests-050/package-check.json)：打包产物包含新增登录模块，解压后在 Linux 启动成功；检查 Windows bat 换行字节，没有在 Linux 执行 Windows bat。
- [发现和修复的问题](ui-tests-050/issues-resolved.md)。

个人账号流程测试通过模拟 GitHub REST 和真实本地 bare 远端，验证先创建 8 个仓库、再创建 7 个并更新同一根仓库，两领域都保留；再用相同名称时停止。此测试不能替代真实 GitHub 分支规则、权限、网络或 Windows 凭证存储的验证。

## 如何复现

在仓库根目录运行：

```bash
python -m unittest discover -s quanttide-asset/loops/second-brain-init/tests -p 'test_*.py' -v
```

浏览器测试需要 Node、Playwright、可用 Chromium 和中文字体。通过 SECOND_BRAIN_BROWSER 指定浏览器路径，并为结果指定一个不存在的新目录：

```bash
node quanttide-asset/loops/second-brain-init/tests/test_ui_browser.cjs /tmp/new-ui-evidence
node quanttide-asset/loops/second-brain-init/tests/test_github_browser.cjs /tmp/new-account-evidence
```

## 下一轮真人验收

按 [Windows试用表](../Windows试用表.md) 登录本人账号，核对具体公开测试范围，创建两个不同领域，保存实际仓库链接、提交版本、报告和用户意见。若使用 Fork 入口，需另外确认原有链接和规则被保留。

真实 GitHub：待完成。Windows 独立操作：待完成。公司资产云宿主调用：待公司明确接入方式后联调。不得把上述自动化通过改写为全部上线验收通过。
