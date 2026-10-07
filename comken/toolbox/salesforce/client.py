r"""comken/toolbox/salesforce/client.py — Salesforce API クライアント

1インスタンスが1組織を受け持つ。**このクラスは直接使わず、組織ごとに継承する**
（`comken/toolbox/salesforce/sites/`）。組織の My Domain の URL と認証情報のシステム名は
サブクラスがクラス定数として持ち、呼び出し側は組織クラスを作るだけでつながる。

    # 組織クラス側（sites/）
    class Solution(SalesforceBase):
        DOMAIN_URL = "https://example.my.salesforce.com"
        CREDENTIAL_PREFIX = "solution"

    # 使う側
    with Solution() as sf:
        rows = sf.query("SELECT Id, Name FROM Application__c")

認証・レポート・計測は継承せず**持たせている**。認証は「トークンを取る部品」で
あって Salesforce の一種ではなく、合成にしておくと JWT フローへの差し替えが
`auth` の入れ替えだけで済むため（詳しくは docs/機能/salesforce.md）。
"""

import logging
import re
import time
import urllib.parse
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, Self

import requests

from comken.core.table import Table
from comken.core.timer import measure
from comken.exceptions import (
    SalesforceError,
    SalesforceRequestError,
    SiteOwnerRequiredError,
)
from comken.runtime import dry_run_log, is_dry_run
from comken.toolbox.csv import CSV
from comken.toolbox.csv.file import parse_text

# 既定は Refresh Token Flow（→ docs/HISTORY.md）。
from comken.toolbox.salesforce.auth.oauth_refresh import RefreshTokenOAuth
from comken.toolbox.salesforce.metrics import APIMetrics, RetryReason
from comken.toolbox.salesforce.report import ReportAPI

logger = logging.getLogger(__name__)


def _connection_error(url: str, detail: Exception) -> SalesforceError:
    """``SalesforceError`` の「Salesforce につながらない」文言。"""
    return SalesforceError(
        f"Salesforce に接続できませんでした: {url}\n"
        f"（{detail}）\n"
        "ネットワーク接続と URL を確認してください。"
        "\n対処: ネットワークの状態を確認して、少し待ってから再実行してください。"
    )


def _external_id_missing_error(object_name: str, external_id_field: str) -> SalesforceError:
    """``SalesforceError`` の「upsert 用データに外部 ID がない」文言。"""
    return SalesforceError(
        f"Salesforce の upsert データに外部 ID 項目がありません: "
        f"{object_name}.{external_id_field}\n"
        f"data に {external_id_field} の値を含めてください。"
        "\n対処: 管理者へ連絡してください。"
    )


# comken 配下のクラスは OWNER 検査の対象外（管理者が既に昇格を判断した印）。
# SiteBase 側と同じ定数を同じ目的で置く
_COMKEN_MODULE_PREFIX = "comken."

HTTP_UNAUTHORIZED = 401
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR = 500
HTTP_BAD_REQUEST = 400
DRY_RUN_RECORD_ID = "DRYRUN00000000000A"

# オブジェクトの API 参照名（``/sobjects/{object_name}/describe`` の ``object_name``）。
# ``/`` ``?`` ``#`` や空白を含めると URL を壊したり別パスを指したりできるため、
# HTTP を呼ぶ前に弾く。英字・数字・ ``_`` だけを許す（標準オブジェクト・ ``__c``
# カスタムオブジェクト・ ``_`` 始まりの内部オブジェクトを含む）。
_OBJECT_NAME_PATTERN = re.compile(r"\A[A-Za-z0-9_]+\Z")

# 一時的な失敗をやり直す回数と待ち時間。待ち時間は試行回数に比例して伸ばす
MAX_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 2


# NOTE: SalesforceBase の型注釈を実行時に評価するため、_OAuth は公開クラスより前に置く。
class _OAuth(Protocol):
    """Salesforceクライアントが認証方式へ求める最小インターフェース。"""

    @classmethod
    def from_credentials(cls, domain_url: str, prefix: str) -> Self:
        """認証情報からインスタンスを組み立てる（具象クラスごとに実装する）。"""
        ...

    def request_token(self) -> tuple[str, str]:
        """アクセストークンとinstance_urlを返す。"""
        ...


