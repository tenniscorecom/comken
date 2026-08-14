@echo off
setlocal
rem このリポジトリを、現在の Windows ユーザーの PYTHONPATH に追加します。
rem 場所はこの bat から判定するので、編集は不要です。

for %%I in ("%~dp0.") do set "COMKEN_ROOT=%%~fI"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = $env:COMKEN_ROOT;" ^
  "$paths = @([Environment]::GetEnvironmentVariable('PYTHONPATH','User') -split ';' | Where-Object { $_ });" ^
  "if ($paths -notcontains $root) { [Environment]::SetEnvironmentVariable('PYTHONPATH', (($paths + $root) -join ';'), 'User') };" ^
  "Write-Host ('PYTHONPATH に設定しました: ' + $root)"

echo 新しいコマンドプロンプト（または再起動した VS Code）から有効になります。
pause
endlocal
