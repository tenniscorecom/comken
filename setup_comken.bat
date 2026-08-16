@echo off
setlocal
rem comken をこのパソコンで使えるようにします（初回に1回だけ）。
rem このリポジトリの場所を、現在の Windows ユーザーの PYTHONPATH と PATH に追加します。
rem 一度実行しておくと、各プロジェクトの 実行.bat が comken の場所を知らなくても動きますし、
rem `comken init` と短く打てるようになります。
rem 場所はこの bat から判定するので、編集は不要です。

for %%I in ("%~dp0.") do set "COMKEN_ROOT=%%~fI"

rem 何を登録するかを先に見せる。UNC パス（\\サーバー名\...）でも登録はできるが、
rem 意図しない場所を登録すると、そのPCが以後ずっとそこを見に行くことになる
echo 次の場所を PYTHONPATH と PATH に追加します:
echo     %COMKEN_ROOT%
echo.

if not exist "%COMKEN_ROOT%\comken\__init__.py" (
  echo [エラー] この場所に comken が見つかりません。
  echo   この bat は comken のリポジトリ直下に置いて実行してください。
  pause
  exit /b 1
)

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
