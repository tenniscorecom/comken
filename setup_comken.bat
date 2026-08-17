@echo off
setlocal
rem comken をこのパソコンで使えるようにします（初回に1回だけ）。
rem このリポジトリの場所を、現在の Windows ユーザーの PYTHONPATH と PATH に追加します。
rem 一度実行しておくと、各プロジェクトの 実行.bat が comken の場所を知らなくても動きますし、
rem `comken init` と短く打てるようになります。
rem
rem 渡し方（2つのうちのどちらか）:
rem   setup_comken.bat                  ← この bat 自身のフォルダ（%~dp0）を使う
rem   setup_comken.bat C:\dev\original_libs   ← 引数で comken の場所を明示する
rem comken の場所を次の順で探す（見つかった時点で確定、後ろは見ない）:
rem   1. 第1引数で明示されたパス ―― 別の場所を指定したいとき
rem   2. この bat 自身のフォルダ（%~dp0）―― リポジトリ直下に置いた場合の正規の置き場所
rem   3. 現在の PYTHONPATH の各エントリ ―― セットアップ済みの PC で bat だけ手元にある場合
rem 判定はどの候補も `<候補>\comken\__init__.py` の存在で行う（フォルダ名では判定しない）。
rem この探索ロジックは comken.bat にも同じものを載せてある（共通 bat を作るとそちらも
rem 一緒に持ち歩かないと動かなくなるため、重複を許容している）。

rem --- 段階 1: 第1引数 ---
if not "%~1"=="" (
  call :_test_comken "%~1"
  if not errorlevel 1 goto :_comken_found
)

rem --- 段階 2: bat 自身のフォルダ ---
for %%I in ("%~dp0.") do call :_test_comken "%%~fI"
if not errorlevel 1 goto :_comken_found

rem --- 段階 3: 現在の PYTHONPATH（未設定ならスキップ） ---
if defined PYTHONPATH (
  for %%P in ("%PYTHONPATH:;=" "%") do (
    call :_test_comken "%%~P"
    if not errorlevel 1 goto :_comken_found
  )
)

rem どれも見つからなかった
echo [エラー] comken が見つかりません。
echo   次の3か所を順に探しました（先頭に見つかったものが使われます）:
echo     1. 第1引数で渡されたパス: %~1
echo     2. この bat 自身のフォルダ
echo     3. 環境変数 PYTHONPATH（; 区切り）
echo   comken の場所を引数で渡してください（例）:
echo     setup_comken.bat "C:\dev\original_libs"
echo     setup_comken.bat "\\server\share\tools\comken"
pause
exit /b 1

rem --- 見つかったルートを確定 ---
:_comken_found
rem 何を登録するかを先に見せる。UNC パス（\\サーバー名\...）でも登録はできるが、
rem 意図しない場所を登録すると、そのPCが以後ずっとそこを見に行くことになる
echo 次の場所を PYTHONPATH と PATH に追加します:
echo     %COMKEN_ROOT%
echo.

rem PYTHONPATH と PATH の両方に「無ければ追加」。登録結果は1行で伝える。
rem どちらか片方だけ既登録でも、もう片方は追加する（1回の実行で済ませる）。
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = $env:COMKEN_ROOT;" ^
  "$py = @([Environment]::GetEnvironmentVariable('PYTHONPATH','User') -split ';' | Where-Object { $_ });" ^
  "$path = @([Environment]::GetEnvironmentVariable('Path','User') -split ';' | Where-Object { $_ });" ^
  "$added = @();" ^
  "if ($py -notcontains $root) { [Environment]::SetEnvironmentVariable('PYTHONPATH', (($py + $root) -join ';'), 'User'); $added += 'PYTHONPATH' };" ^
  "if ($path -notcontains $root) { [Environment]::SetEnvironmentVariable('Path', (($path + $root) -join ';'), 'User'); $added += 'PATH' };" ^
  "if ($added.Count -eq 0) { Write-Host '既に登録済みでした。' }" ^
  "else { Write-Host ('追加しました: ' + ($added -join ', ') + ' / ' + $root) }"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [失敗] 環境変数を設定できませんでした（終了コード %EXIT_CODE%）。
  echo   PowerShell の実行が制限されている可能性があります。管理者へ確認してください。
) else (
  echo.
  echo 新しいコマンドプロンプト（または開き直した VS Code）から有効になります。
  echo `comken init プロジェクト名` で雛形を作れます。
)
pause

endlocal & exit /b %EXIT_CODE%

rem --- comken の場所をひとつ試し、見つかれば COMKEN_ROOT に確定する ---
rem 見つかったら errorlevel 0 / COMKEN_ROOT は確定値。見つからなければ 1 / COMKEN_ROOT は空。
:_test_comken
set "COMKEN_ROOT=%~1"
if exist "%COMKEN_ROOT%\comken\__init__.py" exit /b 0
set "COMKEN_ROOT="
exit /b 1
