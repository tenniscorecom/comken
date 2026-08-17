"""bat が cmd.exe から文字化けせず、共有フォルダ（UNC パス）でも動く形かを検証する。

bat は **CP932（Shift-JIS）** で書く。cmd.exe は bat を CP932 として読むため、
UTF-8 で保存すると日本語のメッセージが化ける。

UNC パス（`\\\\サーバー名\\...`）から起動されると、cmd.exe はカレントを
`C:\\Windows` にしたまま動く。`cd` では移動できないので `pushd` を使う
（一時的なドライブ名が割り当てられ、UNC でもそのフォルダで動く）。
"""

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_BAT_FILES = sorted(path for path in _ROOT.rglob("*.bat") if ".git" not in path.parts)


def _read(path: Path) -> str:
    return path.read_bytes().decode("cp932")


def test_batch_files_exist():
    """検査対象が消えていないこと（rglob の空振りでテストが素通りするのを防ぐ）。"""
    assert _BAT_FILES


@pytest.mark.parametrize("path", _BAT_FILES, ids=lambda p: p.name)
def test_batch_file_is_cp932(path: Path):
    """bat は CP932 で保存する。"""
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"{path.name} に UTF-8 の BOM があります。"
    try:
        raw.decode("cp932")
    except UnicodeDecodeError as e:
        pytest.fail(f"{path.name} が CP932 で読めません（UTF-8 で保存された可能性）。: {e}")


@pytest.mark.parametrize("path", _BAT_FILES, ids=lambda p: p.name)
def test_batch_file_ends_with_newline(path: Path):
    """最終行の後に改行を置く。

    改行が無いと cmd.exe が最後の行を読み切れないことがあり、そこが
    `exit /b` だと**終了コードが返らない**。失敗を終了コードで伝える設計が
    ここで崩れるので、エディタ任せにせずテストで固定する。
    """
    assert path.read_bytes().endswith(b"\n"), (
        f"{path.name} の末尾に改行がありません。最終行が実行されないことがあります。"
    )


@pytest.mark.parametrize("path", _BAT_FILES, ids=lambda p: p.name)
def test_batch_file_uses_pushd_for_unc(path: Path):
    """フォルダ移動は `pushd` を使う（`cd` は UNC パスで移動できない）。"""
    assert "cd /d" not in _read(path), (
        f"{path.name} に cd /d があります。"
        "UNC パスから起動すると移動できないので、pushd を使ってください。"
    )


@pytest.mark.parametrize("path", _BAT_FILES, ids=lambda p: p.name)
def test_batch_file_does_not_switch_codepage(path: Path):
    """`chcp` でコードページを切り替えない。

    切り替えると、cmd.exe が bat を読み進める位置がバイト単位でずれ、
    後続の `set "X=値"` や `set /p` が壊れる。
    """
    assert "chcp" not in _read(path), f"{path.name} に chcp があります。CP932 のままで動きます。"


@pytest.mark.parametrize("path", _BAT_FILES, ids=lambda p: p.name)
def test_batch_file_returns_the_exit_code(path: Path):
    """**終了コードをそのまま返す。**

    `pause` や `popd` で終わると、bat の終了コードはそれらの結果（0）になり、
    中の Python が失敗してもスケジューラや RPA 基盤からは成功に見える。
    """
    assert "exit /b" in _read(path), "失敗を終了コードで返していない（exit /b が無い）"


@pytest.mark.parametrize("path", _BAT_FILES, ids=lambda p: p.name)
def test_batch_file_captures_errorlevel_before_popd(path: Path):
    """`popd` の前に終了コードを控える。

    `popd` は成功すると ERRORLEVEL を 0 にするので、後から読むと失敗が消える。
    """
    text = _read(path)
    # `popd` コマンドとして使われているか。rem コメント内の言及は無視する
    popd_iter = list(re.finditer(r"(?m)^\s*popd\b", text))
    if not popd_iter:
        return  # popd を使わない bat（環境変数を設定するだけ・純粋なラッパー）は対象外
    if "%ERRORLEVEL%" not in text:
        return  # 終了コードを見ていない bat は対象外
    # 最後の popd（正常系）と ERRORLEVEL の控えの位置を比べる
    assert popd_iter[-1].start() > text.index('set "EXIT_CODE=%ERRORLEVEL%"'), (
        "popd より後で ERRORLEVEL を読んでいる（そこでは 0 になっている）"
    )


@pytest.mark.parametrize("path", _BAT_FILES, ids=lambda p: p.name)
def test_batch_file_checks_comken_before_running(path: Path):
    """comken を使う bat は、先に見つかるかを確かめる。

    共有サーバーへつながっていないのが一番多い失敗。先に名指しで出さないと、
    Python の `ModuleNotFoundError: comken` だけになり、原因が分からない。
    """
    text = _read(path)
    if "PYTHONPATH" not in text:
        return  # comken を使わない bat は対象外
    assert r"%COMKEN_ROOT%\comken\__init__.py" in text, "comken の存在を確かめていない"


