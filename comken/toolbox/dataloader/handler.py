"""comken/toolbox/dataloader/handler.py — Salesforce Data Loader の CLI 呼び出し。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from comken.core.table import Table
from comken.exceptions import (
    DataLoaderExecutionError,
    DataLoaderLauncherNotFoundError,
    DataLoaderResultFileMissingError,
    DataLoaderTimeoutError,
)
from comken.toolbox.csv import CSV

DEFAULT_TIMEOUT_SECONDS = 3600


@dataclass(frozen=True)
class DataLoaderResult:
    """Data Loader 実行結果。

    Attributes:
        success: Data Loader が書き出した成功 CSV を読み込んだ ``Table``。
            ``success_csv`` を ``None`` に指定した場合は空の ``Table``。
        errors: Data Loader が書き出したエラー CSV を読み込んだ ``Table``。
            ``error_csv`` を ``None`` に指定した場合は空の ``Table``。
            **1件以上のエラー行が入っていても例外ではない**（呼び出し側が
            中身を見て個別に判断する。プロセス自体は正常終了している）。
        returncode: サブプロセスの終了コード。正常終了は 0。
        stdout: Data Loader の標準出力（プロセス終了時点）。
        stderr: Data Loader の標準エラー出力（プロセス終了時点）。
    """

    success: Table
    errors: Table
    returncode: int
    stdout: str
    stderr: str


class DataLoaderCLI:
    """Salesforce Data Loader をコマンドラインから実行する。

    Salesforce Data Loader は、Salesforce が配布する大量データの一括変更用の
    デスクトップアプリ。インストールすると ``dataloader.bat``（Windows の場合）
    のような実行ファイルが配置され、CLI モードで動かすと ``config.properties`` と
    ``process-conf.xml`` を読み込んで一括挿入・更新・削除を行う。

    **このクラスは、その CLI 呼び出しを Python から扱いやすくする薄ラッパー。**
    ``subprocess.run`` の呼び出し・タイムアウト管理・終了コード確認・成功／
    エラー CSV の ``Table`` 読み込みまでを担当する。

    **Data Loader 自身のインストールと ``config.properties`` /
    ``process-conf.xml`` の作成は利用者の作業。** comken 側で用意しない。

    **最重要の設計方針:** Data Loader の CLI 呼び出し構文（launcher に渡す
    引数の形）は **バージョンによって変わりうる**。comken 側では構文を
    決め打ちせず、利用者が ``launcher_path`` と ``args`` を渡す形にする。
    実際に動くコマンドは、使っている Data Loader のバージョンに合わせて
    ターミナルで一度確認してから ``args`` に渡す。
    """

    def __init__(
        self,
        launcher_path: str | Path,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """``launcher_path`` とタイムアウト秒数を保持する。

        ここではファイルの存在を確認しない。コンストラクタと ``run()`` の間で
        ファイルが移動・復旧する余地を残すため（既存の ``Excel`` など、
        「コンストラクタでは開かない、``__enter__``/操作時に確認する」設計に
        ならう）。実際の存在確認は ``run()`` の冒頭で行う。

        Args:
            launcher_path: Data Loader の実行ファイル（例:
                ``C:\\Program Files\\salesforce.com\\Data Loader\\dataloader.bat``）。
            timeout_seconds: サブプロセスのタイムアウト秒数。大量データを扱うため
                既定値は 3600秒（1時間）。短くするほどタイムアウト判定が早くなる。
        """
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds は0より大きい値で指定してください。")
        self._launcher_path = Path(launcher_path)
        self._timeout_seconds = timeout_seconds

    @property
    def launcher_path(self) -> Path:
        """コンストラクタに渡した実行ファイルのパス。"""
        return self._launcher_path

    @property
    def timeout_seconds(self) -> float:
        """サブプロセスのタイムアウト秒数。"""
        return self._timeout_seconds

    def run(
        self,
        args: list[str],
        *,
        success_csv: str | Path | None = None,
        error_csv: str | Path | None = None,
        cwd: str | Path | None = None,
    ) -> DataLoaderResult:
        """Data Loader を subprocess で実行し、結果を ``DataLoaderResult`` で返す。

        Data Loader の CLI 呼び出し（launcher_path に渡す args の形）は
        バージョンによって異なることがある。**このメソッドは正確な構文を
        決め打ちしない。** 実際に動くコマンドを、事前にターミナルで
        一度確認してから args に渡すこと。

        使用例（構文は一例。実際の値は自分の Data Loader のバージョンで確認する）:

            cli = DataLoaderCLI(r"C:\\Program Files\\salesforce.com\\Data Loader\\dataloader.bat")
            result = cli.run(
                ["run", str(config_dir)],
                success_csv=config_dir / "success.csv",
                error_csv=config_dir / "error.csv",
            )
            if len(result.errors) > 0:
                print(f"{len(result.errors)} 件が失敗しました")

        Args:
            args: launcher に渡す引数のリスト。先頭に launcher 自身は含めない
                （このクラスが ``[str(launcher_path), *args]`` の形で組み立てる）。
            success_csv: Data Loader が書き出した成功 CSV のパス。``None`` を
                渡すと読み込み対象外（空の ``Table`` が返る）。
            error_csv: Data Loader が書き出したエラー CSV のパス。``None`` を
                渡すと読み込み対象外（空の ``Table`` が返る）。
            cwd: サブプロセスのカレントディレクトリ。``None`` のときは
                ``subprocess.run`` の既定動作に従う。

        Returns:
            DataLoaderResult: 成功／エラー CSV を ``Table`` 化した結果。

        Raises:
            DataLoaderLauncherNotFoundError: ``launcher_path`` が存在しない。
            DataLoaderTimeoutError: ``timeout_seconds`` 内にプロセスが終わらなかった。
            DataLoaderExecutionError: Data Loader が 0 以外の終了コードで終了した
                （stdout / stderr がメッセージに含まれる）。
            DataLoaderResultFileMissingError: 正常終了したのに ``success_csv`` または
                ``error_csv`` に指定したパスにファイルが無い。
        """
        if not self._launcher_path.exists():
            raise DataLoaderLauncherNotFoundError(self._launcher_path)

        command = [str(self._launcher_path), *args]
        try:
            completed = subprocess.run(
                command,
                cwd=None if cwd is None else str(cwd),
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired as e:
            raise DataLoaderTimeoutError(self._launcher_path, self._timeout_seconds) from e

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        if completed.returncode != 0:
            raise DataLoaderExecutionError(
                self._launcher_path, completed.returncode, stdout, stderr
            )

        success_table = self._read_result_csv(success_csv)
        error_table = self._read_result_csv(error_csv)
        return DataLoaderResult(
            success=success_table,
            errors=error_table,
            returncode=completed.returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def _read_result_csv(self, path: str | Path | None) -> Table:
        """``success_csv`` / ``error_csv`` を ``Table`` に読み込む。

        ``None`` のときは空の ``Table``。指定されたパスにファイルが無いと
        ``DataLoaderResultFileMissingError``。ファイルが有るときは ``CSV`` で読む。
        0 バイトファイル・ヘッダーのみのケースは ``CSV`` クラスの既存動作に任せる。
        """
        if path is None:
            return Table([], [])
        result_path = Path(path)
        if not result_path.exists():
            raise DataLoaderResultFileMissingError(result_path)
        with CSV(result_path, read_only=True) as csv_file:
            return csv_file.read()
