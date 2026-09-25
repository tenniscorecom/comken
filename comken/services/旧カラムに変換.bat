@echo off
rem CSV を旧ロールの列だけにする（応需の新ロールで列が255を超えて、Access に取り込めないときの応急処置）。
rem この bat を CSV のあるフォルダへコピーして使う。
rem   ダブルクリック                  : この bat のあるフォルダの *.csv を全部変換する
rem   ファイル・フォルダをドラッグ＆ドロップ : 落としたものだけを変換する
rem 新ロールの元ファイルは「元の名前_bak.csv」として残る。変換済みのファイルは飛ばすので、何度押しても安全。
rem comken の場所は、PC のイメージ配布で設定済みの環境変数を使う。
rem 実行結果を見られるよう、最後に pause で止める（RPA から呼ぶ bat ではない）。
pushd "%~dp0" || (echo [エラー] フォルダに移動できません: %~dp0 & pause & exit /b 1)
python -m comken.services.csv_column_reducer %*
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" echo [失敗] 上のログで、変換できなかったファイルと原因を確認してください
pause
exit /b %EXIT_CODE%
