"""Windows プロセス操作のテスト。"""

from subprocess import CompletedProcess
from unittest.mock import patch

from comken.toolbox.windows import kill_excel


def test_kill_excel_returns_false_when_taskkill_fails():
    """taskkill が失敗した場合は成功扱いにしない。"""
    running = CompletedProcess([], 0, stdout="EXCEL.EXE", stderr="")
    failed = CompletedProcess([], 1, stdout="", stderr="access denied")

    with patch("comken.toolbox.windows.process.subprocess.run", side_effect=[running, failed]):
        assert kill_excel() is False