class SalesforceBase:
    """Salesforce の 1 組織に対する API クライアント（組織クラスの土台）。

    DOMAIN_URL と CREDENTIAL_PREFIX を持つサブクラスを作って使う。
    認証情報は DPAPI から読むので、呼び出し側のコードに秘密の値が現れない。

    使い方:
        with Solution() as sf:
            records = sf.query("SELECT Id, Name FROM Account")
            rows = sf.report.get("00O000000000001")
            sf.metrics.log_summary()

    Attributes:
        report: レポート API（sf.report.get(...)）。
        metrics: API 呼び出しの計測（sf.metrics.log_summary()）。
        DOMAIN_URL: 組織の My Domain の URL。組織クラスで指定する。
        CREDENTIAL_PREFIX: 認証情報のキー名の頭。組織クラスで指定する。
        DISPLAY_NAME: 人が読むための組織名。空なら display_name() がクラス名を返す。
        CALLBACK_URL: 初回認可（Refresh Token Flow）で使うローカル Callback URL。
    """

    # API バージョン。組織が対応していない場合はサブクラスで上書きする
    API_VERSION = "67.0"
    TIMEOUT_SECONDS = 60

    # 組織の My Domain の URL。組織クラスで指定する
    DOMAIN_URL = ""

    # 認証情報のキー名の頭。組織クラスで指定する
    CREDENTIAL_PREFIX = ""

    # 表示用の分かりやすい名前（任意）。空なら display_name() がクラス名を返す
    DISPLAY_NAME = ""

    # 初回認可（Refresh Token Flow）で使うローカル Callback URL。
    # 通常は組織ごとに変える必要はないが、ECA 側の設定と食い違う組織が
    # あれば、そのクラスで上書きする
    CALLBACK_URL = "http://localhost:8080/callback"

    # 「どのプロジェクト／誰が継承して作ったか」を示す識別子。同じ社内組織の
    # クラスが複数プロジェクトで重複していないかを、ライブラリ管理者が
    # 把握するために使う。comken 配下に置くクラスは OWNER = "comken" にする。
    OWNER = ""

    @classmethod
    def display_name(cls) -> str:
        """人が読むための組織名。``DISPLAY_NAME`` が空ならクラス名を使う。"""
        return cls.DISPLAY_NAME or cls.__name__

    def __init__(
        self,
        *,
        prefix: str = "",
        domain_url: str = "",
        org_name: str = "",
        auth: _OAuth | type[_OAuth] | None = None,
    ) -> None:
        """DPAPI に保管した認証情報を読み、選択中の OAuth 方式で接続する。

        読み込む項目は client.py が import している OAuth 方式（既定は
        RefreshTokenOAuth）で決まる。Refresh Token 方式は
        client_id / client_secret / refresh_token を使う。

        Args:
            prefix: 認証情報のシステム名。省略時はクラスの CREDENTIAL_PREFIX。
                本番とテストを切り替えるときだけ渡す。
            domain_url: My Domain の URL。省略時はクラスの DOMAIN_URL。
            org_name: 計測ログに出す組織の呼び名。省略時はクラス名を使う。
            auth: 認証方式を差し替えるときに渡す。**クラスを渡せば**
                DPAPI から組み立てる（値を手で並べなくてよい）。
                作成済みのインスタンスを渡すこともできる（テスト・JWT 等）。
                その場合だけ prefix / domain_url は使われない。

        Raises:
            CredentialError: システム名が空、または使えない文字を含む場合、
                別のユーザー・PC で登録されていて復号できない場合。
            CredentialNotFoundError: 選択方式に必要な認証情報が未登録の場合。
            SalesforceAuthError: 認証に失敗した場合。
            SalesforceError: ネットワークの問題で接続できない場合。
        """
        # 認証やネットワークに触れる前に OWNER を確かめる。`_check_start()` は
        # OWNER 必須検査だけを行う classmethod。comken 配下の組織クラスは検査しない
        # （管理者が既に判断した印）。ライブラリ内の同名組織は sites/site_for() が
        # 別途検出するため、ここでは NAME 衝突まで見ない
        type(self)._check_start()
        # 認証方式のクラスを渡されたら、組み立ては省略せず DPAPI から作る。
        # 値を手で並べる書き方を利用側に強いないため。既定（None）も同じ経路を通る。
        if auth is None:
            auth = RefreshTokenOAuth
        if isinstance(auth, type):
            auth = auth.from_credentials(
                domain_url or self.DOMAIN_URL,
                prefix or self.CREDENTIAL_PREFIX,
            )
        self.auth = auth
        self.metrics = APIMetrics(org_name or type(self).__name__)
        self.report = ReportAPI(self)

        self._session = requests.Session()
        self._access_token = ""
        self._instance_url = ""
        self._authenticate()
        # 起動成功後に1回だけ INFO ログを出す。検証 (`_check_start()`) とは別
        # 経路で、認証が失敗したら出さない（5xx をリトライしたと計測しながら
        # 実際にはやり直していなかった反省を踏まないため）
        type(self)._log_started()

    @classmethod
    def _check_start(cls) -> None:
        """起動時に1回だけ行う検証（OWNER 必須）。

        OWNER の必須検査を `with SalesforceBase()` 経路から確実に通すため、
        SiteBase と同じ形で classmethod にまとめる。comken 配下の組織クラスは
        検査対象外（管理者が既に判断した印）。ライブラリ内の同名組織の検出は
        sites/site_for() が担うため、ここでは NAME 衝突まで見ない。
        起動 INFO ログは出さない。ログは起動が成功した後 `_log_started()` で
        1回だけ出す（ここで出すと認証失敗のときに「使った」という嘘のログが残る）。
        """
        if cls.__module__.startswith(_COMKEN_MODULE_PREFIX):
            return
        if not cls.OWNER:
            raise SiteOwnerRequiredError(cls, "SalesforceBase")

    @classmethod
    def _log_started(cls) -> None:
        """起動が成功した後に1回だけ出す INFO ログ。

        検証 (`_check_start()`) とは分けて、認証の出口に置く。
        認証が失敗したらログは出さない（5xx をリトライしたと計測しながら
        実際にはやり直していなかった反省を踏まないため）。
        comken 配下のクラスは免除の判定を `_check_start()` と共有し、ログも
        出さない（管理者が把握済みのものを毎回流しても情報が増えないため）。
        """
        if cls.__module__.startswith(_COMKEN_MODULE_PREFIX):
            return
        logger.info("site=%s owner=%s defined=%s", cls.__name__, cls.OWNER, cls.__module__)

    # 組織クラスのまま返す（with Solution() as sf: で組織固有メソッドの補完が効く）
    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """HTTP セッションを閉じる。with を使う場合は自動で呼ばれる。"""
        self._session.close()

    # ------------------------------------------------------------------ query
    @measure
    def query_rows(self, soql: str) -> Iterator[dict[str, Any]]:
        """SOQL クエリを実行し ``{項目: 値}`` の dict を 1 件ずつ返す（全件・ページ送り自動）。

        レポートは上限 2000 行だが、SOQL に上限はない。**ページ受信のたびに**
        ``yield`` するため、全件を溜め込まずに 1 件目からすぐ処理を始められる。
        ``query()`` はこのイテレータを ``Table`` に包む薄い層
        （順序を「イテレータ先・Table 後」に揃えるため）。

        列の情報は SOQL のレスポンスからは取れないため、戻り値からは直接
        列名が出ない。``query()`` は ``records[0]`` から列を推測するが、
        これは「1 件以上あるとき」の便宜であって、本物のスキーマではない。
        列名を厳密に扱いたいときは ``describe`` 系エンドポイントを使うこと。

        Args:
            soql: 実行する SOQL クエリ文字列。

        Returns:
            SOQL のレコードを ``{項目: 値}`` の dict で 1 件ずつ返すイテレータ。
        """
        logger.debug("Salesforce SOQL取得開始")
        path = self.data_path(f"/query?q={urllib.parse.quote(soql)}")
        # 件数ログは逐次 yield と両立させるため、ページ受信のたびに数える
        yielded = 0
        while path:
            result, _ = self.request("GET", path, component="query")
            if not isinstance(result, dict):
                break
            page_records = result.get("records", [])
            for record in page_records:
                record.pop("attributes", None)  # メタ情報は業務データに不要
                yielded += 1
                yield record
            # done が真なら次のページは無い
            path = "" if result.get("done", True) else result.get("nextRecordsUrl", "")
        logger.debug("Salesforce SOQL取得完了: 件数=%d", yielded)

    @measure
    def query(self, soql: str) -> Table:
        """SOQL クエリを実行して ``Table`` を返す（全件取得・ページ送り自動）。

        ``query_rows()`` を呼んで ``Table`` に包むだけの薄い層。
        列は SOQL からはメタデータが取れないため、**1 件目から推測**する。
        0 件のときは列が空の ``Table`` を返す（``rows[0]`` からの推測に依存
        しないため）。なお ``Account.Name`` のようなドット区切りの親子リレーション
        項目は**そのまま列名にする**（平坦化しない）。``records[0]`` のキーが
        そのまま列になるため、リレーションを跨いだ項目の取り回しを呼び出し側で
        揃えておくこと。

        Args:
            soql: 実行する SOQL クエリ文字列。

        Returns:
            SOQL の結果を表す ``Table``。
        """
        records = list(self.query_rows(soql))
        # 0 件のときは列を空で返す。``list(records[0])`` は 0 件だと例外になるため、
        # 分岐して空リストを返す（実装の意図を明示するため ``else []`` を付ける）。
        columns = list(records[0]) if records else []
        return Table(columns, records)

    @measure
    def query_csv(self, soql: str, path: str | Path) -> Path:
        """SOQL クエリを実行して、結果をそのまま CSV へ保存する。

        ``query()`` が返す ``Table`` を ``CSV`` へ書き出すだけの薄い層。
        ``Table`` 自体はファイル I/O を持たない設計（保存先の責任を分ける）ため、
        SOQL の結果を直接 CSV で欲しいだけのときはこちらを使う。

        Args:
            soql: 実行する SOQL クエリ文字列。
            path: 保存先の CSV パス（拡張子は ``.csv``）。

        Returns:
            保存した CSV のパス。
        """
        table = self.query(soql)
        csv_path = Path(path)
        with CSV(csv_path) as csv_file:
            csv_file.replace(table)
        return csv_path

    # Bulk API 2.0 Query のポーリング間隔。Salesforce 側の負荷を下げるため短すぎない値
    BULK_POLL_SECONDS = 5
    # Bulk API 2.0 Query 全体のタイムアウト。30 分を超えたら中止して例外
    BULK_TIMEOUT_SECONDS = 1800

    @measure
    def bulk_query(self, soql: str) -> Table:
        """SOQL クエリを Bulk API 2.0 で実行し ``Table`` を返す（大量データ向け）。

        ``query()`` は REST API を同期でページを送りながら返すため、件数が
        非常に多い取得では往復回数と 1 リクエストあたりの処理時間がともに
        効いてくる。Bulk API 2.0 Query はジョブを Salesforce 側に登録して
        から結果 CSV をページ単位で取り出す形のため、長時間ジョブをサーバ側で
        実行でき、件数が多い・定期取得で同じ SOQL を回す用途に向く。

        一方で Bulk API 2.0 Query が**受け付けない SOQL 構文**がある
        （集計関数・``GROUP BY``・``OFFSET``・親→子のサブクエリなど）。
        この場合は Salesforce がジョブ作成時に 400 を返すため、
        ``REST 版（query()）へ黙って切り替えず``そのまま
        ``SalesforceRequestError`` で止まる。集計や少量の対話的な取得は
        ``query()`` を使うこと。

        列は CSV の見出しから取得するため **0 件ヒットでも列情報が残る**
        （``records[0]`` からの推測に依存しない）。値は**全て文字列のまま**
        （数値・真偽値への変換は行わない。"0012" の先頭ゼロや "1234567890"
        を整数化しない）。``Account.Name`` のような参照項目も見出しの名前を
        そのまま列名にする（平坦化しない）。null のセルは空文字にする。
        複数ページの見出しが食い違うときは例外を呼ぶ。

        通信は既存の ``self.request()`` を通すため、計測・5xx/429 のバック
        オフ・401 の再認証は ``query()`` と共通。タイムアウト
        （``BULK_TIMEOUT_SECONDS`` 秒）で完了しなかった場合は、ジョブを
        ``Aborted`` に遷移させてから例外を投げる。中止の PATCH が失敗
        しても例外にはしない（ログだけ残す）。

        Args:
            soql: 実行する SOQL クエリ文字列。

        Returns:
            SOQL の結果を表す ``Table``。列は CSV の見出し順、値は全て文字列。
        """
        job_id = self._bulk_create_job(soql)
        try:
            self._bulk_wait_for_job(job_id)
        except _BulkTimeoutError as exc:
            self._bulk_abort_job(job_id)
            raise SalesforceError(
                f"Bulk API 2.0 のジョブが {self.BULK_TIMEOUT_SECONDS} 秒以内に"
                f"終わりませんでした: {exc.job_id}\n"
                "対処: データの量・SOQL の条件・Salesforce 側の負荷を確認してください。"
            ) from exc
        return self._bulk_fetch_results(job_id)

    # ---------------------------------------------------------------- describe
    @measure
    def describe_object(self, object_name: str) -> dict[str, Any]:
        """オブジェクトの describe（項目の一覧・型・参照先など）を返す。

        Salesforce の ``/services/data/v{API_VERSION}/sobjects/{object_name}/describe``
        を GET で呼び、API のレスポンス dict をそのまま返す。
        ``fields`` / ``childRelationships`` / ``recordTypeInfos`` など、メタデータに
        載るすべての情報を含むため、関連オブジェクトを調べるときの下敷きに使う。

        ``record`` 1 件を取りたい ``get()`` / レコードを更新する ``upsert()``
        など CRUD の動詞群とは目的が違うため、``describe_object()`` と
        別名で切っている。SOQL の ``query()`` と同じく「読むだけ」だが、
        戻り値は行ではなく dict なので ``Table`` には包まない。

        **キャッシュはしない。** 1 回の呼び出しごとに HTTP を打つ。
        結果を再利用したい呼び出し側で ``functools.lru_cache`` 相当を持たせる。

        Args:
            object_name: オブジェクトの API 参照名（例: ``"Account"``、
                ``"Opportunity"``、``"Custom__c"``）。

        Returns:
            API のレスポンス dict。API が dict 以外を返したときは空 dict。

        Raises:
            ValueError: ``object_name`` が空文字、または英数字と ``_`` 以外の
                文字を含む場合（URL を壊す名前を HTTP を呼ぶ前に弾く）。
            SalesforceRequestError: HTTP エラー。
        """
        if not _OBJECT_NAME_PATTERN.match(object_name):
            raise ValueError(
                f"無効なオブジェクト名です: {object_name!r}"
                "（英数字と _ のみ。例: 'Account'、'Custom__c'）"
            )
        path = self.data_path(f"/sobjects/{object_name}/describe")
        result, _ = self.request("GET", path, component="describe")
        return result if isinstance(result, dict) else {}

    # ------------------------------------------------------------------- CRUD
    @measure
    def get(self, object_name: str, record_id: str) -> dict[str, Any]:
        """レコードを1件取得する。

        ``sf.report.get(...)`` ではなく ``sf.get(...)``（CRUD）で使う。
        ``report`` は ``ReportAPI`` インスタンスで名前空間が分かれているため、
        CRUD の動詞群 ``get`` / ``insert`` / ``update`` / ``upsert`` / ``delete``
        と揃える目的で ``get`` を採用する。

        Args:
            object_name: オブジェクトの API 参照名（例: "Account"）。
            record_id: レコードの Id。
        """
        record, _ = self.request(
            "GET", self.data_path(f"/sobjects/{object_name}/{record_id}"), component="crud"
        )
        if isinstance(record, dict):
            record.pop("attributes", None)
            return record
        return {}

    @measure
    def insert(self, object_name: str, data: dict[str, Any]) -> str:
        """レコードを作成して Id を返す。

        Args:
            object_name: オブジェクトの API 参照名。
            data: 作成するレコードの項目と値。
        """
        if is_dry_run():
            dry_run_log("Salesforce %s に insert: %s", object_name, data)
            return DRY_RUN_RECORD_ID
        result, _ = self.request(
            "POST", self.data_path(f"/sobjects/{object_name}"), body=data, component="crud"
        )
        return result["id"] if isinstance(result, dict) else ""

    @measure
    def update(self, object_name: str, record_id: str, data: dict[str, Any]) -> None:
        """レコードを更新する。

        Args:
            object_name: オブジェクトの API 参照名。
            record_id: 更新するレコードの Id。
            data: 更新する項目と値。
        """
        if is_dry_run():
            dry_run_log("Salesforce %s (%s) を update: %s", object_name, record_id, data)
            return
        self.request(
            "PATCH",
            self.data_path(f"/sobjects/{object_name}/{record_id}"),
            body=data,
            component="crud",
        )

    @measure
    def upsert(self, object_name: str, external_id_field: str, data: dict[str, Any]) -> None:
        """外部 ID で upsert する（一致すれば更新、なければ作成）。

        Args:
            object_name: オブジェクトの API 参照名。
            external_id_field: 外部 ID 項目の API 参照名（例: "ExternalId__c"）。
            data: 項目と値。external_id_field の値を含めること。

        Raises:
            SalesforceError: data に external_id_field が無い場合。
        """
        if is_dry_run():
            dry_run_log("Salesforce %s を upsert（%s）: %s", object_name, external_id_field, data)
            return
        if external_id_field not in data:
            raise _external_id_missing_error(object_name, external_id_field)
        external_id = urllib.parse.quote(str(data[external_id_field]), safe="")
        # 外部 ID は URL 側で指定するため、本文からは取り除く
        body = {key: value for key, value in data.items() if key != external_id_field}
        self.request(
            "PATCH",
            self.data_path(f"/sobjects/{object_name}/{external_id_field}/{external_id}"),
            body=body,
            component="crud",
        )

    @measure
    def delete(self, object_name: str, record_id: str) -> None:
        """レコードを削除する。

        Args:
            object_name: オブジェクトの API 参照名。
            record_id: 削除するレコードの Id。
        """
        if is_dry_run():
            dry_run_log("Salesforce %s (%s) を delete", object_name, record_id)
            return
        self.request(
            "DELETE", self.data_path(f"/sobjects/{object_name}/{record_id}"), component="crud"
        )

    # ---------------------------------------------------------------- request
    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        component: str = "other",
        headers: dict[str, str] | None = None,
        data: str | None = None,
    ) -> tuple[dict[str, Any] | list[Any] | str | None, dict[str, str]]:
        """REST API を呼び、(レスポンス本文, レスポンスヘッダー) を返す。

        すべての API 呼び出しがここを通る。計測と、401 のときの再認証もここで行う。
        通常は query() / get() 等を使い、このメソッドは
        ライブラリに無い API を叩くときだけ使う。

        中身は薄い調整役で、実処理は ``_send_with_backoff``（5xx/429 リトライ）と
        ``_reauthenticate_if_unauthorized``（401 再認証）に任せている。

        Args:
            method: HTTP メソッド（GET / POST / PATCH / DELETE）。
            path: "/services/data/..." から始まるパス。
            body: JSON で送る辞書（省略可）。
            component: 計測での呼び出し元の区別（"query" / "crud" / "report"）。
            headers: この呼び出しだけ上書きする追加ヘッダー（省略可）。
                セッションの既定ヘッダーと同名のキーはこの値が勝つ（``requests``
                ライブラリの挙動）。``None`` のときは何も追加しない。
            data: CSV 本体など、生テキストで送りたいときに指定する（省略可）。
                ``body`` と同じ呼び出しでは使わない。

        Raises:
            SalesforceRequestError: API がエラーを返した場合。
            SalesforceError: ネットワークの問題で接続できない場合。
        """
        start = time.perf_counter()
        # 初回送信をバックオフの外で行い、response を必ず束縛する。下のループは
        # 5xx/429 の一時障害だけを拾うので、初回送信と合計で最大 MAX_ATTEMPTS 回
        # になる（試行 1..MAX_ATTEMPTS-1 = 2 回まで再試行）。pyright から見ても
        # response は Optional にならない
        response = self._send(method, self._request_url(path), body, headers, data)
        response = self._send_with_backoff(method, path, body, headers, data, component, response)
        response = self._reauthenticate_if_unauthorized(
            response, method, path, body, headers, data, component
        )

        is_error = response.status_code >= HTTP_BAD_REQUEST
        self.metrics.record_call(component, time.perf_counter() - start, is_error=is_error)

        limit_info = response.headers.get("Sforce-Limit-Info")
        if limit_info:
            self.metrics.update_api_usage(limit_info)

        if is_error:
            raise SalesforceRequestError(method, path, response.status_code, response.text)

        return self._body_of(response), dict(response.headers)

    def _send_with_backoff(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        headers: dict[str, str] | None,
        data: str | None,
        component: str,
        response: requests.Response,
    ) -> requests.Response:
        """5xx / 429 だけを拾って待ち時間付きで再送信し、最終レスポンスを返す。

        呼び出し側で初回送信を行い、その ``response`` を渡すとリトライ判定から
        続ける。リトライ対象外のステータスならそのまま返す。5xx と 429 は
        Salesforce 側の一時的な事情なので、待って試し直す。

        ``path`` は再認証で ``instance_url`` が変わる可能性があるため、デバッグ
        ログ用に渡し、URL が必要になるたびに ``_request_url(path)`` で組み立て直す。
        """
        for attempt in range(1, MAX_ATTEMPTS):
            reason = _retry_reason(response.status_code)
            if not reason:
                # 成功、または 4xx のようにリトライしても直らない永続的な失敗
                return response
            logger.debug(
                "%s のため %d 秒待って再試行します（%d/%d）: %s",
                reason,
                RETRY_WAIT_SECONDS * attempt,
                attempt,
                MAX_ATTEMPTS,
                path,
            )
            self.metrics.record_retry(component, reason)
            time.sleep(RETRY_WAIT_SECONDS * attempt)
            response = self._send(method, self._request_url(path), body, headers, data)
        return response

    def _reauthenticate_if_unauthorized(
        self,
        response: requests.Response,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        headers: dict[str, str] | None,
        data: str | None,
        component: str,
    ) -> requests.Response:
        """401 ならトークンを取り直して 1 回だけ再送信し、最終レスポンスを返す。

        401 の再認証はバックオフのリトライ回数を消費しない別ルート。一時障害の
        リトライ中に 401 が出ても、ここはループの外で 1 回だけ拾う。2 回続けて
        401 になるのは設定の問題なので、再認証後も 401 のままなら次の
        ``SalesforceRequestError`` にそのまま落とす。
        """
        if response.status_code == HTTP_UNAUTHORIZED:
            logger.debug("401 を受け取ったのでトークンを取り直します: %s", path)
            self.metrics.record_retry(component, RetryReason.REAUTH)
            self._authenticate()
            response = self._send(method, self._request_url(path), body, headers, data)
        return response

    def _request_url(self, path: str) -> str:
        """相対パスと Salesforce が返す絶対 URL の両方を送信用 URL にする。

        絶対 URL で渡された場合もホスト部分は使わず、必ず instance_url へ送る。
        nextRecordsUrl はレスポンス本文の値なので、書かれたホストへそのまま送ると
        Authorization ヘッダーのアクセストークンを別のホストへ渡すことになる。
        同じ組織の中でページを辿るだけなので、ホストは自分が知っているものに固定する。
        """
        parsed = urllib.parse.urlsplit(path)
        relative = urllib.parse.urlunsplit(("", "", parsed.path, parsed.query, ""))
        return f"{self._instance_url}{relative}"

    def _send(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None,
        headers: dict[str, str] | None = None,
        data: str | None = None,
    ) -> requests.Response:
        """HTTP リクエストを1回送る。"""
        try:
            return self._session.request(
                method, url, json=body, data=data, headers=headers, timeout=self.TIMEOUT_SECONDS
            )
        except requests.exceptions.RequestException as e:
            raise _connection_error(url, e) from e

    @staticmethod
    def _body_of(response: requests.Response) -> dict[str, Any] | list[Any] | str | None:
        """レスポンス本文を、内容に応じて辞書・リスト・文字列・None で返す。

        非 JSON（CSV など）の本文は Content-Type に ``charset`` が付いていれば
        ``response.text``（requests が charset で復号した結果）を使い、付いて
        いなければ ``response.content`` を UTF-8 で復号する。``response.text``
        は Content-Type に charset が無いと requests が ISO-8859-1 で復号する
        ため、CSV のような非 JSON 本文は明示的に UTF-8 復号する。
        JSON 経路は ``response.json()`` を使うので影響を受けない。
        """
        if not response.content:
            return None  # DELETE や PATCH は本文が空で返る
        if response.headers.get("Content-Type", "").startswith("application/json"):
            return response.json()
        content_type = response.headers.get("Content-Type", "")
        if "charset=" in content_type.lower():
            return response.text
        return response.content.decode("utf-8")

    def _authenticate(self) -> None:
        """トークンを取り直し、以降のリクエストに使うヘッダーを差し替える。"""
        self._access_token, self._instance_url = self.auth.request_token()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def data_path(self, path: str) -> str:
        """REST API のバージョン付きパスを組み立てる。

        ライブラリに無い API を request() で叩くときに使う。

            sf.request("GET", sf.data_path("/limits"))
        """
        return f"/services/data/v{self.API_VERSION}{path}"

    # ---------------------------------------------------------------- Bulk
    def _bulk_create_job(self, soql: str) -> str:
        """Bulk API 2.0 の Query ジョブを作成し、ジョブ ID を返す。

        ジョブ作成時に Salesforce が SOQL を検証する。集計関数・
        ``GROUP BY``・``OFFSET``・親→子のサブクエリなどはこの時点で
        400 が返る。REST 版 ``query()`` へのフォールバックはしない
        （呼び出し側で使い分けてもらう）。
        """
        started, _ = self.request(
            "POST",
            self.data_path("/jobs/query"),
            body={"operation": "query", "query": soql},
            component="bulk",
        )
        if not isinstance(started, dict) or not started.get("id"):
            raise SalesforceError(
                "Bulk API 2.0 のジョブ作成に失敗しました（id が返っていません）。\n"
                "対処: 通信状況と SOQL を確認し、しばらく待ってから再実行してください。"
            )
        return str(started["id"])

    def _bulk_wait_for_job(self, job_id: str) -> None:
        """ジョブの完了（``JobComplete``）をポーリングして待つ。

        ``Failed`` / ``Aborted`` を見たら ``SalesforceError`` で例外。
        ``BULK_TIMEOUT_SECONDS`` を超えたら ``_BulkTimeoutError``
        を投げる（``bulk_query()`` が捕捉して Aborted に遷移する）。
        """
        path = self.data_path(f"/jobs/query/{job_id}")
        deadline = time.monotonic() + self.BULK_TIMEOUT_SECONDS
        while True:
            data, _ = self.request("GET", path, component="bulk")
            if not isinstance(data, dict):
                raise SalesforceError(
                    f"Bulk API 2.0 のジョブ状態取得に失敗しました: {job_id}\n"
                    "対処: 通信状況を確認し、しばらく待ってから再実行してください。"
                )
            state = str(data.get("state", ""))
            if state == "JobComplete":
                return
            if state in ("Failed", "Aborted"):
                error_message = data.get("errorMessage") or "詳細情報なし"
                raise SalesforceError(
                    f"Bulk API 2.0 のジョブが {state} になりました: {job_id}\n"
                    f"{error_message}\n"
                    "対処: SOQL の構文・参照項目・権限を確認してください。"
                )
            if time.monotonic() >= deadline:
                raise _BulkTimeoutError(job_id)
            time.sleep(self.BULK_POLL_SECONDS)

    def _bulk_abort_job(self, job_id: str) -> None:
        """ジョブを ``Aborted`` に遷移させる。失敗はログだけで例外にはしない。

        タイムアウトで残ったジョブを放置しないために呼ぶ。既に
        Failed / Aborted のときは PATCH しても 400 が返る可能性が
        あるが、そのときは例外にせずログだけ残す（呼び出し側は
        元の例外を再送出すべき）。
        """
        try:
            self.request(
                "PATCH",
                self.data_path(f"/jobs/query/{job_id}"),
                body={"state": "Aborted"},
                component="bulk",
            )
        except SalesforceError as exc:
            logger.warning("Bulk API 2.0 のジョブ中止に失敗しました: %s (%s)", job_id, exc)

    def _bulk_fetch_results(self, job_id: str) -> Table:
        """結果 CSV をページ送りしながら ``Table`` に組み立てる。

        列は **1 ページ目の見出し**から取り、2 ページ目以降の見出し行は
        捨てる。2 ページ目以降の見出しが食い違ったら ``SalesforceError``
        を送出する（ページ間で列構造が変わることはない想定のため）。

        結果の本文が空（``None``）のときは 0 行として扱う。Salesforce は
        0 件のときに本文を空で返す場合があり、そのときに後続ページが無い
        ケース（=1 ページ目が空）を「列も空・0 行の ``Table``」として返す。
        """
        rows: list[dict[str, str]] = []
        columns: list[str] = []
        locator: str | None = None
        first_page = True
        while True:
            path = self.data_path(f"/jobs/query/{job_id}/results")
            if locator:
                path = f"{path}?locator={urllib.parse.quote(locator)}"
            body, response_headers = self.request(
                "GET",
                path,
                headers={"Accept": "text/csv"},
                component="bulk",
            )
            if body is None:
                # 0 件で本文が空のときは空ページとして扱う。1 ページ目なら
                # 「列も空・0 行」の Table を返し、ループを抜ける
                if first_page:
                    return Table([], [])
                raise SalesforceError(
                    f"Bulk API 2.0 の結果取得に失敗しました: {job_id}\n"
                    "対処: 通信状況を確認し、しばらく待ってから再実行してください。"
                )
            if not isinstance(body, str):
                raise SalesforceError(
                    f"Bulk API 2.0 の結果取得に失敗しました: {job_id}\n"
                    "対処: 通信状況を確認し、しばらく待ってから再実行してください。"
                )
            page_rows, page_columns = _parse_bulk_csv(body)
            if first_page:
                columns = page_columns
                rows.extend(page_rows)
                first_page = False
            elif page_columns != columns:
                raise SalesforceError(
                    f"Bulk API 2.0 の結果ページで見出しが一致しません: {job_id}\n"
                    f"1 ページ目: {columns}\n2 ページ目以降: {page_columns}\n"
                    "対処: Salesforce 側のレスポンスを確認してください。"
                )
            else:
                rows.extend(page_rows)
            locator_header = response_headers.get("Sforce-Locator", "")
            if not locator_header or locator_header == "null":
                return Table(columns, rows)
            locator = locator_header


