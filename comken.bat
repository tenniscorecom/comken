@echo off
setlocal
rem comken の入口。`comken init [プロジェクト名]` で、新しいプロジェクトの雛形を作ります。
rem この bat の場所を PYTHONPATH へ一時的に足してから Python を起動するので、
rem 共有サーバー上の comken を参照している環境でもそのまま動きます。
rem PATH に登録していない PC では、フルパスで指定してください。
rem
rem comken の場所は次の順で探す（見つかった時点で確定、後ろは見ない）:
rem   1. この bat 自身のフォルダ（%~dp0）―― リポジトリ直下に置いた場合の正規の置き場所
rem   2. 現在の PYTHONPATH の各エントリ ―― セットアップ済みの PC で bat だけ手元にある場合
rem 判定はどの候補も `<候補>\comken\__init__.py` の存在で行う（フォルダ名では判定しない）。
rem この探索ロジックは setup_comken.bat にも同じものを載せてある（共通 bat を作ると
rem そちらも一緒に持ち歩かないと動かなくなるため、重複を許容している）。

rem --- 段階 1: bat 自身のフォルダ ---
for %%I in ("%~dp0.") do call :_test_comken "%%~fI"
if not errorlevel 1 goto :_comken_found

rem --- 段階 2: 現在の PYTHONPATH（未設定ならスキップ） ---
if defined PYTHONPATH (
  for %%P in ("%PYTHONPATH:;=" "%") do (
    call :_test_comken "%%~P"
    if not errorlevel 1 goto :_comken_found
  )
)

rem どちらも見つからなかった
echo [エラー] 共有ライブラリ comken が見つかりません。
echo   探した手順:
echo     1. この bat 自身のフォルダ
echo     2. 環境変数 PYTHONPATH（; 区切り）
echo   comken の場所を引数で渡して setup_comken.bat を実行してください（例）:
echo     setup_comken.bat "C:\dev\original_libs"
echo     setup_comken.bat "\\server\share\tools\comken"
exit /b 1

rem --- 見つかったルートを確定 ---
:_comken_found
rem python が見つからないときは、その旨を名指しで表示する。
rem popd や pause を使わずにそのまま返すので、スケジューラや RPA 基盤から
rem 呼んだときも成否が正しく伝わる。
where python >nul 2>&1 || (
  echo [エラー] Python が見つかりません。
  echo   このパソコンに Python がインストールされているか、管理者に確認してください。
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

rem --- comken の場所をひとつ試し、見つかれば COMKEN_ROOT に確定する ---
rem 見つかったら errorlevel 0 / COMKEN_ROOT は確定値。見つからなければ 1 / COMKEN_ROOT は空。
:_test_comken
set "COMKEN_ROOT=%~1"
if exist "%COMKEN_ROOT%\comken\__init__.py" exit /b 0
set "COMKEN_ROOT="
exit /b 1
