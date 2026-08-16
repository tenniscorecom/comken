@echo off
setlocal
rem comken の入口。`comken init [プロジェクト名]` で、新しいプロジェクトの雛形を作ります。
rem この bat の場所を PYTHONPATH へ一時的に足してから Python を起動するので、
rem 共有サーバー上の comken を参照している環境でもそのまま動きます。
rem PATH に登録していない PC では、フルパスで指定してください。

rem comken の場所を確定（%~dp0 から末尾の \ を除いた絶対パス）
for %%I in ("%~dp0.") do set "COMKEN_ROOT=%%~fI"

rem python が見つからないときは、その旨を名指しで表示する。
rem popd や pause を使わずにそのまま返すので、スケジューラや RPA 基盤から
rem 呼んだときも成否が正しく伝わる。
where python >nul 2>&1 || (
  echo [エラー] Python が見つかりません。
  echo   このパソコンに Python がインストールされているか、管理者に確認してください。
  exit /b 1
)

rem comken がここにあるかを先に確かめる。共有サーバーへつながらないうちに
rem 進めると、後ろで出るエラーが `ModuleNotFoundError: comken` だけになり、
rem 原因が分かりにくい
if not exist "%COMKEN_ROOT%\comken\__init__.py" (
  echo [エラー] 共有ライブラリ comken が見つかりません。
  echo     確認した場所: %COMKEN_ROOT%
  echo   - 共有サーバーに接続できているか確認してください
  echo   - この bat は comken のリポジトリ直下に置いて実行してください
  exit /b 1
)

rem PYTHONPATH へ一時追加（恒久登録は setup_comken.bat の仕事）。
rem setlocal の中で set しているので、呼び出し元の環境は汚さない。
set "PYTHONPATH=%COMKEN_ROOT%;%PYTHONPATH%"

rem 引数の形: comken init [プロジェクト名]
rem 引数なし、または第1引数が init 以外 → 使い方を表示して 1 で終了
if "%~1"=="" goto usage
if /i not "%~1"=="init" goto usage

rem 第3引数以降は不可（init は名前を1つだけ受け取る）
if not "%~3"=="" goto too_many_args

set "PROJECT_NAME=%~2"
if "%PROJECT_NAME%"=="" (
  set /p "PROJECT_NAME=プロジェクト名を入力してください: "
  if not defined PROJECT_NAME (
    echo.
    echo [中断] プロジェクト名が入力されなかったので、終了しました。
    exit /b 1
  )
)

rem 作成先は打った場所（%CD%）。中で cd / pushd しないのは、
rem 共有サーバー上の comken を参照していても、プロジェクトは手元に作られるようにするため。
python "%COMKEN_ROOT%\tools\new_project.py" "%PROJECT_NAME%" --into "%CD%"
exit /b %ERRORLEVEL%

:usage
echo 使い方: comken init [プロジェクト名]
echo.
echo   プロジェクト名を指定すると、今いるフォルダに新しいプロジェクトの
echo   ひな形を作ります。プロジェクト名を省略すると、対話で名前を聞きます。
exit /b 1

:too_many_args
echo [エラー] 引数が多すぎます。
echo 使い方: comken init [プロジェクト名]
exit /b 1
