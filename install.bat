@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ============================================
echo  BiliSimul  -  install python dependencies
echo ============================================

rem 国内默认走清华镜像；国外网络可以改成 https://pypi.org/simple
set "INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
if not "%~1"=="" set "INDEX=%~1"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] creating virtualenv .venv ...
    python -m venv .venv
    if errorlevel 1 goto :err
) else (
    echo [1/3] using existing .venv
)

echo [2/3] installing packages from %INDEX% ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check -i "%INDEX%"
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -i "%INDEX%" -r "server\requirements.txt"
if errorlevel 1 goto :err

echo [3/3] preparing config ...
if not exist "server\config.yaml" copy /Y "server\config.example.yaml" "server\config.yaml" >nul
if not exist "data" mkdir data

echo.
echo Done. Now:
echo   1) set DEEPSEEK_API_KEY=sk-xxxx     (optional, otherwise google fallback)
echo   2) start.bat
pause
exit /b 0

:err
echo.
echo Install failed. Check your network, or try: install.bat https://pypi.org/simple
pause
exit /b 1