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


class ReportNotRegisteredError(DownloaderError):
    """指定した管理番号が管理表に無い

    管理番号はコードに定数で書く（CUSTOMER_LIST = "1001"）。管理表から行を消したり、
    番号を打ち間違えたりすると、どのレポートを指しているか決められない。

    発生箇所: Salesforceレポートダウンローダー の download_scheduled() /
    comken.services.salesforce_downloader の cached_report()

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


class GroupNotRegisteredError(DownloaderError):
    """管理表の「グループ」列に設定シートに登録されていない値が書かれている

    出力先フォルダは「グループ→ベースパス」の対応を、設定シート（レポート管理表
    と同じブック内の「設定」シート）で管理する。管理表にないグループ名が書かれて
    いると、出力先を決められない。

    発生箇所: comken.services.salesforce_downloader.provider の report_folder()

    対処:
        管理表の「グループ」列に書かれた値が、設定シート（`group_settings.py` の
        `GroupSetting`）の「グループ」列に存在するか確認する。新しく部署・グループを
        追加するときは、設定シート側にも同じ名前で行を足す
    """

    def __init__(self, group: str, registered: list[str], master_path: Path) -> None:
        known = "、".join(registered) or "（登録なし）"
        super().__init__(
            f"管理表の「グループ」列に設定されていないグループ名です: {group}\n"
            f"設定シートに登録済みのグループ: {known}\n"
            f"管理表: {master_path}"
        )


class SoqlReportNotRegisteredError(DownloaderError):
    """管理表の「SOQL」列が「○」なのに、同じ管理番号の SoqlReport が登録されていない

    管理表と ``SOQL_REPORTS`` は別々に編集できるため、「SOQL」列だけ「○」にして
    ``SoqlReport`` の追加・登録（``soql_reports/_registry.py``）を忘れると、
    どの SOQL クエリを使えばいいか決められない。

    発生箇所: comken.services.salesforce_downloader.soql_reports の soql_report_for()

    対処:
        管理番号に対応する ``SoqlReport`` サブクラスを追加し、``KEY`` を管理表と
        同じ値にして ``soql_reports/_registry.py`` の ``SOQL_REPORTS`` へ登録する。
        まだ SOQL 化していないなら、管理表の「SOQL」列を「×」に戻す
    """

    def __init__(self, report_key: str, registered: list[str]) -> None:
        known = "、".join(str(key) for key in registered) or "（登録なし）"
        super().__init__(
            f"管理番号 {report_key} はSOQL列が「○」ですが、SoqlReportが登録されていません。\n"
            f"登録済みのSOQL管理番号: {known}"
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

    発生箇所: comken.services.salesforce_downloader の cached_report() / cached_report_path()

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

    発生箇所: Salesforceレポートダウンローダー の download_scheduled()

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
    """保存先として組み立てたフォルダが無い

    保存先フォルダは、管理表の「グループ」で引いた設定シートの「ベースURL」（フォルダのパス）
    そのものである（`provider.report_folder()`）。そのフォルダが存在しない場合にこの例外になる。
    無いフォルダを作らないのは、書き間違いのことが多いため。
    勝手に作ると、誰も読まない場所へ置き続けることになる。

    発生箇所: Salesforceレポートダウンローダー の download_scheduled()

    対処:
        設定シートの「ベースURL」（フォルダのパス）と、管理表の「グループ」を
        確認する。共有フォルダなら、つながっているか・権限があるかも確認する
    """

    def __init__(self, report_key: str, folder: Path) -> None:
        super().__init__(
            f"保存先のフォルダがありません: {report_key}\n"
            f"{folder}\n"
            "設定シートの「ベースURL」（フォルダのパス）と、管理表の「グループ」を"
            "確認してください。\n"
            "共有フォルダの場合は、つながっているか（権限があるか）も確認してください。"
        )


class ReportReservePathLimitError(DownloaderError):
    """保存ファイル名の連番が上限に達した

    `_reserve_path()` は同じフォルダに既存ファイルがあると連番を足して別の
    ファイル名を探す。 上限（ ``RESERVE_PATH_LIMIT`` ）まで試しても確保できない
    のは権限・同期の異常など、運用側に原因があることが多い。

    発生箇所: Salesforceレポートダウンローダー の _reserve_path()

    対処:
        保存先フォルダが想定どおりか確認する。 共有フォルダなら、 古い取得
        ファイルを退避するか、 別の保存先に変える。 連発する場合は権限・排他
        制御の設定も見直す
    """

    def __init__(self, report_key: str, base_path: Path, limit: int) -> None:
        super().__init__(
            f"保存ファイル名の連番が上限に達しました: {report_key}\n"
            f"{base_path}\n"
            f"{limit} 回試しても空きのファイル名が見つかりませんでした。\n"
            "保存先フォルダの権限・排他制御と、 古い取得ファイルの数を確認してください。"
        )


class ScheduledDownloadFailedError(DownloaderError):
    """定期取得で1件以上が失敗した

    取得できたものは保存済み。**1件失敗しても残りは続けたうえで、最後にまとめて知らせる。**
    ログだけに出して正常終了すると、スケジューラや RPA 基盤から見て成功と区別が付かず、
    落ちていることに誰も気づかない。

    発生箇所: Salesforceレポートダウンローダー の download_scheduled()

    対処:
        履歴（ダウンロード履歴.csv）の「エラー内容」で、失敗した理由を確認する。
        急いで必要なものは download_scheduled() をスケジュール外で実行する。
        権限を持つ人が Salesforce から手動でダウンロードしてもよい
    """

    def __init__(self, failed_keys: list[str], history_path: Path) -> None:
        keys = "、".join(str(key) for key in failed_keys)
        super().__init__(
            f"定期取得で {len(failed_keys)} 件が失敗しました: {keys}\n"
            f"失敗した理由は履歴を確認してください: {history_path}"
        )


class SoqlDownloadFailedError(DownloaderError):
    """SOQL レポートの取得で1件以上が失敗した

    取得できたものは保存済み。**1件失敗しても残りは続けたうえで、最後にまとめて知らせる。**
    `download_scheduled()` と同じ「ログだけだと気づけない」問題なので、最後に例外で
    上げる。``ScheduledDownloadFailedError`` は履歴 CSV の存在を前提にしたメッセージ
    になるため、履歴機能を持たない SOQL レポート経路ではこの例外を使う。

    発生箇所: comken.services.salesforce_downloader.soql_reports の download_soql_reports()

    対処:
        表示された管理番号について、SOQL クエリ・組織の認証情報・保存先フォルダの
        権限・ネットワークの状態を確認する。急いで必要なものは
        ``download_soql_reports()`` を直接実行してもよい
    """

    def __init__(self, failed_keys: list[str]) -> None:
        self.failed_keys = failed_keys
        keys = "、".join(str(key) for key in failed_keys)
        super().__init__(
            f"SOQL レポートの取得で {len(failed_keys)} 件が失敗しました: {keys}\n"
            "失敗した管理番号について、SOQL クエリ・組織の認証情報・保存先フォルダの"
            "権限・ネットワークの状態を確認してください。"
        )


class UnsupportedScheduleFrequencyError(DownloaderError):
    """管理表の「取得頻度」に、想定外の値が書かれている

    許容される値は ``毎日`` / ``毎週`` / ``毎月`` の3種類。
    それ以外（手書きのタイポ・想定外の列挙値）が入っていると判定できない。

    発生箇所: comken.services.salesforce_downloader.sheets.schedule の is_due()

    対処:
        管理表の「取得頻度」列の値を ``毎日`` / ``毎週`` / ``毎月`` の
        いずれかに修正する
    """

    def __init__(self, frequency: str) -> None:
        super().__init__(
            f"対応していない取得頻度です: {frequency}\n"
            "管理表の「取得頻度」列の値を 毎日 / 毎週 / 毎月 の"
            "いずれかに修正してください。"
        )


class ScheduleWeekdayInvalidError(DownloaderError):
    """管理表の「曜日」列に想定外の値が入っている

    許容されるのは月〜日の漢字1文字（「月」「火」「水」「木」「金」「土」「日」）
    または「〜曜日」の接尾辞付き表記。

    発生箇所: comken.services.salesforce_downloader.sheets.schedule の ScheduleRule.weekday

    対処:
        管理表の「曜日」列の値を月〜日のいずれかに修正する（「曜日」を付ける
        形式でも可）
    """

    def __init__(self, value: object) -> None:
        super().__init__(
            f"曜日が正しくありません: {value}\n"
            "管理表の「曜日」列の値を 月 / 火 / 水 / 木 / 金 / 土 / 日 の"
            "いずれかに修正してください（「曜日」を付ける形式でも可）。"
        )
