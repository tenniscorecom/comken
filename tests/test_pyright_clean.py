"""pyright のエラー件数が 0 を維持していることを保証するテスト。

pyright の実行が遅い (`npx` 経由の初回インストール + 型解析) ため、
タイムアウトは余裕を見て 600 秒。pyright が利用できない環境では skip する。
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PYRIGHT_TIMEOUT_SECONDS = 600


def _has_npx() -> bool:
    return shutil.which("npx") is not None


@pytest.mark.skipif(not _has_npx(), reason="npx が無い環境では pyright を実行できない")
def test_pyright_zero_errors() -> None:
    """pyright が 0 errors を維持していることを保証する。

    このテストが落ちる = 新しい pyright エラーが入ったということ。
    直したら、件数の上限を更新する (今のところ上限は 0)。
    """
    # Windows では npx は npx.cmd なので shutil.which の戻り値（フルパス）をそのまま渡す。
    # "npx" だけだと Python の subprocess が PATHEXT を見ずに失敗する。
    npx_cmd = shutil.which("npx")  # type: ignore[assignment]
    assert npx_cmd is not None  # _has_npx で確認済みだが型チェッカー用に絞り込む
    proc = subprocess.run(
        [npx_cmd, "--yes", "pyright@latest", "comken/"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=PYRIGHT_TIMEOUT_SECONDS,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    match = re.search(r"(\d+) errors?", output)
    count = int(match.group(1)) if match else -1
    assert count == 0, f"pyright errors: {count}\n{output}"
