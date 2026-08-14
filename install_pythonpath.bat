@echo off
setlocal

rem Add this repository to the current Windows user's PYTHONPATH.
rem The repository path is detected from this batch file, so no editing is needed.
for %%I in ("%~dp0.") do set "COMKEN_ROOT_TO_ADD=%%~fI"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = [Environment]::GetEnvironmentVariable('COMKEN_ROOT_TO_ADD', 'Process');" ^
  "$current = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'User');" ^
  "$paths = @($current -split ';' | Where-Object { $_ });" ^
  "$exists = $paths | Where-Object { $_.TrimEnd('\') -ieq $root.TrimEnd('\') };" ^
  "if (-not $exists) { $paths += $root; [Environment]::SetEnvironmentVariable('PYTHONPATH', ($paths -join ';'), 'User'); Write-Host ('Added to user PYTHONPATH: ' + $root) } else { Write-Host ('Already in user PYTHONPATH: ' + $root) }"

if errorlevel 1 (
    echo Failed to update PYTHONPATH.
    pause
    exit /b 1
)

echo.
echo Open a new Command Prompt or restart VS Code before using comken.
pause
