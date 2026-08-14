@echo off
setlocal
rem config.ini から補完用スタブ（typings/comken/）を作り直します。
rem 普段は main.py を1回動かせば自動で作られるので、必須ではありません。

set "COMKEN_ROOT=\\server\share\tools\comken"
set "PYTHONPATH=%COMKEN_ROOT%;%PYTHONPATH%"

pushd "%~dp0"
python -m comken.config
if errorlevel 1 pause
popd
endlocal
