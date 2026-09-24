"""comken/exceptions/dataloader.py — Salesforce Data Loader CLI 呼び出しの例外。"""

from pathlib import Path

from comken.exceptions.base import ComkenError


class DataLoaderError(ComkenError):
    """Data Loader の実行に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class DataLoaderTimeoutError(DataLoaderError):
    """Data Loader の実行が制限時間内に終わらなかった

    ``timeout_seconds`` を超えてもプロセスが生きている。大量データを処理する場合
    は既定値（3600秒 = 1時間）でも足りないことがある。

    対処:
        処理対象の件数を減らすか、``timeout_seconds`` を長くする。
        プロセスがハングしている場合はタスクマネージャーから Data Loader の
        プロセスを終了させる
    """

    def __init__(self, launcher_path: Path | str, timeout_seconds: float) -> None:
        super().__init__(
            f"Data Loader の実行が {timeout_seconds:.1f} 秒以内に終わりませんでした: "
            f"{launcher_path}\n"
            "処理対象の件数を減らすか、timeout_seconds を長くしてください。"
        )


class DataLoaderExecutionError(DataLoaderError):
    """Data Loader が 0 以外の終了コードで終わった

    Data Loader プロセス自体が起動・実行に失敗した場合に出る。
    **1件1件のレコードの成否とは別**（個別レコードの失敗は
    ``DataLoaderResult.errors`` で確認する。プロセス自体は正常終了しつつ
    一部レコードだけ失敗するのは普通に起きることなので、ここでは例外にしない）。

    対処:
        表示された標準出力・標準エラー出力を確認する。``config.properties``・
        ``process-conf.xml`` の設定を見直す。よくある原因はログイン情報の誤り、
    SOQL のフィールド名不一致、書き出し先パスへの権限不足
    """

    def __init__(
        self,
        launcher_path: Path | str,
        returncode: int,
        stdout: str,
        stderr: str,
    ) -> None:
        super().__init__(
            f"Data Loader が 0 以外の終了コードで終了しました: {launcher_path}\n"
            f"returncode: {returncode}\n"
            f"--- stdout ---\n{stdout}\n"
            f"--- stderr ---\n{stderr}\n"
            "config.properties・process-conf.xml の設定と、表示された"
            "標準出力・標準エラー出力を確認してください。"
        )
