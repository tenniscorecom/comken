@echo off
setlocal
rem このツールの起動用。日本語のコメントが化けないことも確かめる。

set "PYTHON_LIBRARY=\\new\share\tools"
set "PYTHONPATH=%PYTHON_LIBRARY%;%PYTHONPATH%"

pushd "%~dp0"
python main.py
popd
endlocal
