"""comken/exceptions/base.py — ライブラリ共通の基底例外。"""


class ComkenError(Exception):
    """comken が出す固有エラー全体

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class SiteOwnerRequiredError(ComkenError):
    """`SiteBase` / `SalesforceBase` のサブクラスに `OWNER` が設定されていない

    継承してサイト／組織クラスを作った事実がライブラリ管理者に届かないと、
    同じ社内システムのクラスが複数プロジェクトで重複しても気づけない。
    ドキュメントの努力目標では守れないので、起動時に OWNER の設定を強制する。

    発生箇所: SiteBase.__enter__() / Browsers.launch(SiteBase) /
             SalesforceBase.__init__()

    対処:
        サブクラスに `OWNER = "プロジェクト名 / 担当者"` を1行追加する。
        ライブラリ（`comken.toolbox.browser.sites/` または
        `comken.toolbox.salesforce.sites/`）に入れるべきサイトかは
        `docs/開発/ライブラリ開発規約.md` の「サイト／組織クラスを昇格させる基準」を
        参照して判断する。ライブラリに昇格したい場合はライブラリ管理者へ連絡する。
    """

    def __init__(self, site_cls: type, base_cls_name: str) -> None:
        super().__init__(
            f"{site_cls.__name__} に OWNER が設定されていません。\n"
            f"  class {site_cls.__name__}({base_cls_name}):\n"
            '      OWNER = "プロジェクト名 / 担当者"   # ← この1行を追加してください\n'
            "OWNER は「どのプロジェクト／誰が継承して作ったか」を示す識別子で、\n"
            "同じ社内システムのクラスが複数プロジェクトで重複していないかを\n"
            "ライブラリ管理者が把握するために使います。\n"
            "なお、ライブラリ本体（comken.toolbox.browser.sites/ または\n"
            'comken.toolbox.salesforce.sites/）に置くサイトは OWNER = "comken" にします。\n'
            "プロジェクト側に置くかライブラリに昇格するかの基準は docs/開発/ライブラリ開発規約.md\n"
            "の「サイト／組織クラスを昇格させる基準」を参照してください。\n"
            "ライブラリに昇格したい場合は、ライブラリ管理者へ連絡してください。"
        )
