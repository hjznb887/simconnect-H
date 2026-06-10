@echo off
chcp 65001 >nul
setlocal

echo === simconnect-H 安装与诊断 ===
echo.

where py >nul 2>&1
if %errorlevel%==0 (
    set PY=py
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set PY=python
    ) else (
        echo [错误] 未找到 Python。请先安装 Python 3.8+ 并勾选 "Add to PATH"。
        pause
        exit /b 1
    )
)

echo 使用: %PY%
%PY% --version
echo.

set WHEEL=
for %%f in ("%~dp0..\*.whl") do set WHEEL=%%f
if not defined WHEEL (
    for %%f in ("%~dp0..\dist\simconnect_h-*.whl") do set WHEEL=%%f
)
if not defined WHEEL (
    for %%f in ("%~dp0..\dist\simconnect_H-*.whl") do set WHEEL=%%f
)
if not defined WHEEL (
    for %%f in ("%~dp0*.whl") do set WHEEL=%%f
)

if defined WHEEL (
    echo 安装库: %WHEEL%
    %PY% -m pip install --upgrade "%WHEEL%"
) else (
    echo 未找到 wheel，尝试从上级目录源码安装...
    %PY% -m pip install --upgrade "%~dp0.."
)

if errorlevel 1 (
    echo [错误] 安装失败
    pause
    exit /b 1
)

echo.
echo === 开始诊断（请先启动 MSFS 并进入飞行）===
echo.
%PY% "%~dp0diagnose_read.py"
set RC=%errorlevel%

echo.
if %RC%==0 (
    echo 诊断通过。
) else if %RC%==2 (
    echo 未收到数据，请确认 MSFS 已在飞行中。
) else (
    echo 连接失败，请确认 MSFS 已启动。
)
pause
exit /b %RC%
