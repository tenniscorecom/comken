@echo off
setlocal
rem 新しいプロジェクトのフォルダ一式を作ります。
rem 作成先は、この bat があるフォルダの1つ上（comken と並ぶ場所）です。

rem 共有フォルダ（\\サーバー名\...）から起動されても動くよう pushd を使う（cd は UNC 不可）
pushd "%~dp0" || (
  echo [エラー] このフォルダを開けませんでした: %~dp0
  pause
  exit /b 1
)

where python >nul 2>&1 || (
  echo [エラー] Python が見つかりません。
  echo   このパソコンに Python が入っているか、管理者に確認してください。
  popd
  pause
  exit /b 1
)

set /p "PROJECT_NAME=プロジェクト名を入力してください: "
if not defined PROJECT_NAME (
  echo.
  echo [中止] プロジェクト名が入力されなかったので、何も作りませんでした。
  popd
  pause
  exit /b 1
)

python new_project.py "%PROJECT_NAME%" --into ".."
set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [失敗] プロジェクトを作れませんでした（終了コード %EXIT_CODE%）。
  echo   同じ名前のフォルダが既にある場合は、別の名前で試してください。
)
pause

endlocal & exit /b %EXIT_CODE%
