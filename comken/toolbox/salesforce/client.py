r"""comken/toolbox/salesforce/client.py — Salesforce API クライアント

1インスタンスが1組織を受け持つ。**このクラスは直接使わず、組織ごとに継承する**
（`comken/salesforce/sites/`）。組織の My Domain の URL と認証情報のシステム名は
サブクラスがクラス定数として持ち、呼び出し側は組織クラスを作るだけでつながる。

    # 組織クラス側（sites/）
    class Sandbox(SalesforceBase):
        DOMAIN_URL = "https://example--sandbox.sandbox.my.salesforce.com"
        CREDENTIAL_PREFIX = "sandbox"

    # 使う側
    with Sandbox() as sf:
        rows = sf.query("SELECT Id, Name FROM Application__c")

認証・レポート・計測は継承せず**持たせている**。認証は「トークンを取る部品」で
あって Salesforce の一種ではなく、合成にしておくと JWT フローへの差し替えが
`auth` の入れ替えだけで済むため（詳しくは docs/salesforce.md）。
"""

import logging
import time
import urllib.parse
from typing import Protocol, Self

import requests

from comken.core.table import Table
from comken.core.timer import measure
from comken.exceptions import (
    SalesforceConnectionError,
    SalesforceExternalIDMissingError,
    SalesforceRequestError,
    SiteOwnerRequiredError,
)
from comken.runtime import dry_run_log, is_dry_run
from comken.toolbox.salesforce.metrics import APIMetrics, RetryReason

# 既定は Refresh Token Flow。Client Credentials Flow は client_secret だけで
# アクセストークンを取れてしまい、漏えいしたときに実行ユーザーとして操作されるため
# 使わない（→ docs/開発/salesforce-authentication.md）。
from comken.toolbox.salesforce.oauth_refresh import RefreshTokenOAuth
from comken.toolbox.salesforce.report import ReportAPI

logger = logging.getLogger(__name__)

# comken 配下のクラスは OWNER 検査の対象外（管理者が既に昇格を判断した印）。
# SiteBase 側と同じ定数を同じ目的で置く
_COMKEN_MODULE_PREFIX = "comken."

HTTP_UNAUTHORIZED = 401
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR = 500
HTTP_BAD_REQUEST = 400
DRY_RUN_RECORD_ID = "DRYRUN00000000000A"

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

    def fetch(self) -> tuple[str, str]:
        """アクセストークンとinstance_urlを返す。"""
        ...


