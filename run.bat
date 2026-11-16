@echo off
setlocal
cd /d "%~dp0"

echo.
echo   vidtrans launcher
echo   -----------------
set "PY="

rem ---------- 1. explicit env var ----------
if defined VIDTRANS_PYTHON call :try "%VIDTRANS_PYTHON%"

rem ---------- 2. portable python shipped next to this file ----------
if not defined PY if exist "%~dp0.python\python.exe" call :try "%~dp0.python\python.exe"

rem ---------- 3. python on PATH ----------
if not defined PY for /f "usebackq delims=" %%P in (`where python 2^>nul`) do if not defined PY call :try "%%P"

rem ---------- 4. py launcher ----------
if not defined PY for /f "usebackq delims=" %%P in (`py -3 -c "import sys;print(sys.executable)" 2^>nul`) do if not defined PY call :try "%%P"

rem ---------- 5. common install locations ----------
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if not defined PY call :try "%%D\python.exe"
if not defined PY for /d %%D in ("C:\Python3*") do if not defined PY call :try "%%D\python.exe"
if not defined PY for /d %%D in ("D:\Python3*") do if not defined PY call :try "%%D\python.exe"
if not defined PY for /d %%D in ("C:\Program Files\Python3*") do if not defined PY call :try "%%D\python.exe"

if not defined PY goto :no_python

echo   python : %PY%

rem ---------- keep the model cache next to the tool ----------
if not defined HF_HOME set "HF_HOME=%~dp0.hf"

rem ---------- dependencies ----------
"%PY%" -c "import faster_whisper" >nul 2>&1
if not errorlevel 1 goto :launch

echo.
echo   First run: installing dependencies (faster-whisper, numpy) ...
echo.
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :pip_fail

:launch
echo   Starting vidtrans ...
echo   Browser will open http://127.0.0.1:8765/
echo   Close this window to stop the server.
echo.
"%PY%" app.py serve
goto :end

:try
rem only accept a python that actually runs (skips the Microsoft Store stub)
if "%~1"=="" goto :eof
"%~1" -c "import sys" >nul 2>&1
if errorlevel 1 goto :eof
set "PY=%~1"
goto :eof

:no_python
echo.
echo   [ERROR] No working Python found.
echo.
echo   Fix it in one of these ways:
echo     1) Install Python 3.10+ from https://www.python.org/downloads/
echo        and tick "Add Python to PATH" during setup.
echo     2) If you installed from the Microsoft Store, disable its
echo        "App execution aliases" for python first.
echo     3) Or unpack a portable Python into the folder ".python"
echo        next to this file (so that .python\python.exe exists).
echo     4) Or set the environment variable VIDTRANS_PYTHON to the
echo        full path of a python.exe.
echo.
pause
exit /b 1

:pip_fail
echo.
echo   [ERROR] Failed to install dependencies. Run this manually:
echo     "%PY%" -m pip install -r requirements.txt
echo.
pause
exit /b 1

:end
pause
