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


@pytest.mark.parametrize("path", _BAT_FILES, ids=lambda p: p.name)
def test_batch_file_does_not_rely_on_dp0_alone(path: Path):
    """bat が comken の場所を %~dp0 だけから判定していないこと。

    リポジトリの直下以外（デスクトップ・任意の作業フォルダ）に bat を
    コピーしても動くためには、`%~dp0` 以外からも comken を見つけられる
    手段を持っていなければならない。
    """
    text = _read(path)
    # comken を探さない bat は対象外
    if r"comken\__init__.py" not in text:
        return
    # bat の探索系ロジックが入っているサイン
    for phrase, meaning in [
        ("%~dp0", "bat 自身のフォルダ"),
        ("PYTHONPATH", "環境変数 PYTHONPATH"),
    ]:
        assert phrase in text, f"{path.name} は comken の場所を {meaning} からしか探していない"


def test_setup_comken_accepts_a_path_argument():
    """setup_comken.bat は第1引数で comken の場所を受け取れる。

    リポジトリ外に bat を置いた場合に、引数で明示する導線が残っているかを
    見る（引数を渡すと `%~1` が展開される）。
    """
    path = _ROOT / "setup_comken.bat"
    text = _read(path)
    assert "%~1" in text, "setup_comken.bat は第1引数を受け取れる形であるべき"


def test_pythonpath_search_is_implemented_in_comken_locators():
    """comken の場所を探す 2 本の bat は、PYTHONPATH を `;` 区切りで走査する。

    リポジトリ外に bat がある状況（%~dp0 が comken 直下でない）で、
    既に PYTHONPATH に入っていればそこから見つけられる必要がある。
    `%PYTHONPATH:;=" "%` という cmd.exe のイディオムが使われていることで
    「`;` で split して for に流す」実装があることを固定する
    （cmd.exe 側の慣用句で、書き方が変わると bat が壊れる）。
    """
    for name in ("comken.bat", "setup_comken.bat"):
        path = _ROOT / name
        text = _read(path)
        assert r'%PYTHONPATH:;=" "%' in text, (
            f"{name} は PYTHONPATH を走査していない。"
            "bat を comken の外に置いたとき、comken を見つけられない。"
        )
