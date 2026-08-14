@echo off
setlocal
rem 認証情報（client_secret・パスワード・トークン）の登録画面を開きます。
rem ダブルクリックで起動してください。入れた値は Windows の DPAPI で暗号化して保存され、
rem 登録した Windows ユーザー・その PC でしか読めません。
rem comken を別の場所へ移したときは、ここと 実行.bat・.vscode\settings.json を直してください。

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

python -m comken.toolbox.credentials gui
set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [失敗] 登録画面を開けませんでした（終了コード %EXIT_CODE%）。
  echo   エラーの内容は画面の上のほうに出ています。
  pause
)

endlocal & exit /b %EXIT_CODE%
