@echo off
setlocal

rem comken のリポジトリルートを指定する（環境に合わせて変更）
set "COMKEN_ROOT=\\server\share\tools\comken"

if not exist "%COMKEN_ROOT%\comken\__init__.py" (
  echo.
  echo [!] comken が見つかりません: %COMKEN_ROOT%
  echo     このファイルの COMKEN_ROOT を正しい共有フォルダに変更してください。
  pause
  exit /b 1
)

rem この起動中だけ comken を import できるようにする（PC の環境変数は変更しない）
set "PYTHONPATH=%COMKEN_ROOT%;%PYTHONPATH%"
rem 共有フォルダから起動されると cd では移動できないため pushd を使う（CMD の仕様）
pushd "%~dp0"

python main.py
if errorlevel 1 pause

popd

endlocal
