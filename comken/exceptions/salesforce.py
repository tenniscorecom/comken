"""Salesforce API の呼び出しに関する例外。"""

from .base import ComkenError


class SalesforceError(ComkenError):
    """Salesforce に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class SalesforceAuthError(SalesforceError):
    """Salesforce にログインできない

    発生箇所: comken.salesforce.Salesforce の認証時（初回・401 後の取り直し）

    対処:
        表示された確認項目を上から順に見る。それでも直らなければ管理者へ連絡する
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
    """Salesforce につながらない

    発生箇所: comken.salesforce.Salesforce の全リクエスト

    対処:
        ネットワークの状態を確認して、少し待ってから再実行する
    """

    def __init__(self, url: str, detail: Exception) -> None:
        super().__init__(
            f"Salesforce に接続できませんでした: {url}\n"
            f"（{detail}）\n"
            "ネットワーク接続と URL を確認してください。"
        )


class SalesforceRequestError(SalesforceError):
    """Salesforce が処理を断った

    発生箇所: comken.salesforce.Salesforce の全リクエスト

    対処:
        表示されたメッセージをそのまま添えて管理者へ連絡する（権限か項目名の問題が多い）
    """

    def __init__(self, method: str, path: str, status_code: int, detail: str) -> None:
        super().__init__(
            f"Salesforce API がエラーを返しました（HTTP {status_code}）: {method} {path}\n"
            f"{detail}\n"
            "オブジェクト名・項目名・レコード Id と、実行ユーザーの権限を確認してください。"
        )


class SalesforceExternalIdMissingError(SalesforceError):
    """upsert 用データに外部 ID がない

    対処:
        管理者へ連絡する
    """

    def __init__(self, object_name: str, external_id_field: str) -> None:
        super().__init__(
            f"Salesforce の upsert データに外部 ID 項目がありません: "
            f"{object_name}.{external_id_field}\n"
            f"data に {external_id_field} の値を含めてください。"
        )


class SalesforceCredentialRotationError(SalesforceError):
    """consumer key / secret のローテーションを安全に完了できない場合。"""

    def __init__(self, detail: str) -> None:
        super().__init__(
            "Salesforce の認証情報をローテーションできませんでした。\n"
            f"{detail}\n"
            "旧認証情報はまだ有効です。Salesforce の ECA 設定、API レスポンス、"
            "DPAPI の保存先を確認してください。"
        )


class SalesforceReportTruncatedError(SalesforceError):
    """レポートが上限の 2000 行で切れた（**全件ではない**）

    レポート API は同期・非同期とも 2000 行が上限。非同期にしても超えられない。
    黙って欠けたデータで処理を続けないよう、既定ではこの例外で止める。

    発生箇所: comken.salesforce.ReportApi.run() / run_async()

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


class SalesforceReportFormatError(SalesforceError):
    """レポートの形式が対応していない

    集計（サマリ・マトリックス）形式は行の入れ物の構造が変わり、
    そのまま読むと無言で空を返すため、明示的に弾く。

    発生箇所: comken.salesforce.ReportApi.run() / run_async()

    対処:
        レポートを明細形式にするか、管理者へ連絡する
    """

    def __init__(self, report_id: str, report_format: str) -> None:
        super().__init__(
            f"このレポートは {report_format} 形式です: {report_id}\n"
            "取得できるのは明細（TABULAR）形式のレポートだけです。\n"
            "レポート側を明細形式に変更するか、SOQL（query）で取得してください。"
        )


class SalesforceReportExecutionError(SalesforceError):
    """Salesforce 側でレポート実行に失敗した

    対処:
        Salesforce で同じレポートを直接実行し、表示された内容を管理者へ連絡する
    """

    def __init__(self, report_id: str, detail: str) -> None:
        super().__init__(
            f"Salesforce のレポート実行に失敗しました: {report_id}\n"
            f"{detail}\n"
            "Salesforce でレポートを直接実行し、条件・権限・参照項目を確認してください。"
        )
