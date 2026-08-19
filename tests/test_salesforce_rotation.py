"""Salesforce ECA の認証情報ローテーションを検証する。"""

import datetime
from unittest.mock import Mock, call, patch

import pytest

from comken.exceptions import SalesforceCredentialRotationError
from comken.toolbox.salesforce.direct.rotation import SalesforceCredentialRotator

TODAY = datetime.date(2026, 8, 13)

# 差し替え先はすべてこのモジュールの中。毎回フルパスを書くと行が長くなるうえ、
# モジュールを移したときの直し漏れが起きやすい
_ROTATION = "comken.toolbox.salesforce.direct.rotation"


def _client() -> Mock:
    client = Mock()
    client.data_path.side_effect = lambda path: f"/services/data/v67.0{path}"
    client.request.side_effect = [
        ({"consumerId": "consumer-1"}, {}),
        ({"id": "staged-1", "consumerKey": "new-key", "consumerSecret": "new-secret"}, {}),
        (None, {}),
    ]
    return client


class TestSalesforceCredentialRotator:
    def test_uses_local_today_when_date_is_not_injected(self):
        client = _client()
        rotator = SalesforceCredentialRotator(client, "app-1", "site_a", is_enabled=True)

        with (
            patch(f"{_ROTATION}.local_today", return_value=TODAY) as current_date,
            patch(f"{_ROTATION}.load_credential", return_value="2026-08-01"),
        ):
            assert not rotator.rotate_if_due()

        current_date.assert_called_once_with()

    def test_rotates_after_saving_new_credentials(self):
        client = _client()
        rotator = SalesforceCredentialRotator(client, "app-1", "site_a", is_enabled=True)

        with (
            patch(f"{_ROTATION}.load_credential", return_value="2026-06-01"),
            patch(f"{_ROTATION}.save_credentials") as save,
        ):
            assert rotator.rotate_if_due(TODAY)

        assert client.request.call_args_list == [
            call(
                "GET",
                "/services/data/v67.0/apps/oauth/credentials/app-1",
                component="credential_rotation",
            ),
            call(
                "POST",
                "/services/data/v67.0/apps/oauth/credentials/app-1/consumer-1/staged",
                component="credential_rotation",
            ),
            call(
                "PATCH",
                "/services/data/v67.0/apps/oauth/credentials/app-1/consumer-1/staged/staged-1",
                body={"command": "rotate"},
                component="credential_rotation",
            ),
        ]
        save.assert_called_once_with(
            {
                "site_a_client_id": "new-key",
                "site_a_client_secret": "new-secret",
                "site_a_last_rotation_date": "2026-08-13",
            },
            None,
        )

    def test_does_not_rotate_when_dpapi_save_fails(self):
        client = _client()
        rotator = SalesforceCredentialRotator(client, "app-1", "site_a", is_enabled=True)

        with (
            patch(f"{_ROTATION}.load_credential", return_value="2026-06-01"),
            patch(f"{_ROTATION}.save_credentials", side_effect=OSError("保存失敗")),
            pytest.raises(SalesforceCredentialRotationError, match="DPAPI"),
        ):
            rotator.rotate_if_due(TODAY)

        assert [request.args[0] for request in client.request.call_args_list] == ["GET", "POST"]

    def test_is_disabled_by_default(self):
        client = _client()
        rotator = SalesforceCredentialRotator(client, "app-1", "site_a")

        assert not rotator.rotate_if_due(TODAY)
        client.request.assert_not_called()
