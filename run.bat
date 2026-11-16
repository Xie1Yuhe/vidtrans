@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem ---------- 找 Python ----------
set "PY="
if exist "%~dp0.python\python.exe" set "PY=%~dp0.python\python.exe"
if not defined PY (
  for %%P in (python.exe) do if not defined PY set "PY=%%~$PATH:P"
)

if not defined PY (
  echo.
  echo   [错误] 没有找到 Python。
  echo   请安装 Python 3.10+，安装时勾选 "Add Python to PATH"。
  echo.
  pause
  exit /b 1
)

rem ---------- 验证可用（排除 Windows 应用商店的占位程序）----------
"%PY%" -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   [错误] 找到的 python 不能运行：%PY%
  echo   如果你装的是微软商店版，请在"设置-应用执行别名"里关掉 python，
  echo   或直接把本文件里的 PY 改成真实 python.exe 的完整路径。
  echo.
  pause
  exit /b 1
)

rem ---------- 依赖 ----------
"%PY%" -c "import faster_whisper" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   第一次运行，正在安装依赖 faster-whisper / numpy ...
  echo.
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo   依赖安装失败。请手动执行：
    echo     "%PY%" -m pip install -r requirements.txt
    pause
    exit /b 1
  )
)

echo.
echo   正在启动 vidtrans ... 浏览器会自动打开 http://127.0.0.1:8765/
echo   关闭本窗口即停止服务。
echo.
"%PY%" app.py serve
pause
