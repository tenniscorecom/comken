"""bat が cmd.exe から文字化けせず、共有フォルダ（UNC パス）でも動く形かを検証する。

bat は **CP932（Shift-JIS）** で書く。cmd.exe は bat を CP932 として読むため、
UTF-8 で保存すると日本語のメッセージが化ける。

UNC パス（`\\\\サーバー名\\...`）から起動されると、cmd.exe はカレントを
`C:\\Windows` にしたまま動く。`cd` では移動できないので `pushd` を使う
（一時的なドライブ名が割り当てられ、UNC でもそのフォルダで動く）。
"""

from __future__ import annotations

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
