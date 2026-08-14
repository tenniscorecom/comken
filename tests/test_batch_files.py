"""bat が cmd.exe から行の解釈を崩さずに動く状態かを検証する。

bat は UTF-8 で統一する（BOM は付いていてもよい）。実測した挙動（Windows 10 / cmd.exe）:

| 保存形式 | UTF-8 コンソール(65001) | CP932 コンソール(932) |
|---|---|---|
| UTF-8 | 正常 | 日本語表示だけ化ける（コマンドは壊れない） |
| UTF-8 + BOM | 正常 | 1 行目に BOM が食い込みエラーになる |
| UTF-8 + `chcp 65001` | 正常 | 行のパースがずれて `set "X=値"` が壊れる |
| CP932 | 日本語が化ける | 正常 |

`chcp` だけは、どのコンソールでも後続の `set` を壊しうるため禁止する。
"""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_BAT_FILES = sorted(path for path in _ROOT.rglob("*.bat") if ".git" not in path.parts)


def test_batch_files_exist():
    """検査対象が消えていないこと（rglob の空振りでテストが素通りするのを防ぐ）。"""
    assert _BAT_FILES


@pytest.mark.parametrize("path", _BAT_FILES, ids=lambda p: p.name)
def test_batch_file_is_utf8(path: Path):
    """bat は UTF-8 で保存する（BOM の有無は問わない）。"""
    raw = path.read_bytes()
    try:
        raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        pytest.fail(
            f"{path.relative_to(_ROOT)} が UTF-8 で読めません"
            f"（CP932 で保存されている可能性）。: {e}"
        )


@pytest.mark.parametrize("path", _BAT_FILES, ids=lambda p: p.name)
def test_batch_file_does_not_switch_codepage(path: Path):
    """`chcp` でコードページを切り替えない。

    切り替えると、cmd.exe が bat を読み進める位置がバイト単位でずれ、
    後続の `set "X=値"` や `set /p` が壊れる（日本語を含む行の直後で起きる）。
    """
    text = path.read_bytes().decode("utf-8-sig")
    assert "chcp" not in text, (
        f"{path.relative_to(_ROOT)} に chcp があります。"
        "切り替えると後続の set 行が壊れるため、入れないでください。"
    )
