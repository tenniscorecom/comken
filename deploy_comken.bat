@echo off
setlocal
rem comken を BO 用の共有フォルダへ配置します。
rem バージョンは上げません。先に comken\__init__.py の __version__ を上げてください。

rem 共有フォルダから起動されても動くよう pushd を使う（cd は UNC 不可）
pushd "%~dp0"
set "DEPLOY_TARGET=%~1"
if not defined DEPLOY_TARGET set /p "DEPLOY_TARGET=配置先のフォルダ: "
if defined DEPLOY_TARGET python deploy.py "%DEPLOY_TARGET%"
popd
pause
endlocal
