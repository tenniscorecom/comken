@echo off
setlocal
rem ============================================================
rem  comken を BO 用の共有フォルダへ配置します。
rem  バージョンは上げません。先に comken\__init__.py の
rem  __version__ を上げてから実行してください。
rem ============================================================

cd /d "%~dp0"

set "DEPLOY_TARGET=%~1"
if not defined DEPLOY_TARGET set /p "DEPLOY_TARGET=配置先のフォルダ: "

if not defined DEPLOY_TARGET (
  echo [!] 配置先が指定されていません。
  pause
  exit /b 1
)

python deploy.py "%DEPLOY_TARGET%"

if errorlevel 1 (
  echo.
  echo [!] 配置に失敗しました。上のメッセージを確認してください。
  echo     前に入っていた版はそのまま残っています。
)

pause
endlocal
