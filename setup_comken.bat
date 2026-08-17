@echo off
setlocal
rem comken をこのパソコンで使えるようにします（初回に1回だけ）。
rem このリポジトリの場所を、現在の Windows ユーザーの PYTHONPATH と PATH に追加します。
rem 一度実行しておくと、各プロジェクトの 実行.bat が comken の場所を知らなくても動きますし、
rem `comken init` と短く打てるようになります。
rem
rem ============================================================
rem  ★ 配る前に、ここへ comken の場所を書いてください
rem     （空のままなら、この bat 自身のフォルダを使います。
rem       comken のリポジトリ直下に置いて実行するならそのままでよい）
rem
rem     例: set "COMKEN_ROOT_FIXED=\\server\share\tools\comken"
rem ============================================================
set "COMKEN_ROOT_FIXED="

rem comken の場所を次の順で探す（見つかった時点で確定、後ろは見ない）:
rem   1. 上に書いた固定値 ―― 各PCへ配るときはここに書いておく
rem   2. この bat 自身のフォルダ（%~dp0）―― リポジトリ直下に置いた場合の正規の置き場所
rem 判定はどちらも `<候補>\comken\__init__.py` の存在で行う（フォルダ名では判定しない）。
rem
rem **PYTHONPATH からは探さない。** この bat は PYTHONPATH と PATH を「これから通す」ための
rem ものなので、通っていない前提で動かなければならない。通っていないから実行するのに
rem そこから探すのは筋が通らない（comken.bat は通っている前提なので PYTHONPATH を見る）。

rem --- 段階 1: 上に書いた固定値 ---
if defined COMKEN_ROOT_FIXED (
  call :_test_comken "%COMKEN_ROOT_FIXED%"
  if not errorlevel 1 goto :_comken_found
)

rem --- 段階 2: bat 自身のフォルダ ---
for %%I in ("%~dp0.") do call :_test_comken "%%~fI"
if not errorlevel 1 goto :_comken_found

rem どちらにも無かった
echo [エラー] comken が見つかりません。
echo   次の2か所を順に探しました:
echo     1. この bat に書いてある固定値: %COMKEN_ROOT_FIXED%
echo     2. この bat 自身のフォルダ
echo.
echo   対処は次のどちらかです:
echo     - この bat を comken のリポジトリ直下（comken フォルダと同じ場所）へ置いて実行する
echo     - この bat をテキストエディタで開き、上のほうにある
echo       set "COMKEN_ROOT_FIXED=" の = の後ろへ comken の場所を書いてから実行する
echo         例: set "COMKEN_ROOT_FIXED=\\server\share\tools\comken"
pause
exit /b 1
rem --- 見つかったルートを確定 ---
:_comken_found
rem 何を登録するかを先に見せる。UNC パス（\\サーバー名\...）でも登録はできるが、
rem 意図しない場所を登録すると、そのPCが以後ずっとそこを見に行くことになる
echo 次の場所を PYTHONPATH と PATH に追加します:
echo     %COMKEN_ROOT%
echo.

rem PYTHONPATH と PATH の両方に「無ければ追加」。登録結果は1行で伝える。
rem どちらか片方だけ既登録でも、もう片方は追加する（1回の実行で済ませる）。
rem
rem **生の値を、元の型のまま書く。**
rem   [Environment]::GetEnvironmentVariable('Path','User') は %USERPROFILE% などを
rem   絶対パスへ展開した値を返し、それを書き戻すと型が REG_SZ に変わる。
rem   元の REG_EXPAND_SZ ではその %変数% が機能しなくなるため、HKCU を直接読み書きする。
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = $env:COMKEN_ROOT;" ^
  "$key = Get-Item 'HKCU:\Environment';" ^
  "function _Read($name){ $raw = $key.GetValue($name, '', 'DoNotExpandEnvironmentNames'); if ($raw) { $raw -split ';' | Where-Object { $_ } } else { @() } };" ^
  "function _Write($name, $value){" ^
  "  $kind = $key.GetValueKind($name); if (-not $kind) { $kind = 'String' };" ^
  "  Set-ItemProperty -Path 'HKCU:\Environment' -Name $name -Value $value -Type $kind" ^
  "};" ^
  "$py = _Read 'PYTHONPATH';" ^
  "$path = _Read 'Path';" ^
  "$added = @();" ^
  "if (-not ($py | Where-Object { $_.ToString() -ieq $root })) { _Write 'PYTHONPATH' (($py + $root) -join ';'); $added += 'PYTHONPATH' };" ^
  "if (-not ($path | Where-Object { $_.ToString() -ieq $root })) { _Write 'Path' (($path + $root) -join ';'); $added += 'PATH' };" ^
  "if ($added.Count -eq 0) { Write-Host '既に登録済みでした。' }" ^
  "else { Write-Host ('追加しました: ' + ($added -join ', ') + ' / ' + $root) }"
set "EXIT_CODE=%ERRORLEVEL%"

rem 環境変数の変更を他プロセスへ通知する（Explorer から起動したターミナル等）。
rem Set-ItemProperty はレジストリを書くだけで WM_SETTINGCHANGE を送らないので、
rem setx を1つ呼んでブロードキャストを誘発する。**PATH/PYTHONPATH を setx で書かないこと**
rem （1024 文字制限で切り捨てられ PATH が壊れる。短い変数を1つ書くためだけに使う）。
if "%EXIT_CODE%"=="0" setx COMKEN_ROOT_REGISTERED "1" >nul

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

rem --- comken の場所をひとつ試し、見つかれば COMKEN_ROOT に確定する ---
rem 見つかったら errorlevel 0 / COMKEN_ROOT は確定値。見つからなければ 1 / COMKEN_ROOT は空。
:_test_comken
set "COMKEN_ROOT=%~1"
if exist "%COMKEN_ROOT%\comken\__init__.py" exit /b 0
set "COMKEN_ROOT="
exit /b 1