class SalesforceBase:
    """Salesforce の 1 組織に対する API クライアント（組織クラスの土台）。

    DOMAIN_URL と CREDENTIAL_PREFIX を持つサブクラスを作って使う。
    認証情報は DPAPI から読むので、呼び出し側のコードに秘密の値が現れない。

    使い方:
        with Sandbox() as sf:
            records = sf.query("SELECT Id, Name FROM Account")
            rows = sf.report.run("00O000000000001")
            sf.metrics.log_summary()

    Attributes:
        report: レポート API（sf.report.run(...)）。
        metrics: API 呼び出しの計測（sf.metrics.log_summary()）。
    """

    # API バージョン。組織が対応していない場合はサブクラスで上書きする
    API_VERSION = "67.0"
    TIMEOUT_SECONDS = 60

    # 組織の My Domain の URL。組織クラスで指定する
    DOMAIN_URL = ""

    # 認証情報のキー名の頭。組織クラスで指定する
    CREDENTIAL_PREFIX = ""

    # 「どのプロジェクト／誰が継承して作ったか」を示す識別子。同じ社内組織の
    # クラスが複数プロジェクトで重複していないかを、ライブラリ管理者が
    # 把握するために使う。comken 配下に置くクラスは OWNER = "comken" にする。
    OWNER = ""

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
        RefreshTokenOAuth）で決まる。Client Credentials 方式は
        client_id / client_secret、Refresh Token 方式は
        client_id / client_secret / refresh_token を使う。

        Args:
            prefix: 認証情報のシステム名。省略時はクラスの CREDENTIAL_PREFIX。
                本番とテストを切り替えるときだけ渡す。
            domain_url: My Domain の URL。省略時はクラスの DOMAIN_URL。
            org_name: 計測ログに出す組織の呼び名。省略時はクラス名を使う。
            auth: 認証方式を差し替えるときに渡す。**クラスを渡せば**
                DPAPI から組み立てる（値を手で並べなくてよい）。
                    Sandbox(auth=ClientCredentialsAuth)   # 開発中だけ
                作成済みのインスタンスを渡すこともできる（テスト・JWT 等）。
                その場合だけ prefix / domain_url は使われない。

        Raises:
            InvalidCredentialNameError: システム名が空、または使えない文字を含む場合。
            CredentialNotFoundError: 選択方式に必要な認証情報が未登録の場合。
            CredentialDecryptionError: 別のユーザー・PC で登録されていて復号できない場合。
            SalesforceAuthError: 認証に失敗した場合。
            SalesforceConnectionError: ネットワークの問題で接続できない場合。
        """
        # 認証やネットワークに触れる前に OWNER を確かめる。`_check_start()` は
        # OWNER 必須検査だけを行う classmethod。comken 配下の組織クラスは検査しない
        # （管理者が既に判断した印）。ライブラリ内の同名組織は sites/site_for() が
        # 別途検出するため、ここでは NAME 衝突まで見ない
        type(self)._check_start()
        # 認証方式のクラスを渡されたら、組み立ては省略せず DPAPI から作る。
        # 値を手で並べる書き方（ClientCredentialsAuth(cid, secret, url)）を
        # 利用側に強いないため。既定（None）も同じ経路を通る。
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

    # 組織クラスのまま返す（with Sandbox() as sf: で sf.opportunities() の補完が効く）
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        """HTTP セッションを閉じる。with を使う場合は自動で呼ばれる。"""
        self._session.close()

    # ------------------------------------------------------------------ query
    @measure
    def query(self, soql: str) -> Table:
        """SOQL クエリを実行してレコードを返す（全件取得・ページ送り自動）。

        レポート API と違って**行数の上限がない**ので、
        2000 行を超えるデータはこちらで取る。

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
        records: list[dict] = []
        logger.debug("Salesforce SOQL取得開始")
        path = self.data_path(f"/query?q={urllib.parse.quote(soql)}")
        while path:
            result, _ = self.request("GET", path, component="query")
            if not isinstance(result, dict):
                break
            for record in result.get("records", []):
                record.pop("attributes", None)  # メタ情報は業務データに不要
                records.append(record)
            # done が真なら次のページは無い
            path = "" if result.get("done", True) else result.get("nextRecordsUrl", "")
        logger.debug("Salesforce SOQL取得完了: 件数=%d", len(records))
        # 0 件のときは列を空で返す。``list(records[0])`` は 0 件だと例外になるため、
        # 分岐して空リストを返す（実装の意図を明示するため ``else []`` を付ける）。
        columns = list(records[0]) if records else []
        return Table(columns, records)

    # ------------------------------------------------------------------- CRUD
    @measure
    def get(self, object_name: str, record_id: str) -> dict:
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
    def insert(self, object_name: str, data: dict) -> str:
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
    def update(self, object_name: str, record_id: str, data: dict) -> None:
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
    def upsert(self, object_name: str, external_id_field: str, data: dict) -> None:
        """外部 ID で upsert する（一致すれば更新、なければ作成）。

        Args:
            object_name: オブジェクトの API 参照名。
            external_id_field: 外部 ID 項目の API 参照名（例: "ExternalId__c"）。
            data: 項目と値。external_id_field の値を含めること。

        Raises:
            SalesforceExternalIDMissingError: data に external_id_field が無い場合。
        """
        if is_dry_run():
            dry_run_log("Salesforce %s を upsert（%s）: %s", object_name, external_id_field, data)
            return
        if external_id_field not in data:
            raise SalesforceExternalIDMissingError(object_name, external_id_field)
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
        body: dict | None = None,
        component: str = "other",
    ) -> tuple[dict | list | str | None, dict]:
        """REST API を呼び、(レスポンス本文, レスポンスヘッダー) を返す。

        すべての API 呼び出しがここを通る。計測と、401 のときの再認証もここで行う。
        通常は query() / get() 等を使い、このメソッドは
        ライブラリに無い API を叩くときだけ使う。

        Args:
            method: HTTP メソッド（GET / POST / PATCH / DELETE）。
            path: "/services/data/..." から始まるパス。
            body: JSON で送る辞書（省略可）。
            component: 計測での呼び出し元の区別（"query" / "crud" / "report"）。

        Raises:
            SalesforceRequestError: API がエラーを返した場合。
            SalesforceConnectionError: ネットワークの問題で接続できない場合。
        """
        start = time.perf_counter()
        is_reauthenticated = False
        # 初回送信をループの前で行い、response を必ず束縛する。
        # その下のループは 5xx/429 の一時障害だけを拾うので、初回送信と
        # 合計で最大 MAX_ATTEMPTS 回になる（試行 1..MAX_ATTEMPTS-1 = 2 回まで再試行）。
        # pyright から見ても response は Optional にならない
        response = self._send(method, self._request_url(path), body)

        for attempt in range(1, MAX_ATTEMPTS):
            reason = _retry_reason(response.status_code)
            if not reason:
                # 成功、または 4xx のようにリトライしても直らない永続的な失敗
                break
            # 5xx と 429 は Salesforce 側の一時的な事情なので、待って試し直す
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
            # instance_url は再認証で変わりうるので、毎回組み立て直す
            response = self._send(method, self._request_url(path), body)

        # 401 の再認証は試行回数を消費しない別ルート。一時障害のリトライ中に
        # 出ても、ループの外で1回だけ拾う。既に再認証済み（is_reauthenticated）なら
        # 何もしない。2回続けて 401 になるのは設定の問題なので、リトライで隠さず
        # 下の SalesforceRequestError に落とす
        if response.status_code == HTTP_UNAUTHORIZED and not is_reauthenticated:
            logger.debug("401 を受け取ったのでトークンを取り直します: %s", path)
            self.metrics.record_retry(component, RetryReason.REAUTH)
            self._authenticate()
            is_reauthenticated = True
            response = self._send(method, self._request_url(path), body)

        # response は初回送信で必ず束縛済み
        is_error = response.status_code >= HTTP_BAD_REQUEST
        self.metrics.record_call(component, time.perf_counter() - start, is_error=is_error)

        limit_info = response.headers.get("Sforce-Limit-Info")
        if limit_info:
            self.metrics.update_api_usage(limit_info)

        if is_error:
            raise SalesforceRequestError(method, path, response.status_code, response.text)

        return self._body_of(response), dict(response.headers)

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

    def _send(self, method: str, url: str, body: dict | None) -> requests.Response:
        """HTTP リクエストを1回送る。"""
        try:
            return self._session.request(method, url, json=body, timeout=self.TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as e:
            raise SalesforceConnectionError(url, e) from e

    @staticmethod
    def _body_of(response: requests.Response) -> dict | list | str | None:
        """レスポンス本文を、内容に応じて辞書・リスト・文字列・None で返す。"""
        if not response.text:
            return None  # DELETE や PATCH は本文が空で返る
        if response.headers.get("Content-Type", "").startswith("application/json"):
            return response.json()
        return response.text

    def _authenticate(self) -> None:
        """トークンを取り直し、以降のリクエストに使うヘッダーを差し替える。"""
        self._access_token, self._instance_url = self.auth.fetch()
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


# ── 内部ヘルパー ──────────────────────────────────────────────────────────────


def _retry_reason(status_code: int) -> str:
    """やり直す価値のあるステータスなら、その理由を返す。それ以外は空文字。"""
    if status_code >= HTTP_SERVER_ERROR:
        return RetryReason.SERVER_ERROR  # Salesforce 側の一時的な不調
    if status_code == HTTP_TOO_MANY_REQUESTS:
        return RetryReason.RATE_LIMIT  # 同時実行数の制限。待てば通ることがある
    return ""
