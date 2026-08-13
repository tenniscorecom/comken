@echo off
chcp 65001 >nul
rem ============================================================
rem  このツールの起動用。ダブルクリックで main.py を実行します。
rem
rem  下の COMKEN_ROOT は作成時に入っているので、通常は触らなくてよい。
rem  comken を別の場所へ移したときだけ、ここと .vscode\settings.json の両方を直す。
rem  （PC の環境変数は変更しません。この bat の実行中だけ PYTHONPATH を設定します）
rem ============================================================

set "COMKEN_ROOT=\\server\share\tools\comken"

cd /d "%~dp0"
set "PYTHONPATH=%COMKEN_ROOT%;%PYTHONPATH%"

python main.py

if errorlevel 1 (
  echo.
  echo [!] エラーで終了しました。上の赤い文字（エラー名）を docs\ERRORS.md で調べてください。
  pause
)
