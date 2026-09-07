@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在准备第二大脑创建工具。首次配置需要联网下载 Python 依赖。
where git >nul 2>nul
if errorlevel 1 goto missing_git
python -c "import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 (
  python -m venv .venv
  goto dependencies
)
py -3 -c "import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 goto missing_python
py -3 -m venv .venv
:dependencies
if not exist ".venv\Scripts\python.exe" goto failed
".venv\Scripts\python.exe" -m pip install -r quanttide-asset\loops\second-brain-init\requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -X utf8 quanttide-asset\asset-entry.py check >nul
if errorlevel 1 goto failed
echo 配置完成。以后双击“启动向导.bat”即可使用。
pause
exit /b 0
:missing_git
echo 未找到 Git，请从 https://git-scm.com/install/windows 安装后重新运行。
goto failed
:missing_python
echo 未找到 Python 3.10 或以上。请从 https://www.python.org/downloads/windows/ 安装后重新运行。
:failed
echo 配置尚未完成。请保留上方错误信息并联系维护者。
pause
exit /b 1
