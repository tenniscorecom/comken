@echo off
setlocal
rem 新しいプロジェクトのフォルダ一式を作ります。
rem 作成先は、この bat があるフォルダの1つ上（comken と並ぶ場所）です。

rem 共有フォルダから起動されても動くよう pushd を使う（cd は UNC 不可）
pushd "%~dp0"
set /p "PROJECT_NAME=プロジェクト名を入力してください: "
if defined PROJECT_NAME python new_project.py "%PROJECT_NAME%" --into ".."
popd
pause
endlocal
