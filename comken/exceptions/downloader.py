"""comken/exceptions/downloader.py — Salesforce レポートの集約ダウンローダーの例外。

管理表（Excel）と履歴（CSV）に関する失敗をここにまとめる。
Salesforce との通信そのものの失敗は salesforce.py の例外を使う。
"""

from pathlib import Path

from .base import ComkenError


class DownloaderError(ComkenError):
    """Salesforce レポートの集約取得に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class ReportNotRegisteredError(DownloaderError):
    """指定した管理番号が管理表に無い

    管理番号はコードに定数で書く（CUSTOMER_LIST = 1001）。管理表から行を消したり、
    番号を打ち間違えたりすると、どのレポートを指しているか決められない。

    発生箇所: comken.services.salesforce_downloader の download_report()

    対処:
        管理表を開いて、その管理番号の行があるか確認する。
        新しく使うレポートは、先に管理表へ登録する
    """

    def __init__(self, report_key: int, registered: list[int], master_path: Path) -> None:
        known = "、".join(str(key) for key in registered) or "（登録なし）"
        super().__init__(
            f"管理表に登録されていない管理番号です: {report_key}\n"
            f"登録済みの管理番号: {known}\n"
            f"管理表: {master_path}"
        )


class InvalidReportUrlError(DownloaderError):
    """管理表の URL から Salesforce のレポート ID を取り出せない

    貼られたものが Salesforce のレポート URL でないと、どのレポートか決められない。

    発生箇所: comken.services.salesforce_downloader の管理表読み込み

    対処:
        Salesforce でレポートを開いたときのアドレスを、そのまま貼り直す
    """

    def __init__(self, report_key: int, url: str, reason: str) -> None:
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

    def __init__(self, report_key: int, summary: str, master_path: Path) -> None:
        super().__init__(
            f"このレポートは無効になっています: {report_key}（{summary}）\n"
            f"管理表: {master_path}\n"
            "また使うなら「有効」列を有効に戻してください。"
        )


class ScheduledReportNotRegisteredError(DownloaderError):
    """定期取得の対象として登録されていないレポートを、定期取得済みとして受け取ろうとした

    get_scheduled_report() は「決まった時刻に取っておいたものを受け取る」関数。
    管理表で「個別」になっているレポートは誰も取りに行かないので、いつまでも揃わない。

    発生箇所: comken.services.salesforce_downloader の get_scheduled_report()

    対処:
        毎日決まった時刻に取るなら、管理表の「実行方式」を「定期」にする。
        使うときに毎回取りに行くなら、download_report() を呼ぶ
    """

    def __init__(self, report_key: int, summary: str, schedule: str, master_path: Path) -> None:
        super().__init__(
            f"定期取得の対象ではありません: {report_key}（{summary}）\n"
            f"管理表の「実行方式」は「{schedule}」になっています: {master_path}\n"
            "毎日決まった時刻に取るなら「定期」に変えてください。\n"
            "使うときに毎回取りに行くなら、download_report() を呼んでください。"
        )


class ScheduledReportNotDownloadedError(DownloaderError):
    """本日の定期取得がまだ済んでいない

    定期取得の時刻より前に呼ばれた、定期取得が失敗した、その日に管理表へ
    追加されて今日の分に間に合わなかった、のいずれか。

    **勝手に Salesforce へ取りに行かない。** get_scheduled_report() は
    「取っておいたものを受け取る」関数で、取りに行く関数ではない。
    ここで自動的に取りに行くと、定期取得が動いていないことに誰も気づかなくなる。

    発生箇所: comken.services.salesforce_downloader の get_scheduled_report()

    対処:
        定期取得の実行結果を確認する。急ぐ場合は download_report() で
        その場で取得する（そのぶん Salesforce への呼び出しが増える）
    """

    def __init__(self, report_key: int, summary: str, history_path: Path) -> None:
        super().__init__(
            f"本日の定期取得がまだ済んでいません: {report_key}（{summary}）\n"
            f"履歴: {history_path}\n"
            "定期取得の実行結果を確認してください。\n"
            "急ぐ場合は download_report() でその場で取得できます。"
        )


class ReportFileMissingError(DownloaderError):
    """履歴では取得済みだが、保存先にファイルが無い

    取得の後で人が消した・移動した・保存先の設定を変えた、のいずれか。

    発生箇所: comken.services.salesforce_downloader の get_scheduled_report()

    対処:
        保存先のフォルダを確認する。消してしまった場合は
        download_report() で取り直す
    """

    def __init__(self, report_key: int, path: Path) -> None:
        super().__init__(
            f"履歴では取得済みですが、ファイルが見つかりません: {report_key}\n"
            f"{path}\n"
            "消した・移動した場合は download_report() で取り直してください。"
        )


class EmptyReportError(DownloaderError):
    """レポートは実行できたが明細が 0 行だった

    空のファイルを置くと、使う側は「データが無い日」と「取得が失敗した日」を
    区別できなくなる。0 行のときはファイルを作らず、失敗として扱う。

    発生箇所: comken.services.salesforce_downloader の download_report()

    対処:
        Salesforce の画面で同じレポートを開き、本当に 0 件か確認する。
        本当に 0 件の日であれば、空の CSV を保存先へ手で置く
    """

    def __init__(self, report_key: int, summary: str, url: str) -> None:
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

    def __init__(self, report_key: int, folder: Path) -> None:
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

    def __init__(self, failed_keys: list[int], history_path: Path) -> None:
        keys = "、".join(str(key) for key in failed_keys)
        super().__init__(
            f"定期取得で {len(failed_keys)} 件が失敗しました: {keys}\n"
            f"失敗した理由は履歴を確認してください: {history_path}"
        )
