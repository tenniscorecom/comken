"""新しいパスワードをCLIから2回入力させる prompt_new_password() のテスト。

getpass.getpass() は実際の端末入力を読むため、呼び出しをモックして
「何回目にどの値を返すか」だけを差し替える。
"""

from unittest.mock import patch

from comken.toolbox.credentials.prompt import prompt_new_password


class TestPromptNewPassword:
    def test_returns_value_when_both_entries_match(self, capsys):
        with patch("getpass.getpass", side_effect=["new-pass", "new-pass"]):
            assert prompt_new_password() == "new-pass"
        assert capsys.readouterr().out == ""

    def test_retries_when_entries_do_not_match(self, capsys):
        with patch(
            "getpass.getpass",
            side_effect=["typo", "different", "new-pass", "new-pass"],
        ):
            assert prompt_new_password() == "new-pass"
        assert "一致しませんでした" in capsys.readouterr().out

    def test_retries_when_first_entry_is_empty(self, capsys):
        with patch("getpass.getpass", side_effect=["", "new-pass", "new-pass"]):
            assert prompt_new_password() == "new-pass"
        assert "空のパスワード" in capsys.readouterr().out

    def test_label_is_used_in_prompt(self):
        with patch("getpass.getpass", side_effect=["value", "value"]) as mock_getpass:
            prompt_new_password(label="ams のパスワード")
        first_call, second_call = mock_getpass.call_args_list
        assert first_call.args[0] == "ams のパスワード: "
        assert second_call.args[0] == "ams のパスワード（確認のため再入力）: "
