@echo off
setlocal

set "DEPLOY_TARGET=%~1"
set "VERSION_CHANGE=%~2"

if not defined DEPLOY_TARGET (
    set /p "DEPLOY_TARGET=BO deployment folder: "
)

if not defined VERSION_CHANGE (
    echo.
    echo Version change: patch / minor / major / X.Y.Z
    set /p "VERSION_CHANGE=Choose version change: "
)

if not defined DEPLOY_TARGET (
    echo Deployment folder is required.
    pause
    exit /b 1
)

if not defined VERSION_CHANGE (
    echo Version change is required.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy_comken.ps1" ^
    -Target "%DEPLOY_TARGET%" -VersionChange "%VERSION_CHANGE%"

if errorlevel 1 (
    echo.
    echo Deployment failed. The previous BO version was preserved when possible.
    pause
    exit /b 1
)

echo.
echo Deployment completed.
pause
