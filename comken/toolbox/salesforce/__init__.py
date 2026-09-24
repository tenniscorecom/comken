"""comken/toolbox/salesforce/__init__.py — Salesforce API 連携（requests）。

1インスタンスが1組織を受け持つ。**入口は組織クラス**（`sites/`）:

    from comken.toolbox.salesforce.sites import Solution

    with Solution() as sf:
        records = sf.query("SELECT Id, Name FROM Account")
        rows = sf.report.get("00O000000000001")
        sf.metrics.log_summary()

URL と認証情報のシステム名は組織クラスがクラス定数として持つので、
呼び出し側は何も渡さなくてよい。組織を増やすときは `sites/` にクラスを足す。
**認証の既定は Refresh Token Flow。** 組織クラスをそのまま使えばこれになる。

    with Solution() as sf:                                    # 既定（本番もこれ）
        ...

設計の背景は docs/HISTORY.md「認証方式」を参照。

    SalesforceBase              1組織ぶんの API クライアントの土台（組織クラスで継承する）
    DataLoaderCLI                Salesforce Data Loader の CLI 呼び出し（サブプロセス実行）
    DataLoaderResult             DataLoaderCLI.run() の戻り値
    RefreshTokenOAuth            Authorization Code + Refresh Token Flow（既定）
    APIMetrics                   API 呼び出しの計測。SalesforceBase.metrics が持っている
    APIUsage                     組織の 24 時間 API 消費量
    BulkIngestResult             Bulk Ingest ジョブの実行結果（成功／失敗行を Table で持つ）
    SalesforceCredentialRotator  ECA の資格情報を期限到来時だけローテーションする（既定で無効）

レポートAPIの2000行上限を超える場合（マトリックス／統合などSOQLに書き換えられない
形式）の最終手段は `comken.toolbox.browser.sites.salesforce`。画面のエクスポート
機能をブラウザ経由で叩く。組織ごとの設定（URL・認証情報名）は API 側の組織クラス
（`sites/` の `Solution` 等）からそのまま読むため、API 版とブラウザ版で同じ組織でも
個別の値を二重に持たなくてよい（詳しくは docs/salesforce.md）。

    from comken.toolbox.browser.sites.salesforce import site_for

    site_class = site_for(report_url)
    with site_class() as sf:
        sf.login_with_credentials()  # prefix省略 → CREDENTIAL_PREFIXを使う
        sf.wait_for_manual_login()
        for report_id, path in sf.export_reports(reports):
            ...
"""

from types import ModuleType
from typing import TYPE_CHECKING

from comken.toolbox.salesforce.bulk_ingest import BulkIngestResult
from comken.toolbox.salesforce.dataloader import DataLoaderCLI, DataLoaderResult
from comken.toolbox.salesforce.metrics import APIMetrics, APIUsage

# requests の存在チェックだけ先に行う。依存が無い環境でもこのパッケージを
# import だけはできるようにしておき、実際に API を叩く経路
# （`oauth_refresh` / `client` / `rotation` 等）で
# `import requests` が走った時点で ImportError が出る。
_requests: ModuleType | None
try:
    import requests as _requests  # 依存の有無をここで確かめるだけ
except ImportError:
    _requests = None

# `requests` を直接 import するモジュールは遅延ロードする。`report` のような
# requests 非依存モジュールだけ使う場合（BO 環境）にパッケージ全体を
# import 可能にするため
_LAZY_TARGETS: dict[str, str] = {
    "SalesforceBase": "comken.toolbox.salesforce.client",
    "RefreshTokenOAuth": "comken.toolbox.salesforce.auth.oauth_refresh",
    "SalesforceCredentialRotator": "comken.toolbox.salesforce.auth.rotation",
}

if TYPE_CHECKING:
    # 型チェッカー（pyright 等）は __getattr__ の戻り値を追えず、遅延対象を
    # 全て object 型と見なしてしまう（継承・属性アクセス・呼び出しが軒並み
    # エラーになる）。TYPE_CHECKING はここでだけ True 扱いになり実行時には
    # 一切評価されないため、requests 非依存という遅延importの目的を壊さずに
    # 型だけ正しく解決できる。
    from comken.toolbox.salesforce.auth.oauth_refresh import RefreshTokenOAuth
    from comken.toolbox.salesforce.auth.rotation import SalesforceCredentialRotator
    from comken.toolbox.salesforce.client import SalesforceBase


def __getattr__(name: str) -> object:
    """`from ... import X` の X を必要になったタイミングでだけ import する。

    Raises:
        AttributeError: 定義されていない属性を要求したとき。
    """
    module_name = _LAZY_TARGETS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """`dir(comken.toolbox.salesforce)` で遅延対象も返す。"""
    return sorted(set(__all__) | set(_LAZY_TARGETS))


__all__ = [
    "SalesforceBase",
    "BulkIngestResult",
    "DataLoaderCLI",
    "DataLoaderResult",
    "RefreshTokenOAuth",
    "APIMetrics",
    "APIUsage",
    "SalesforceCredentialRotator",
]
