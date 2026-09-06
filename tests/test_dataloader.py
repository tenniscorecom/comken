"""DataLoaderCLI の subprocess 配線と結果 CSV 読み込みを疑似 launcher で検証する。

このテストは **Python 側の配管**（subprocess 呼び出し・タイムアウト・終了
コード判定・成功／エラー CSV の Table 化）を確認するためのもので、
本物の Salesforce Data Loader を実際に動かす検証ではないことに注意。
疑似 launcher には Python 自身の ``[sys.executable, "-c", "..."]`` を
``launcher_path`` の代わりに渡す。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from comken.core.table import Table
from comken.exceptions import (
    DataLoaderExecutionError,
    DataLoaderLauncherNotFoundError,
    DataLoaderResultFileMissingError,
    DataLoaderTimeoutError,
)
from comken.toolbox.dataloader import DataLoaderCLI, DataLoaderResult


def _write_python_launcher(tmp_path: Path, source: str) -> Path:
    """``python -c <source>`` を launcher の代わりに使える小さな .py として書き出す。

    ``subprocess.run`` の第1引数は list なので、本来 launcher には実行ファイル
    のパスを1要素として渡せば十分だが、テストでは
    ``[sys.executable, "-c", source]`` 相当のラッパーを ``.py`` に焼き直して
    ``launcher_path`` に渡すことで ``exists()`` チェックを通す。
    """
    launcher = tmp_path / "fake_launcher.py"
    launcher.write_text(source, encoding="utf-8")
    return launcher


class TestDataLoaderCLI:
    """DataLoaderCLI の subprocess 配線と結果 CSV 読み込みの検証。"""

    def test_launcher_path_must_be_a_real_file(self, tmp_path: Path) -> None:
        """launcher が無いパスだと ``DataLoaderLauncherNotFoundError``。"""
        cli = DataLoaderCLI(tmp_path / "missing.bat")
        with pytest.raises(DataLoaderLauncherNotFoundError, match="見つかりません"):
            cli.run([])

    def test_constructor_rejects_non_positive_timeout(self, tmp_path: Path) -> None:
        """``timeout_seconds`` が 0 以下は ``ValueError``。"""
        launcher = tmp_path / "fake_launcher.py"
        launcher.write_text("pass", encoding="utf-8")
        with pytest.raises(ValueError, match="0より大きい"):
            DataLoaderCLI(launcher, timeout_seconds=0)

    def test_constructor_does_not_check_file_existence(self, tmp_path: Path) -> None:
        """コンストラクタではファイルの存在を確認しない（``run()`` で確認する）。"""
        # 存在しないパスを渡してもコンストラクタは例外を出さない
        DataLoaderCLI(tmp_path / "not_yet_created.bat")
        # ファイルはこのあと run() までに用意すればよい（間隙を許す設計）

    def test_run_loads_success_and_error_csvs_into_tables(self, tmp_path: Path) -> None:
        """正常終了時に success_csv / error_csv が ``Table`` として読める。"""
        success_csv = tmp_path / "success.csv"
        error_csv = tmp_path / "error.csv"
        success_csv.write_text("id,name\n1,山田\n2,鈴木\n", encoding="utf-8-sig")
        error_csv.write_text("id,reason\n3,validation\n", encoding="utf-8-sig")

        # 疑似 launcher: 引数を受け取って即終了するだけの Python スクリプト
        launcher_source = "import sys\nprint('done')\n"
        launcher = _write_python_launcher(tmp_path, launcher_source)

        # launcher に渡すコマンドは list 形式で組み立てる。
        # テストでは本物の Data Loader を呼び出せないので、python 自体を
        # launcher に見立て、起動後すぐに return 0 させる。
        result = DataLoaderCLI(sys.executable, timeout_seconds=10).run(
            [str(launcher)],
            success_csv=success_csv,
            error_csv=error_csv,
        )

        assert isinstance(result, DataLoaderResult)
        assert result.returncode == 0
        assert result.success.columns == ["id", "name"]
        assert result.success.read_rows() == [
            {"id": "1", "name": "山田"},
            {"id": "2", "name": "鈴木"},
        ]
        assert result.errors.columns == ["id", "reason"]
        assert result.errors.read_rows() == [{"id": "3", "reason": "validation"}]

    def test_run_returns_empty_tables_when_csvs_are_none(self, tmp_path: Path) -> None:
        """``success_csv`` / ``error_csv`` を ``None`` にすると空 ``Table`` が返る。"""
        launcher_source = "print('ok')\n"
        launcher = _write_python_launcher(tmp_path, launcher_source)

        result = DataLoaderCLI(sys.executable, timeout_seconds=10).run([str(launcher)])

        assert result.returncode == 0
        assert result.success == Table([], [])
        assert result.errors == Table([], [])
        # 空 Table なので長さも 0、列も空
        assert len(result.success) == 0
        assert result.success.columns == []

    def test_non_zero_returncode_raises_with_stdout_and_stderr(self, tmp_path: Path) -> None:
        """0 以外の終了コードだと ``DataLoaderExecutionError``。stdout / stderr が残る。"""
        launcher_source = (
            "import sys\n"
            "print('何かの標準出力', file=sys.stdout)\n"
            "print('何かの標準エラー', file=sys.stderr)\n"
            "sys.exit(7)\n"
        )
        launcher = _write_python_launcher(tmp_path, launcher_source)

        cli = DataLoaderCLI(sys.executable, timeout_seconds=10)
        with pytest.raises(DataLoaderExecutionError) as caught:
            cli.run([str(launcher)])

        message = str(caught.value)
        # 終了コード・標準出力・標準エラーのすべてがメッセージに含まれる
        assert "returncode: 7" in message
        assert "何かの標準出力" in message
        assert "何かの標準エラー" in message
        # 個別例外の派生元が ``DataLoaderError`` / ``ComkenError``
        assert isinstance(caught.value, DataLoaderExecutionError)

    def test_timeout_raises_data_loader_timeout_error(self, tmp_path: Path) -> None:
        """``timeout_seconds`` を超えると ``DataLoaderTimeoutError``。"""
        # sleep する launcher
        launcher_source = "import time\ntime.sleep(5)\n"
        launcher = _write_python_launcher(tmp_path, launcher_source)

        cli = DataLoaderCLI(sys.executable, timeout_seconds=0.5)
        with pytest.raises(DataLoaderTimeoutError, match=r"0\.5 秒以内") as caught:
            cli.run([str(launcher)])

        assert isinstance(caught.value, DataLoaderTimeoutError)

    def test_missing_success_csv_raises_result_file_missing_error(self, tmp_path: Path) -> None:
        """指定した ``success_csv`` が無いと ``DataLoaderResultFileMissingError``。"""
        launcher_source = "print('ok')\n"
        launcher = _write_python_launcher(tmp_path, launcher_source)
        nonexistent = tmp_path / "never_created.csv"

        cli = DataLoaderCLI(sys.executable, timeout_seconds=10)
        with pytest.raises(DataLoaderResultFileMissingError) as caught:
            cli.run([str(launcher)], success_csv=nonexistent)
        assert str(nonexistent) in str(caught.value)

    def test_missing_error_csv_raises_result_file_missing_error(self, tmp_path: Path) -> None:
        """指定した ``error_csv`` が無いと ``DataLoaderResultFileMissingError``。"""
        launcher_source = "print('ok')\n"
        launcher = _write_python_launcher(tmp_path, launcher_source)
        nonexistent = tmp_path / "never_created.csv"

        cli = DataLoaderCLI(sys.executable, timeout_seconds=10)
        with pytest.raises(DataLoaderResultFileMissingError) as caught:
            cli.run([str(launcher)], error_csv=nonexistent)
        assert str(nonexistent) in str(caught.value)

    def test_launcher_path_property_returns_path(self, tmp_path: Path) -> None:
        """``launcher_path`` プロパティがコンストラクタに渡した ``Path`` を返す。"""
        target = tmp_path / "dataloader.bat"
        cli = DataLoaderCLI(target)
        assert cli.launcher_path == target
        assert isinstance(cli.launcher_path, Path)

    def test_timeout_seconds_property_returns_value(self, tmp_path: Path) -> None:
        """``timeout_seconds`` プロパティがコンストラクタに渡した値を返す。"""
        cli = DataLoaderCLI(tmp_path / "dataloader.bat", timeout_seconds=120)
        assert cli.timeout_seconds == 120
