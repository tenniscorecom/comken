r"""comken/toolbox/salesforce/direct/rotation.py — Salesforce 認証情報の定期ローテーション

ローテーションは既定で無効。同じ ECA を複数 PC で使う場合、有効にしてよいのは1台だけ。
DPAPI は Windows ユーザーと PC に紐付くため、実行した PC だけが新しい secret を持ち、
他の PC は旧資格情報の30日猶予後に接続できなくなるためである。

REST レスポンスの正確なスキーマは公式リファレンスで確認できていない。
社内環境で確認してフィールド名が異なった場合に1箇所だけ直せるよう、取り出しは
``_staged_credentials_of`` に集約している。
"""

import datetime
from dataclasses import dataclass
from pathlib import Path

from comken.core.clock import today as local_today
from comken.exceptions import (
    CredentialError,
    CredentialNotFoundError,
    SalesforceCredentialRotationError,
)
from comken.toolbox.credentials import load_credential, save_credentials
from comken.toolbox.salesforce.direct.client import SalesforceBase

DEFAULT_ROTATION_INTERVAL_DAYS = 60
ROTATION_COMPONENT = "credential_rotation"


@dataclass(frozen=True)
class _StagedCredentials:
    staged_id: str
    consumer_key: str
    consumer_secret: str


class SalesforceCredentialRotator:
    """ECA の資格情報を、期限到来時だけ安全な順序でローテーションする。

    ``is_enabled`` は config.ini の明示設定から渡す。既定で無効なのは、DPAPI が
    Windows ユーザーと PC に紐付き、同じ ECA を使う他 PC へ新 secret を配れないため。
    同じ ECA を複数 PC で使う場合、有効にしてよいのは1台だけである。
    """

    def __init__(
        self,
        client: SalesforceBase,
        app_id: str,
        credential_prefix: str,
        is_enabled: bool = False,
        interval_days: int = DEFAULT_ROTATION_INTERVAL_DAYS,
        credential_path: Path | None = None,
    ) -> None:
        self._client = client
        self._app_id = app_id
        self._credential_prefix = credential_prefix
        self._is_enabled = is_enabled
        self._interval_days = interval_days
        self._credential_path = credential_path

    def rotate_if_due(self, today: datetime.date | None = None) -> bool:
        """有効かつ指定日数を過ぎていれば実行し、実行したかを返す。"""
        if not self._is_enabled:
            return False
        rotation_date = today or local_today()
        if not self._is_due(rotation_date):
            return False
        self._rotate(rotation_date)
        return True

    def _is_due(self, today: datetime.date) -> bool:
        try:
            raw_date = load_credential(
                self._credential_name("last_rotation_date"), self._credential_path
            )
        except CredentialNotFoundError:
            return True
        try:
            last_rotation_date = datetime.date.fromisoformat(raw_date)
        except ValueError as error:
            raise SalesforceCredentialRotationError(
                f"最終ローテーション日が YYYY-MM-DD 形式ではありません: {raw_date}"
            ) from error
        return (today - last_rotation_date).days >= self._interval_days

    def _rotate(self, rotation_date: datetime.date) -> None:
        credentials_response, _ = self._client.request(
            "GET",
            self._client.data_path(f"/apps/oauth/credentials/{self._app_id}"),
            component=ROTATION_COMPONENT,
        )
        consumer_id = _consumer_id_of(credentials_response)
        base_path = self._client.data_path(f"/apps/oauth/credentials/{self._app_id}/{consumer_id}")
        response, _ = self._client.request(
            "POST", f"{base_path}/staged", component=ROTATION_COMPONENT
        )
        staged = _staged_credentials_of(response)

        # 保存前に rotate すると、新 secret を失ったまま旧 secret の猶予だけが進む。
        # 3値を一括保存できた場合に限って Salesforce 側を切り替える。
        try:
            save_credentials(
                {
                    self._credential_name("client_id"): staged.consumer_key,
                    self._credential_name("client_secret"): staged.consumer_secret,
                    self._credential_name("last_rotation_date"): rotation_date.isoformat(),
                },
                self._credential_path,
            )
        except (CredentialError, OSError) as error:
            raise SalesforceCredentialRotationError(
                f"新しい認証情報を DPAPI へ保存できませんでした: {error}"
            ) from error

        self._client.request(
            "PATCH",
            f"{base_path}/staged/{staged.staged_id}",
            body={"command": "rotate"},
            component=ROTATION_COMPONENT,
        )

    def _credential_name(self, suffix: str) -> str:
        return f"{self._credential_prefix}_{suffix}"


def _staged_credentials_of(response: dict | list | str | None) -> _StagedCredentials:
    """未確認のレスポンススキーマから必要な3項目を取り出す唯一の場所。"""
    if not isinstance(response, dict):
        raise SalesforceCredentialRotationError(
            "staged 作成 API の応答が JSON オブジェクトではありません。"
        )
    try:
        return _StagedCredentials(
            staged_id=str(response["id"]),
            consumer_key=str(response["consumerKey"]),
            consumer_secret=str(response["consumerSecret"]),
        )
    except KeyError as error:
        raise SalesforceCredentialRotationError(
            f"staged 作成 API の応答に必要な項目がありません: {error.args[0]}"
        ) from error


def _consumer_id_of(response: dict | list | str | None) -> str:
    """未確認の資格情報一覧スキーマから consumer ID を取り出す唯一の場所。"""
    candidate = response[0] if isinstance(response, list) and response else response
    if not isinstance(candidate, dict) or "consumerId" not in candidate:
        raise SalesforceCredentialRotationError(
            "資格情報取得 API の応答に consumerId がありません。"
        )
    return str(candidate["consumerId"])
