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

rem 共有フォルダ（\\サーバー名\...）から起動されると、cd ではこのフォルダへ移動できず、
rem カレントが C:\Windows のままになって main.py が見つからない（CMD の仕様）。
rem pushd は共有フォルダに一時的なドライブ名を割り当てるので、その場合でも動く。
pushd "%~dp0"
if errorlevel 1 (
  echo.
  echo [!] このフォルダへ移動できませんでした: %~dp0
  echo     共有フォルダが切断されていないか確認してください。
  pause
  exit /b 1
)

set "PYTHONPATH=%COMKEN_ROOT%;%PYTHONPATH%"

python main.py

if errorlevel 1 (
  echo.
  echo [!] エラーで終了しました。上の赤い文字（エラー名）を docs\ERRORS.md で調べてください。
  pause
)

popd
