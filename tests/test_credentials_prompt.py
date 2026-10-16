"""新しいパスワードをCLIから2回入力させ、Credentials へ保存する prompt_new_password() のテスト。

``_read_masked()`` は実際のコンソール（msvcrt）を読むため、単体テストでは
そこをモックして「何回目にどの値を返すか」だけを差し替える。保存側は
実際の Credentials（tmp_path の DPAPI ストア）を使い、setattr → save() の
連携まで含めて確かめる。
"""

from unittest.mock import MagicMock, patch

import pytest

from comken.exceptions import CredentialNotFoundError, PasswordRejectedError
from comken.toolbox.credentials.prompt import change_password, prompt_new_password
from comken.toolbox.credentials.store import Credentials, load_credential

_READ_MASKED = "comken.toolbox.credentials.prompt._read_masked"


@pytest.fixture
def store(tmp_path):
    return tmp_path / "system-id.enc"


class TestPromptNewPassword:
    def test_returns_value_and_saves_it(self, store, capsys):
        cred = Credentials("ams", store)
        with patch(_READ_MASKED, side_effect=["new-pass", "new-pass"]):
            assert prompt_new_password(cred) == "new-pass"
        assert load_credential("ams", "password", store) == "new-pass"
        assert capsys.readouterr().out == ""

    def test_saves_under_the_given_field(self, store):
        cred = Credentials("ams", store)
        with patch(_READ_MASKED, side_effect=["new-pass", "new-pass"]):
            prompt_new_password(cred, "pin")
        assert load_credential("ams", "pin", store) == "new-pass"

    def test_retries_when_entries_do_not_match(self, store, capsys):
        cred = Credentials("ams", store)
        with patch(
            _READ_MASKED,
            side_effect=["typo", "different", "new-pass", "new-pass"],
        ):
            assert prompt_new_password(cred) == "new-pass"
        assert "一致しませんでした" in capsys.readouterr().out

    def test_retries_when_first_entry_is_empty(self, store, capsys):
        cred = Credentials("ams", store)
        with patch(_READ_MASKED, side_effect=["", "new-pass", "new-pass"]):
            assert prompt_new_password(cred) == "new-pass"
        assert "空のパスワード" in capsys.readouterr().out

    def test_label_is_used_in_prompt(self, store):
        cred = Credentials("ams", store)
        with patch(_READ_MASKED, side_effect=["value", "value"]) as mock_read:
            prompt_new_password(cred, label="ams のパスワード")
        first_call, second_call = mock_read.call_args_list
        assert first_call.args[0] == "ams のパスワード: "
        assert second_call.args[0] == "ams のパスワード（確認のため再入力）: "

    def test_timeout_seconds_is_passed_through(self, store):
        cred = Credentials("ams", store)
        with patch(_READ_MASKED, side_effect=["value", "value"]) as mock_read:
            prompt_new_password(cred, timeout_seconds=5.0)
        for call in mock_read.call_args_list:
            assert call.args[1] == 5.0

    def test_timeout_propagates_and_saves_nothing(self, store):
        """無人実行で入力が無いまま timeout_seconds を過ぎたら、保存せず TimeoutError にする。"""
        cred = Credentials("ams", store)
        with (
            patch(_READ_MASKED, side_effect=TimeoutError("timed out")),
            pytest.raises(TimeoutError),
        ):
            prompt_new_password(cred)
        with pytest.raises(CredentialNotFoundError):
            load_credential("ams", "password", store)


class TestChangePassword:
    """change_password() — 拒否されたら自動で聞き直し、成功したときだけ保存する。"""

    def test_saves_and_returns_submit_result_on_first_success(self, store):
        cred = Credentials("ams", store)
        submit = MagicMock(return_value="SECURE_PAGE")
        with patch(_READ_MASKED, side_effect=["new-pass", "new-pass"]):
            result = change_password(cred, submit)
        assert result == "SECURE_PAGE"
        submit.assert_called_once_with("new-pass")
        assert load_credential("ams", "password", store) == "new-pass"

    def test_retries_and_saves_the_accepted_value_not_the_rejected_one(self, store, capsys):
        cred = Credentials("ams", store)
        submit = MagicMock(side_effect=[PasswordRejectedError("記号が必要です"), "SECURE_PAGE"])
        with patch(
            _READ_MASKED,
            side_effect=["rejected", "rejected", "accepted", "accepted"],
        ):
            result = change_password(cred, submit)
        assert result == "SECURE_PAGE"
        assert submit.call_args_list[0].args == ("rejected",)
        assert submit.call_args_list[1].args == ("accepted",)
        # 拒否された値ではなく、受理された値だけが保存される
        assert load_credential("ams", "password", store) == "accepted"
        out = capsys.readouterr().out
        assert "記号が必要です" in out
        assert "1/3回目が拒否されました" in out

    def test_raises_and_saves_nothing_after_max_attempts(self, store):
        cred = Credentials("ams", store)
        submit = MagicMock(side_effect=PasswordRejectedError("文字数が足りません"))
        with (
            patch(
                _READ_MASKED,
                side_effect=["a", "a", "b", "b", "c", "c"],
            ),
            pytest.raises(PasswordRejectedError),
        ):
            change_password(cred, submit, max_attempts=3)
        assert submit.call_count == 3
        with pytest.raises(CredentialNotFoundError):
            load_credential("ams", "password", store)

    def test_max_attempts_one_does_not_retry(self, store):
        cred = Credentials("ams", store)
        submit = MagicMock(side_effect=PasswordRejectedError("拒否"))
        with (
            patch(_READ_MASKED, side_effect=["a", "a"]),
            pytest.raises(PasswordRejectedError),
        ):
            change_password(cred, submit, max_attempts=1)
        submit.assert_called_once()

    def test_max_attempts_below_one_raises_value_error(self, store):
        cred = Credentials("ams", store)
        with pytest.raises(ValueError, match="max_attempts"):
            change_password(cred, MagicMock(), max_attempts=0)

    def test_saves_under_the_given_field(self, store):
        cred = Credentials("ams", store)
        submit = MagicMock(return_value="SECURE_PAGE")
        with patch(_READ_MASKED, side_effect=["new-pass", "new-pass"]):
            change_password(cred, submit, "pin")
        assert load_credential("ams", "pin", store) == "new-pass"
