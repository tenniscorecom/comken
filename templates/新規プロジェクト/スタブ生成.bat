@echo off
setlocal
rem config.ini から補完用スタブ（typings/comken/）を作り直します。
rem 普段は main.py を1回動かせば自動で作られるので、必須ではありません。

set "COMKEN_ROOT=\\server\share\tools\comken"
set "PYTHONPATH=%COMKEN_ROOT%;%PYTHONPATH%"

rem 共有フォルダ（\\サーバー名\...）から起動されても動くよう pushd を使う（cd は UNC 不可）
pushd "%~dp0" || (
  echo [エラー] このフォルダを開けませんでした: %~dp0
  pause
  exit /b 1
)

if not exist "%COMKEN_ROOT%\comken\__init__.py" (
  echo [エラー] 共通ライブラリ comken が見つかりません。
  echo     さがした場所: %COMKEN_ROOT%
  echo   共有サーバーにつながっているか、COMKEN_ROOT が正しいかを確認してください。
  popd
  pause
  exit /b 1
)

python -m comken.config
set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [失敗] スタブを作れませんでした（終了コード %EXIT_CODE%）。
  echo   config.ini がまだ無い場合は、先に 実行.bat を1回動かしてください。
  pause
) else (
  echo 補完用スタブを作り直しました。VS Code を開き直すと反映されます。
)

endlocal & exit /b %EXIT_CODE%
