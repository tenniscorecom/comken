@echo off
setlocal
rem このリポジトリを、現在の Windows ユーザーの PYTHONPATH に追加します。
rem 一度実行しておくと、各プロジェクトの 実行.bat が comken の場所を知らなくても動きます。
rem 場所はこの bat から判定するので、編集は不要です。

for %%I in ("%~dp0.") do set "COMKEN_ROOT=%%~fI"

rem 何を登録するかを先に見せる。UNC パス（\\サーバー名\...）でも登録はできるが、
rem 意図しない場所を登録すると、そのPCが以後ずっとそこを見に行くことになる
echo 次の場所を PYTHONPATH に追加します:
echo     %COMKEN_ROOT%
echo.

if not exist "%COMKEN_ROOT%\comken\__init__.py" (
  echo [エラー] この場所に comken が見つかりません。
  echo   この bat は comken のリポジトリ直下に置いて実行してください。
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = $env:COMKEN_ROOT;" ^
  "$paths = @([Environment]::GetEnvironmentVariable('PYTHONPATH','User') -split ';' | Where-Object { $_ });" ^
  "if ($paths -contains $root) { Write-Host '既に登録済みでした。'; exit 0 };" ^
  "[Environment]::SetEnvironmentVariable('PYTHONPATH', (($paths + $root) -join ';'), 'User');" ^
  "Write-Host ('PYTHONPATH に追加しました: ' + $root)"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [失敗] 環境変数を設定できませんでした（終了コード %EXIT_CODE%）。
  echo   PowerShell の実行が制限されている可能性があります。管理者へ確認してください。
) else (
  echo.
  echo 新しいコマンドプロンプト（または開き直した VS Code）から有効になります。
)
pause

endlocal & exit /b %EXIT_CODE%
