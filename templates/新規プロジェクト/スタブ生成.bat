@echo off
setlocal
rem config.ini から補完用スタブ（typings/comken/）を作り直します。
rem 普段は main.py を1回動かせば自動で作られるので、必須ではありません。

rem comken の場所。PC に恒久登録していない場合だけ、ここが使われる
set "COMKEN_ROOT=\\server\share\tools\comken"

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

rem すでに PYTHONPATH が通っていれば、そのまま動かす（恒久登録してある場合）
python -c "import comken" >nul 2>&1
if not errorlevel 1 goto :run

rem 通っていないので、この bat に書いてある場所を使う
set "PYTHONPATH=%COMKEN_ROOT%;%PYTHONPATH%"

rem 一番多い失敗を先に名指しで出す。ここで止めないと、後から出る Python のエラーが
rem 「ModuleNotFoundError: comken」だけになり、原因が共有サーバーだと分からない
if not exist "%COMKEN_ROOT%\comken\__init__.py" (
  echo [エラー] 共通ライブラリ comken が見つかりません。
  echo     さがした場所: %COMKEN_ROOT%
  echo.
  echo   - 共有サーバーにつながっているか確認してください
  echo   - つながっているなら、この bat の COMKEN_ROOT が正しいか確認してください
  echo   - このパソコンで何度も使うなら、comken のフォルダにある
  echo     install_pythonpath.bat を1回実行しておくと、以後この bat を直さずに済みます
  popd
  pause
  exit /b 1
)

:run
python -m comken.config
rem 終了コードは popd より前に控える（popd が成功すると 0 で上書きされる）
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

rem 終了コードをそのまま返す。スケジューラや RPA 基盤が成否を判断できるようにする
endlocal & exit /b %EXIT_CODE%
