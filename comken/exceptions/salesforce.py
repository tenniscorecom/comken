"""comken/exceptions/salesforce.py — Salesforce API の呼び出しに関する例外。

SalesforceError はカテゴリ基底。直接送出しない。
"""

from comken.exceptions.base import ComkenError


class SalesforceError(ComkenError):
    """Salesforce に関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


# 呼び出し側が型で分岐するエラーはカテゴリにまとめない


class SalesforceAuthError(SalesforceError):
    """Salesforce にログインできない

    発生箇所: comken.toolbox.salesforce.SalesforceBase の認証時（初回・401 後の取り直し）

    対処:
        表示された確認項目を上から順に見る。それでも直らなければ管理者へ連絡する
    """

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(
            f"Salesforce の認証に失敗しました（HTTP {status_code}）: {detail}\n"
            "次を順に確認してください。\n"
            "  1. 選択した OAuth 方式と ECA 側で有効なフローが一致しているか\n"
            "  2. client_id / client_secret と、必要なら refresh_token が正しいか\n"
            "  3. Client Credentials では実行ユーザー（Run As）が指定されているか\n"
            "  4. Refresh Token では初回認可、失効ポリシー、secret 必須設定が正しいか\n"
            "  5. domain_url が My Domain の URL か\n"
            "     （login.salesforce.com では動きません）"
        )


class SalesforceRequestError(SalesforceError):
    """Salesforce が処理を断った

    発生箇所: comken.toolbox.salesforce.SalesforceBase の全リクエスト

    対処:
        表示されたメッセージをそのまま添えて管理者へ連絡する（権限か項目名の問題が多い）
    """

    def __init__(self, method: str, path: str, status_code: int, detail: str) -> None:
        super().__init__(
            f"Salesforce API がエラーを返しました（HTTP {status_code}）: {method} {path}\n"
            f"{detail}\n"
            "オブジェクト名・項目名・レコード Id と、実行ユーザーの権限を確認してください。"
        )
        # 呼び出し側がプログラムから HTTP コードとリクエスト情報で判定できるように
        # 残しておく。メッセージ生成の振る舞いは変えず、追加の属性を備えるだけにする
        self.method = method
        self.path = path
        self.status_code = status_code
        self.detail = detail


class SalesforceReportTruncatedError(SalesforceError):
    """レポートが上限の 2000 行で切れた（**全件ではない**）

    レポート API は同期・非同期とも 2000 行が上限。非同期にしても超えられない。
    黙って欠けたデータで処理を続けないよう、既定ではこの例外で止める。

    発生箇所: comken.toolbox.salesforce.ReportAPI.run() / run_async()

    対処:
        期間を狭めて何回かに分けて実行する。1回で全部必要なら管理者へ連絡する
    """

    def __init__(self, report_id: str, row_limit: int) -> None:
        super().__init__(
            f"レポートの行が上限（{row_limit} 行）で切り捨てられました: {report_id}\n"
            "取得できたのは全件ではありません。次のいずれかで対処してください。\n"
            "  1. filters で日付などを区切り、複数回に分けて取得する\n"
            "  2. 同じ内容を SOQL（query）で取得する\n"
            "  3. 欠けたままでよい場合だけ allow_truncated=True を指定する"
        )


class SalesforceReportIDNotFoundError(SalesforceError):
    """レポートの URL からレポート ID を取り出せない

    管理表にはレポートの URL をそのまま貼れるようにしてあるが、
    貼られたものが Salesforce のレポート URL でないと ID を取り出せない。

    発生箇所: comken.toolbox.salesforce.report.report_id_from_url()
             （呼び出し元の例: comken-salesforce-downloader の master.py。
             comken.toolbox.browser.sites.salesforce.base
             .SalesforceReportBrowser.export_reports() も
             同じ report_id_from_url() を呼ぶ）

    対処:
        Salesforce でレポートを開いたときのアドレスを、そのまま貼り直す
    """

    def __init__(self, text: str) -> None:
        super().__init__(
            f"レポート ID を取り出せませんでした: {text}\n"
            "Salesforce でレポートを開いたときのアドレス（.../Report/00O.../view）を、\n"
            "そのまま貼り付けてください。レポート ID（00O で始まる 15 桁か 18 桁）を"
            "直接書いても構いません。"
        )
