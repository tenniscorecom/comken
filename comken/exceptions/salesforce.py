"""comken/exceptions/salesforce.py — Salesforce API の呼び出しに関する例外。"""

from comken.exceptions.base import ComkenError


class SalesforceError(ComkenError):
    """Salesforce に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


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


class SalesforceConnectionError(SalesforceError):
    """Salesforce につながらない

    発生箇所: comken.toolbox.salesforce.SalesforceBase の全リクエスト

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


class SalesforceExternalIDMissingError(SalesforceError):
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
    """consumer key / secret のローテーションを安全に完了できない

    対処:
        Salesforce の ECA 設定・API レスポンス・DPAPI の保存先を確認する
    """

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


class SalesforceReportFormatError(SalesforceError):
    """レポートの形式が対応していない

    集計（サマリ・マトリックス）形式は行の入れ物の構造が変わり、
    そのまま読むと無言で空を返すため、明示的に弾く。

    発生箇所: comken.toolbox.salesforce.ReportAPI.run() / run_async()

    対処:
        レポートを明細形式にするか、管理者へ連絡する
    """

    def __init__(self, report_id: str, report_format: str) -> None:
        super().__init__(
            f"このレポートは {report_format} 形式です: {report_id}\n"
            "取得できるのは明細（TABULAR）形式のレポートだけです。\n"
            "レポート側を明細形式に変更するか、SOQL（query）で取得してください。"
        )


class SalesforceSiteNotFoundError(SalesforceError):
    """URL のドメインに対応する組織が登録されていない

    管理表には複数の組織のレポート URL が混ざる。どの組織へつなぐかは
    URL のドメインで決めるので、未登録のドメインでは接続先を選べない。

    発生箇所: comken.toolbox.salesforce.sites.site_for()

    対処:
        URL のドメインを見直す。新しい組織なら管理者へ連絡する
        （組織クラスの追加が要る）
    """

    def __init__(self, url: str, known_domains: list[str]) -> None:
        known = "\n".join(f"  {domain}" for domain in known_domains) or "  （登録なし）"
        super().__init__(
            f"この URL の組織が登録されていません: {url}\n"
            f"登録済みの組織:\n{known}\n"
            "レポートを開いたときのアドレスをそのまま貼ってください。\n"
            "新しい組織の場合は、組織クラスの追加が必要です（管理者へ連絡してください）。"
        )


class SalesforceReportIDNotFoundError(SalesforceError):
    """レポートの URL からレポート ID を取り出せない

    管理表にはレポートの URL をそのまま貼れるようにしてあるが、
    貼られたものが Salesforce のレポート URL でないと ID を取り出せない。

    発生箇所: comken.toolbox.salesforce.report.report_id_from_url()
             （呼び出し元の例: comken-salesforce-downloader の master.py。
             2026-08-30 に comken から分離した別リポジトリ）

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


class SalesforceReportAccessDeniedError(SalesforceError):
    """レポート API（Reports and Dashboards REST API）へのアクセスを拒否された

    Salesforce はこの API を「Analytics API」と呼ぶことがあり、別ライセンス製品の
    CRM Analytics（旧 Einstein Analytics / Tableau CRM）と紛らわしい。
    このエラーは comken が誤ったエンドポイントを叩いたのではなく、
    Reports and Dashboards REST API そのものへのアクセスが HTTP 401 / 403 で
    拒否された場合に出る。メッセージの文言ではなくステータスコードで判定する。

    発生箇所: comken.toolbox.salesforce.report.ReportAPI の全メソッド
              （get / run_csv / run_async / describe）

    対処:
        Salesforce 管理者に、実行ユーザー（Client Credentials では Run As ユーザー）
        について次を確認してもらう。
          1. Profile / Permission Set に「API Enabled」権限があるか
          2. 対象のレポート・レポートフォルダへのアクセス権があるか
          3. 組織の Edition・ライセンスが Reports and Dashboards REST API
             に対応しているか（一部の制限ライセンスでは使えない）
    """

    def __init__(self, report_id: str, status_code: int, detail: str) -> None:
        super().__init__(
            f"Salesforce のレポート API（Analytics API）へのアクセスが"
            f"拒否されました（HTTP {status_code}）: {report_id}\n"
            f"{detail}\n"
            "Salesforce 管理者に、実行ユーザーの「API Enabled」権限・"
            "レポートへのアクセス権・組織の Edition が Reports and Dashboards "
            "REST API に対応しているかを確認してもらってください。"
        )
