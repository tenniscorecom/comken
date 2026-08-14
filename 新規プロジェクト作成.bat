@echo off
setlocal
rem ============================================================
rem  新しいプロジェクトのフォルダ一式を作ります。
rem  ダブルクリックして、プロジェクト名を入力してください。
rem
rem  作成先は、この bat があるフォルダの1つ上（comken と並ぶ場所）です。
rem  別の場所に作りたい場合は、下の CREATE_INTO を書き換えてください。
rem ============================================================

cd /d "%~dp0"

set "CREATE_INTO=.."

set "PROJECT_NAME="
set /p "PROJECT_NAME=プロジェクト名を入力してください: "

if "%PROJECT_NAME%"=="" (
  echo.
  echo [!] プロジェクト名が入力されていません。
  pause
  exit /b 1
)

python new_project.py "%PROJECT_NAME%" --into "%CREATE_INTO%"

if errorlevel 1 (
  echo.
  echo [!] 作成に失敗しました。上のメッセージを確認してください。
)

pause
endlocal
