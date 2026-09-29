"""comken/exceptions/downloader.py — Salesforce レポートの履歴・読取に関する例外。

管理表・取得実行（`download_scheduled()`）は 2026-09 に comken の外
（`Salesforceレポートダウンローダー` リポジトリ）へ切り出した。comken 側に
残っているのは履歴の読み書きと管理番号での読取に関する例外。Salesforce との
通信そのものの失敗は web.py を使う。
"""

from pathlib import Path
from typing import TYPE_CHECKING

from comken.exceptions.base import ComkenError

if TYPE_CHECKING:
    pass


class DownloaderError(ComkenError):
    """Salesforce レポートの集約取得に関するエラー

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


class HistoryWriteError(DownloaderError):
    """必須のダウンロード履歴を記録できなかった

    対処:
        履歴CSVの保存先、共有サーバー接続、書込み権限を確認する
    """

    def __init__(self, path: Path, reason: str, *, original: BaseException | None = None) -> None:
        original_text = f"\n元の処理の失敗: {original}" if original is not None else ""
        super().__init__(f"ダウンロード履歴を記録できませんでした: {path}\n{reason}{original_text}")


class HistoryLockTimeoutError(DownloaderError):
    """ダウンロード履歴の排他ロックを待っても取得できなかった

    対処:
        同時実行中の処理が終わるのを待って再実行する。繰り返す場合は共有サーバーを確認する
    """

    def __init__(self, path: Path, timeout: float) -> None:
        super().__init__(
            f"ダウンロード履歴を利用できませんでした: {path}\n"
            f"履歴のロックを {timeout:.1f} 秒待っても取得できませんでした"
        )


class ReportNotDownloadedError(DownloaderError):
    """指定した管理番号の取得済みレポートが見つからない

    履歴に該当行が無い、最新の取得が失敗している、最新の取得は成功だが
    ファイルが消えている、のいずれか。**comken 側は勝手に Salesforce へ
    取りに行わない。**「取っておいたものを受け取る」だけの関数なので、
    ここで自動的に取りに行くと、定期取得が動いていないことに誰も気づか
    なくなる。

    発生箇所: comken.services.salesforce_downloader.history の
              report_path() / read_report()

    対処:
        定期取得（Salesforceレポートダウンローダー）が動いているか、
        ``ダウンロード履歴.csv`` を確認する。ファイルが消えている場合は
        メッセージに表示されたパスに復旧する。最新の取得が失敗している
        場合は、表示された実行日時・原因区分・エラー内容を見て対処する
        （定期取得のログ / Salesforce の状態 / 管理表 / 共有サーバー）
    """

    def __init__(
        self,
        report_key: str,
        missing_path: Path | None,
        history_path: Path,
        *,
        schedule_key: str | None = None,
        failed_at: str | None = None,
        failure: str | None = None,
    ) -> None:
        schedule_text = f"（スケジュールキー {schedule_key}）" if schedule_key else ""
        if failed_at is not None:
            # 最新の取得が失敗しているケース。古い成功行へ遡らず「取れていない」扱い。
            # 呼び出し側は「実行日時」が空でも表示用の文字列を渡す（原因の記録が空の行もあるため、
            # ``failure`` の有無では判定しない）
            cause_line = f"原因: {failure}" if failure else "原因: （記録なし）"
            message = (
                f"管理番号 {report_key}{schedule_text} の最新の取得"
                f"（{failed_at or '（日時不明）'}）が失敗しています。\n"
                f"{cause_line}\n"
                f"履歴: {history_path}\n"
                "Salesforceレポートダウンローダーの定期取得が動いているか、"
                "「ダウンロード履歴.csv」を確認してください。"
            )
        elif missing_path is None:
            message = (
                f"管理番号 {report_key}{schedule_text} の取得の履歴がありません。\n"
                f"履歴: {history_path}\n"
                "Salesforceレポートダウンローダーの定期取得が動いているか、"
                "「ダウンロード履歴.csv」を確認してください。"
            )
        else:
            message = (
                f"管理番号 {report_key}{schedule_text} の成功履歴はありますが、"
                "ファイルが消えています。\n"
                f"履歴が指していたパス: {missing_path}\n"
                f"履歴: {history_path}\n"
                "Salesforceレポートダウンローダーの定期取得が動いているか、"
                "「ダウンロード履歴.csv」を確認してください。"
            )
        super().__init__(message)
