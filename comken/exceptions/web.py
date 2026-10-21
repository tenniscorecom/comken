"""comken/exceptions/web.py — ブラウザ自動化と Salesforce 呼び出しに関する例外。"""

from comken.exceptions.base import ComkenError


class BrowserError(ComkenError):
    """ブラウザ操作に関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


class ElementNotFoundError(BrowserError):
    """画面の部品が時間内に見つからない

    selenium の TimeoutException を、どのセレクターで失敗したかが分かる形に包み直したもの。
    素の TimeoutException はメッセージにセレクターが入らず、ログから原因を追えないため。

    対処:
        もう一度実行する。サイトが重いだけのことが多い。毎回出るなら画面が変わった可能性があるので管理者へ（エラーに、どの部品を探していたかが出ます）
    """

    def __init__(self, locator: object, seconds: int, condition: str) -> None:
        super().__init__(
            f"要素が {seconds} 秒以内に{condition}ませんでした: {locator}\n"
            "次を確認してください:\n"
            "  1. 画面の HTML が変わってセレクターが古くなっていないか\n"
            "  2. 前の画面から遷移しきる前に操作していないか\n"
            "  3. iframe の中の要素ではないか（その場合は frame() で切り替えが必要）\n"
            "待つだけで解決する場合は wait_seconds を長くしてください。"
        )


class LoginFailedError(BrowserError):
    """ログインに失敗した（ユーザー名・パスワードが違う等）

    サイト固有の画面クラス（例: ``LoginPage.login()``）が、送信後もログイン
    画面のエラー表示を検知した場合に送出する。パスワード期限切れによる
    強制的な変更画面への遷移とは別の、単純な「認証情報が間違っている」
    失敗を表す。

    発生箇所: 利用プロジェクト側のログイン画面クラス（サイト固有の実装）

    対処:
        表示されたエラー内容（サイト側のエラーメッセージ）を確認する。
        DPAPI に保存した認証情報が古くなっていないか
        `python -m comken cred list` で確認し、必要なら
        `python -m comken cred gui` で登録し直す
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"ログインに失敗しました: {reason}")


class SalesforceError(ComkenError):
    """Salesforce に関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
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

    発生箇所: comken.toolbox.salesforce.report.ReportAPI.run_csv() / run_async()

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


class SalesforceReportFormatError(SalesforceError):
    """対応外形式、または明細の列が無いレポートで止めた

    明細を取れるのは ``TABULAR`` / ``SUMMARY`` / ``MATRIX`` の 3 形式で、
    それ以外（``MULTI_BLOCK`` などの結合レポート）は対応しないため明示的に
    止める。形式は対応内でも ``detailColumns`` が空（集計だけで明細が無い
    サマリー / マトリックス）のときもここに入る。無言で空の ``Table`` を
    「成功」として返さないための例外。

    メッセージ本文は旧来の ``SalesforceError`` の文言と同じままにしてあるため、
    ``str(exc)`` でログを見ていた既存テストや運用ログも壊れない。

    発生箇所: comken.toolbox.salesforce.report.ReportAPI.get() / run_async()
             （内部の ``_parse_report_payload``）

    対処:
        レポート形式を ``TABULAR`` / ``SUMMARY`` / ``MATRIX`` のいずれかに
        変えるか、SOQL（``query``）で取得してください。集計だけで明細が無い
        レポートのときは、SOQL で組み立て直すか、レポート定義に明細列を足して
        もらうかを管理者に相談してください
    """

    def __init__(self, report_id: str, report_format: str) -> None:
        super().__init__(
            f"このレポートは {report_format} 形式です: {report_id}\n"
            "取得できるのは明細（TABULAR）・サマリー（SUMMARY）・"
            "マトリックス（MATRIX）形式のレポートだけです。\n"
            "レポート形式を確認するか、SOQL（query）で取得してください。"
            "\n対処: レポート形式を確認するか、管理者へ連絡してください。"
        )
        # 利用側プログラムが型で分岐できるよう、レポート ID と形式の短い理由は
        # 属性としても持たせておく（メッセージからの抽出ではなく機械的に判定できる）
        self.report_id = report_id
        self.report_format = report_format


class SalesforceReportAccessDeniedError(SalesforceError):
    """レポート API（Analytics API）への権限が無い（HTTP 401 / 403）

    Reports and Dashboards REST API を叩いたときに 401 / 403 を返された
    場合に、汎用 ``SalesforceRequestError`` から専用のエラーへ差し替える。
    CRM Analytics と紛らわしいので、判定はメッセージ本文ではなく
    **HTTP ステータスコード（401 / 403）**だけで行う。401 は 1 回だけ
    再認証してからもう一度判定するので、再認証後の 401 も対象。

    メッセージ本文は旧来の ``SalesforceError`` の文言と同じままにしてあるため、
    ``str(exc)`` でログを見ていた既存テストや運用ログも壊れない。

    発生箇所: comken.toolbox.salesforce.report.ReportAPI.get() / run_async()
             / describe() の ``_request``（SalesforceRequestError を
             401 / 403 のときだけ入れ替える）

    対処:
        Salesforce 管理者に、refresh_token を発行したユーザーについて
        次を確認してもらってください:
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
            "\n対処: Salesforce 管理者に、refresh_token を発行したユーザーについて"
            "次を確認してもらってください。"
            "  1. Profile / Permission Set に「API Enabled」権限があるか"
            "  2. 対象のレポート・レポートフォルダへのアクセス権があるか"
            "  3. 組織の Edition・ライセンスが Reports and Dashboards REST API"
            "に対応しているか（一部の制限ライセンスでは使えない）"
        )
        # 401 / 403 以外の ``SalesforceRequestError`` の ``detail`` を引き継ぐので、
        # プログラムからは HTTP コードとレポート ID で機械的に判定できる
        self.report_id = report_id
        self.status_code = status_code
        self.detail = detail


class SoqlBuildError(SalesforceError):
    """SOQL の組み立て方が不正で止まった

    オブジェクト名・項目名の書式が壊れている、比較演算子が SOQL に無い、
    値の型が SOQL に書けない、`SELECT` が 1 つも無い、といった組み立て方の誤り。

    SOQL には `SELECT *` が無く、値を差し込む変数（バインド変数）も無い。
    引用符やエスケープは文字列で組み立てると漏れるので、**値は Python の型で
    そのまま渡し、`Soql` にエスケープを任せる。**

    発生箇所: comken.toolbox.salesforce.soql の Soql（コンストラクタと
             select() / where() / where_any() / group_by() / order_by() / limit() / build()）

    対処:
        メッセージに出た対象（項目名など）と値を確認する。識別子は英字・数字・`_` だけで書く
        （項目名の途中だけ `.` で連結できる）。値は引用符を自分で書かず Python の値のまま渡す
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
