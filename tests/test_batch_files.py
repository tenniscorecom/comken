"""bat が cmd.exe から文字化けせずに動く状態かを検証する。

cmd.exe は bat を CP932 として読む。UTF-8 で保存すると日本語のメッセージが化け、
`set /p` の入力プロンプトやエラー案内が読めなくなる。`.gitattributes` で
変換を止めてあるが、エディタが UTF-8 で保存し直すのは防げないためここで検出する。
"""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_BAT_FILES = sorted(path for path in _ROOT.rglob("*.bat") if ".git" not in path.parts)


def test_batch_files_exist():
    """検査対象が消えていないこと（rglob の空振りでテストが素通りするのを防ぐ）。"""
    assert _BAT_FILES


@pytest.mark.parametrize("path", _BAT_FILES, ids=lambda p: p.name)
def test_batch_file_is_cp932(path: Path):
    """bat は CP932 で保存する。"""
    raw = path.read_bytes()
    try:
        raw.decode("cp932")
    except UnicodeDecodeError as e:
        pytest.fail(
            f"{path.relative_to(_ROOT)} が CP932 で読めません（UTF-8 で保存されている可能性）。\n"
            f"cmd.exe は CP932 で読むため、日本語のメッセージが化けます。: {e}"
        )


@pytest.mark.parametrize("path", _BAT_FILES, ids=lambda p: p.name)
def test_batch_file_does_not_switch_codepage(path: Path):
    """`chcp` でコードページを切り替えない。

    CP932 で保存してあれば不要。切り替えると、その bat から起動した
    Python の出力やコンソールの表示まで巻き込んで崩れることがある。
    """
    text = path.read_bytes().decode("cp932")
    assert "chcp" not in text, (
        f"{path.relative_to(_ROOT)} に chcp があります。bat は CP932 で保存し、切り替えない。"
    )
