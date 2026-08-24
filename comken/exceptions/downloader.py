"""comken/exceptions/downloader.py — Salesforce レポートの集約ダウンローダーの例外。

管理表（Excel）と履歴（CSV）に関する失敗をここにまとめる。
Salesforce との通信そのものの失敗は salesforce.py の例外を使う。
"""

from pathlib import Path

from comken.exceptions.base import ComkenError


class DownloaderError(ComkenError):
    """Salesforce レポートの集約取得に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
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


class HistoryHeaderMismatchError(DownloaderError):
    """ダウンロード履歴CSVの見出しが現在の定義と一致しない

    対処:
        履歴CSVの1行目を確認する。列を手で変更していた場合は元へ戻し、
        古い形式の履歴なら別名へ退避してから再実行する
    """

    def __init__(self, path: Path, actual: tuple[str, ...], expected: tuple[str, ...]) -> None:
        actual_text = "、".join(actual) or "（見出しなし）"
        expected_text = "、".join(expected)
        super().__init__(
            f"ダウンロード履歴の見出しが正しくありません: {path}\n"
            f"現在: {actual_text}\n"
            f"必要: {expected_text}"
        )


class ReportNotRegisteredError(DownloaderError):
    """指定した管理番号が管理表に無い

    管理番号はコードに定数で書く（CUSTOMER_LIST = "1001"）。管理表から行を消したり、
    番号を打ち間違えたりすると、どのレポートを指しているか決められない。

    発生箇所: comken.services.salesforce_downloader の download_report()

    対処:
        管理表を開いて、その管理番号の行があるか確認する。
        新しく使うレポートは、先に管理表へ登録する
    """

    def __init__(self, report_key: str, registered: list[str], master_path: Path) -> None:
        known = "、".join(str(key) for key in registered) or "（登録なし）"
        super().__init__(
            f"管理表に登録されていない管理番号です: {report_key}\n"
            f"登録済みの管理番号: {known}\n"
            f"管理表: {master_path}"
        )


class InvalidReportURLError(DownloaderError):
    """管理表の URL から Salesforce のレポート ID を取り出せない

    貼られたものが Salesforce のレポート URL でないと、どのレポートか決められない。

    発生箇所: comken.services.salesforce_downloader の管理表読み込み

    対処:
        Salesforce でレポートを開いたときのアドレスを、そのまま貼り直す
    """

    def __init__(self, report_key: str, url: str, reason: str) -> None:
        super().__init__(
            f"管理番号 {report_key} の Salesforce URL が正しくありません: {url}\n{reason}"
        )


class ReportDisabledError(DownloaderError):
    """管理表で「無効」になっているレポートを取ろうとした

    使うのをやめたレポートは、行を消さずに「無効」にして履歴との対応を残す。
    無効のものを黙って取りに行くと、やめたはずの取得が続いてしまう。

    発生箇所: comken.services.salesforce_downloader の download_report()

    対処:
        また使うなら管理表の「有効」を「有効」に戻す。
        使わないなら、呼び出し側のコードから消す
    """

    def __init__(self, report_key: str, summary: str, master_path: Path) -> None:
        super().__init__(
            f"このレポートは無効になっています: {report_key}（{summary}）\n"
            f"管理表: {master_path}\n"
            "また使うなら「有効」列を有効に戻してください。"
        )


class CachedReportNotRegisteredError(DownloaderError):
    """定期取得の対象ではないレポートのキャッシュを読もうとした

    cached_report() は「定期実行が取っておいた本日のデータを受け取る」関数。
    管理表で「個別」になっているレポートは誰も取りに行かないので、いつまでも揃わない。

    発生箇所: comken.services.salesforce_downloader の cached_report()

    対処:
        毎日決まった時刻に取るなら、管理表の「実行方式」を「定期」にする。
        使うときに毎回取りに行くなら、download_report() を呼ぶ
    """

    def __init__(self, report_key: str, summary: str, schedule: str, master_path: Path) -> None:
        super().__init__(
            f"定期取得の対象ではありません: {report_key}（{summary}）\n"
            f"管理表の「実行方式」は「{schedule}」になっています: {master_path}\n"
            "毎日決まった時刻に取るなら「定期」に変えてください。\n"
            "使うときに毎回取りに行くなら、download_report() を呼んでください。"
        )


class CachedReportNotFoundError(DownloaderError):
    """本日の定期取得キャッシュが見つからない

    定期取得の時刻より前に呼ばれた、定期取得が失敗した、その日に管理表へ
    追加されて今日の分に間に合わなかった、のいずれか。

    **勝手に Salesforce へ取りに行かない。** cached_report() は
    「取っておいたものを受け取る」関数で、取りに行く関数ではない。
    ここで自動的に取りに行くと、定期取得が動いていないことに誰も気づかなくなる。

    発生箇所: comken.services.salesforce_downloader の cached_report()

    対処:
        Salesforce からCSVを手動取得し、画面に表示された正確なパス・ファイル名で置いて、
        同じ python main.py を再実行する
    """

    def __init__(self, report_key: str, summary: str, cache_path: Path) -> None:
        super().__init__(
            f"本日の定期取得キャッシュが見つかりません: {report_key}（{summary}）\n"
            "SalesforceからCSVを手動取得し、次の正確なパス・ファイル名で置いてください:\n"
            f"{cache_path}\n"
            "配置後、同じ python main.py を再実行してください。"
        )


class EmptyReportError(DownloaderError):
    """レポートは実行できたが明細が 0 行だった

    空のファイルを置くと、使う側は「データが無い日」と「取得が失敗した日」を
    区別できなくなる。0 行のときはファイルを作らず、失敗として扱う。

    発生箇所: comken.services.salesforce_downloader の download_report()

    対処:
        Salesforce の画面で同じレポートを開き、本当に 0 件か確認する。
        0 件が正常に起こるレポートなら、管理表の「0件あり」を「○」にする。
    """

    def __init__(self, report_key: str, summary: str, url: str) -> None:
        super().__init__(
            f"レポートの明細が 0 行でした: {report_key}（{summary}）\n"
            f"{url}\n"
            "取得の失敗と区別できないため、ファイルは作りません。"
        )


class ReportFolderNotFoundError(DownloaderError):
    """管理表に書かれた保存先のフォルダが無い

    無いフォルダを作らないのは、書き間違いのことが多いため。
    勝手に作ると、誰も読まない場所へ置き続けることになる。

    発生箇所: comken.services.salesforce_downloader の download_report()

    対処:
        管理表の「保存先」を確認する。共有フォルダなら、
        つながっているか・権限があるかも確認する
    """

    def __init__(self, report_key: str, folder: Path) -> None:
        super().__init__(
            f"保存先のフォルダがありません: {report_key}\n"
            f"{folder}\n"
            "管理表の「保存先」を確認してください。\n"
            "共有フォルダの場合は、つながっているか（権限があるか）も確認してください。"
        )


class ScheduledDownloadFailedError(DownloaderError):
    """定期取得で1件以上が失敗した

    取得できたものは保存済み。**1件失敗しても残りは続けたうえで、最後にまとめて知らせる。**
    ログだけに出して正常終了すると、スケジューラや RPA 基盤から見て成功と区別が付かず、
    落ちていることに誰も気づかない。

    発生箇所: comken.services.salesforce_downloader の download_scheduled()

    対処:
        履歴（ダウンロード履歴.csv）の「エラー内容」で、失敗した理由を確認する。
        急いで必要なものは download_report() でその場で取得する
    """

    def __init__(self, failed_keys: list[str], history_path: Path) -> None:
        keys = "、".join(str(key) for key in failed_keys)
        super().__init__(
            f"定期取得で {len(failed_keys)} 件が失敗しました: {keys}\n"
            f"失敗した理由は履歴を確認してください: {history_path}"
        )