# comken の場所を「bat 自身のフォルダ以外」から知る手段。**bat ごとに違う。**
# setup は PYTHONPATH を「これから通す」側なので、そこから探してはいけない。
# プロジェクト側へ配る bat（実行・認証情報の登録）は、もともと先頭の固定値を書き換えて使う。
_SECOND_SOURCE = {
    "comken.bat": (r'%PYTHONPATH:;=" "%', "環境変数 PYTHONPATH の走査"),
    "setup_comken.bat": ('set "COMKEN_ROOT_FIXED=', "bat に書いておく固定値"),
    "実行.bat": ('set "COMKEN_ROOT=', "bat に書いておく固定値"),
    "認証情報の登録.bat": ('set "COMKEN_ROOT=', "bat に書いておく固定値"),
}


@pytest.mark.parametrize("path", _BAT_FILES, ids=lambda p: p.name)
def test_batch_file_does_not_rely_on_dp0_alone(path: Path):
    """bat が comken の場所を %~dp0 だけから判定していないこと。

    リポジトリの直下以外（デスクトップ・任意の作業フォルダ）に bat を
    コピーしても動くためには、`%~dp0` 以外からも comken を見つけられる
    手段を持っていなければならない。その手段は bat ごとに違う（下記）。
    """
    text = _read(path)
    # comken を探さない bat は対象外
    if r"comken\__init__.py" not in text:
        return
    assert "%~dp0" in text, f"{path.name} は bat 自身のフォルダを見ていない"
    expected = _SECOND_SOURCE.get(path.name)
    assert expected, f"{path.name} の2つ目の手段が未定義。_SECOND_SOURCE に追記すること"
    phrase, meaning = expected
    assert phrase in text, f"{path.name} は comken の場所を「{meaning}」から探していない"


def test_setup_comken_does_not_use_setx_for_long_vars():
    """**setup_comken.bat は setx で PATH / PYTHONPATH を書かない。**

    setx は 1024 文字を超える値を切り捨てる（この PC のユーザー PATH は実測 2102 文字）。
    そのため PATH と PYTHONPATH は Set-ItemProperty で書き、setx は通知目的だけに使う。
    `setx` の直後に `PATH` や `PYTHONPATH` が続く形になっていれば、setx で書いている。
    """
    text = _read(_ROOT / "setup_comken.bat")
    # rem コメント内を除外するため、行頭にある `setx` コマンドだけ拾う
    for m in re.finditer(r"(?m)^\s*setx\s+(.+)$", text):
        target = m.group(1).split()[0]  # setx の次に書いた変数名（先頭のトークン）
        assert target.upper() not in {"PATH", "PYTHONPATH"}, (
            f"setup_comken.bat が setx で {target} を書いている。"
            "1024 文字制限で切り捨てられるので、setx には短い変数だけを渡してください。"
        )


def test_setup_comken_preserves_raw_value():
    """**setup_comken.bat は値を展開せずに読む。**

    `DoNotExpandEnvironmentNames` を渡して読まないと、`GetEnvironmentVariable` や
    `GetValue` が `%USERPROFILE%` などを絶対パスへ展開し、書き戻しで元表記を失う。
    この PC の多くのユーザー PATH は `REG_EXPAND_SZ` で `%USERPROFILE%...` を持つので、
    展開せずに読むことが必須。
    """
    text = _read(_ROOT / "setup_comken.bat")
    assert "DoNotExpandEnvironmentNames" in text, (
        "setup_comken.bat が DoNotExpandEnvironmentNames を使っていない。"
        "値を展開せずに読む実装にしてください。"
    )


def test_setup_comken_preserves_value_kind():
    """**setup_comken.bat は値の型（REG_SZ / REG_EXPAND_SZ）を保つ。**

    `GetValueKind` で現在の型を調べ、同じ型で書き戻す。型が REG_SZ に変わると、
    値に残った `%変数%` が展開されなくなる。
    """
    text = _read(_ROOT / "setup_comken.bat")
    assert "GetValueKind" in text, (
        "setup_comken.bat が GetValueKind を使っていない。"
        "元の型を保って書き戻す実装にしてください。"
    )


def test_setup_comken_does_not_search_pythonpath():
    """**setup_comken.bat は PYTHONPATH から comken を探さない。**

    この bat は PYTHONPATH と PATH を「これから通す」ためのもの。
    通っていないから実行するのに、そこから探すのは筋が通らない。
    （`comken.bat` は通っている前提で動くので、PYTHONPATH を見てよい）
    """
    text = _read(_ROOT / "setup_comken.bat")
    assert r'%PYTHONPATH:;=" "%' not in text, (
        "setup_comken.bat が PYTHONPATH を探索している。"
        "通すための bat が、通っている前提で探してはいけない。"
    )


def test_comken_bat_searches_pythonpath():
    """comken.bat は PYTHONPATH を `;` 区切りで走査する。

    セットアップ済みの PC で bat だけ手元にある状況（`%~dp0` が comken 直下でない）
    でも comken を見つけられる必要がある。`%PYTHONPATH:;=" "%` という cmd.exe の
    イディオムが使われていることで「`;` で split して for に流す」実装を固定する
    （慣用句なので、書き方が変わると bat が壊れる）。
    """
    text = _read(_ROOT / "comken.bat")
    assert r'%PYTHONPATH:;=" "%' in text, (
        "comken.bat は PYTHONPATH を走査していない。"
        "bat を comken の外に置いたとき、comken を見つけられない。"
    )
