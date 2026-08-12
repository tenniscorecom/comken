"""Salesforce API の呼び出しに関する例外。"""

from .base import ComkenError


class SalesforceError(ComkenError):
    """Salesforce に関する例外をまとめて捕捉するための基底クラス。"""


class SalesforceAuthError(SalesforceError):
    """アクセストークンを取得できない場合。

    発生箇所: comken.salesforce.Salesforce の認証時（初回・401 後の取り直し）
    """

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(
            f"Salesforce の認証に失敗しました（HTTP {status_code}）: {detail}\n"
            "次を順に確認してください。\n"
            "  1. client_id / client_secret が正しいか\n"
            "  2. 接続アプリで「クライアントクレデンシャルフローを有効化」にチェックがあるか\n"
            "  3. 接続アプリのポリシーで「実行ユーザー（Run As）」を指定しているか\n"
            "     （未指定だと invalid_grant になります）\n"
            "  4. domain_url が My Domain の URL か\n"
            "     （login.salesforce.com では動きません）"
        )


class SalesforceConnectionError(SalesforceError):
    """ネットワークの問題で Salesforce に接続できない場合。

    発生箇所: comken.salesforce.Salesforce の全リクエスト
    """

    def __init__(self, url: str, detail: Exception) -> None:
        super().__init__(
            f"Salesforce に接続できませんでした: {url}\n"
            f"（{detail}）\n"
            "ネットワーク接続と URL を確認してください。"
        )


class SalesforceRequestError(SalesforceError):
    """Salesforce API がエラーを返した場合。

    発生箇所: comken.salesforce.Salesforce の全リクエスト
    """

    def __init__(self, method: str, path: str, status_code: int, detail: str) -> None:
        super().__init__(
            f"Salesforce API がエラーを返しました（HTTP {status_code}）: {method} {path}\n"
            f"{detail}\n"
            "オブジェクト名・項目名・レコード Id と、実行ユーザーの権限を確認してください。"
        )


class SalesforceReportTruncatedError(SalesforceError):
    """レポートの行が上限で切り捨てられた場合。

    レポート API は同期・非同期とも 2000 行が上限。非同期にしても超えられない。
    黙って欠けたデータで処理を続けないよう、既定ではこの例外で止める。

    発生箇所: comken.salesforce.ReportApi.run() / run_async()
    """

    def __init__(self, report_id: str, row_limit: int) -> None:
        super().__init__(
            f"レポートの行が上限（{row_limit} 行）で切り捨てられました: {report_id}\n"
            "取得できたのは全件ではありません。次のいずれかで対処してください。\n"
            "  1. filters で日付などを区切り、複数回に分けて取得する\n"
            "  2. 同じ内容を SOQL（query）で取得する\n"
            "  3. 欠けたままでよい場合だけ allow_truncated=True を指定する"
        )


class SalesforceReportFormatError(SalesforceError):
    """明細（TABULAR）以外の形式のレポートを取得しようとした場合。

    集計（サマリ・マトリックス）形式は行の入れ物の構造が変わり、
    そのまま読むと無言で空を返すため、明示的に弾く。

    発生箇所: comken.salesforce.ReportApi.run() / run_async()
    """

    def __init__(self, report_id: str, report_format: str) -> None:
        super().__init__(
            f"このレポートは {report_format} 形式です: {report_id}\n"
            "取得できるのは明細（TABULAR）形式のレポートだけです。\n"
            "レポート側を明細形式に変更するか、SOQL（query）で取得してください。"
        )
