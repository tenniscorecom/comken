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