# ── 内部ヘルパー ──────────────────────────────────────────────────────────────


class _BulkTimeoutError(Exception):
    """``_bulk_wait_for_job()`` が ``BULK_TIMEOUT_SECONDS`` を超えたときに送出する内部例外。

    公開 API（``bulk_query()``）側で ``Aborted`` に遷移させてから
    ``SalesforceError`` に積み直して送出すためだけに使う。モジュール外に
    漏らさない前提の薄い例外。
    """

    def __init__(self, job_id: str) -> None:
        super().__init__(job_id)
        self.job_id = job_id


def _parse_bulk_csv(text: str) -> tuple[list[dict[str, str]], list[str]]:
    """Bulk API 2.0 の結果 CSV を (行 dict のリスト, 列名リスト) に分解する。

    列数は **1 行目の見出し**で固定する。データ行の列数が見出しと一致しない
    ときは ``SalesforceError`` で停止する（短い行を空文字で埋めたり長い行の
    余りを捨てると、データが黙ってずれたり消えたりするため）。null セルは
    CSV 側で空文字として届くため、空文字のまま ``row`` に入れる。
    """
    raw_rows = parse_text(text)
    if not raw_rows:
        return [], []
    columns = list(raw_rows[0])
    data_rows: list[dict[str, str]] = []
    for line_number, raw in enumerate(raw_rows[1:], start=2):
        if len(raw) != len(columns):
            raise SalesforceError(
                f"Bulk API 2.0 の結果 CSV の{line_number}行目は列数が一致しません: \n"
                f"見出しは{len(columns)}列、データは{len(raw)}列です。\n"
                "対処: SOQL の SELECT 項目と結果の列数を確認してください。"
            )
        data_rows.append(dict(zip(columns, raw, strict=True)))
    return data_rows, columns


def _retry_reason(status_code: int) -> str:
    """やり直す価値のあるステータスなら、その理由を返す。それ以外は空文字。"""
    if status_code >= HTTP_SERVER_ERROR:
        return RetryReason.SERVER_ERROR  # Salesforce 側の一時的な不調
    if status_code == HTTP_TOO_MANY_REQUESTS:
        return RetryReason.RATE_LIMIT  # 同時実行数の制限。待てば通ることがある
    return ""
