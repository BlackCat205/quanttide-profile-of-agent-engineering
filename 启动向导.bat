@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -X utf8 launch.py
) else (
  echo 请先双击“首次配置.bat”，完成一次性环境准备。
)
echo.
echo 窗口服务已结束。若浏览器未打开，请查看上方提示。
pause
