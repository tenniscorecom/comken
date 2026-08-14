"""認証情報の暗号化保存を、実際に DPAPI で往復させて検証する。

DPAPI は Windows 標準機能なので、モックせず本物で暗号化・復号する。
保存先は tmp_path に逃がし、実行環境の %USERPROFILE%\\.comken は触らない。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import win32crypt

from comken.credentials import (
    Credentials,
    delete_credential,
    import_json,
    list_names,
    load_credential,
    save_credential,
    save_credentials,
)
from comken.credentials.__main__ import main
from comken.exceptions import (
    CredentialDecryptionError,
    CredentialImportError,
    CredentialNotFoundError,
    CredentialStoreCorruptedError,
    InvalidCredentialNameError,
)

SECRET = "s3cret-値-🔑"  # 日本語と絵文字を含めて UTF-8 の往復も確かめる


@pytest.fixture
def store(tmp_path) -> Path:
    return tmp_path / "credentials.dat"


class TestSaveAndLoad:
    def test_saved_value_comes_back(self, store):
        save_credential("site_a_client_secret", SECRET, store)
        assert load_credential("site_a_client_secret", store) == SECRET

    def test_file_does_not_contain_the_plain_value(self, store):
        save_credential("site_a_client_secret", SECRET, store)
        assert SECRET.encode("utf-8") not in store.read_bytes()

    def test_same_name_is_overwritten(self, store):
        save_credential("site_a_client_id", "old", store)
        save_credential("site_a_client_id", "new", store)
        assert load_credential("site_a_client_id", store) == "new"

    def test_other_names_survive_a_save(self, store):
        save_credential("site_a_client_id", "A", store)
        save_credential("site_b_client_id", "B", store)
        assert load_credential("site_a_client_id", store) == "A"

    def test_missing_name_raises(self, store):
        save_credential("site_a_client_id", "A", store)
        with pytest.raises(CredentialNotFoundError) as e:
            load_credential("site_a_client_secret", store)
        # 打ち間違いに気づけるよう、登録済みのキー名を示す
        assert "site_a_client_id" in str(e.value)

    def test_missing_file_is_treated_as_empty(self, store):
        with pytest.raises(CredentialNotFoundError):
            load_credential("site_a_client_id", store)
        assert list_names(store) == []

    def test_invalid_name_raises(self, store):
        with pytest.raises(InvalidCredentialNameError):
            save_credential("サイトA_client_id", "A", store)

    def test_invalid_name_is_not_saved(self, store):
        save_credential("site_a_client_id", "A", store)
        with pytest.raises(InvalidCredentialNameError):
            save_credentials({"site_b_client_id": "B", "site c": "C"}, store)
        # 1件でも不正なら、正しいほうも書き込まない（全部入るか1つも入らないか）
        assert list_names(store) == ["site_a_client_id"]

    def test_non_string_value_raises_type_error(self, store):
        """値の型違いは呼び出し側のバグなので、業務向けの例外にはしない。"""
        with pytest.raises(TypeError):
            save_credentials({"site_a_client_id": 12345}, store)

    def test_broken_file_raises_decryption_error(self, store):
        save_credential("site_a_client_id", "A", store)
        store.write_bytes(b"broken")
        with pytest.raises(CredentialDecryptionError):
            load_credential("site_a_client_id", store)

    def test_decryptable_but_broken_content_is_a_different_error(self, store):
        """復号できるのに中身が JSON でない場合は、取り込み直しを促す別の例外にする。"""
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_bytes(win32crypt.CryptProtectData(b"not json", None, None, None, None, 0))
        with pytest.raises(CredentialStoreCorruptedError):
            list_names(store)

    def test_decryptable_but_wrong_shape_is_corrupted(self, store):
        """キーと値がすべて文字列でなければ、壊れているものとして扱う。"""
        store.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps({"site_a_client_id": ["A"]}).encode("utf-8")
        store.write_bytes(win32crypt.CryptProtectData(raw, None, None, None, None, 0))
        with pytest.raises(CredentialStoreCorruptedError):
            list_names(store)

    def test_no_temporary_file_is_left_behind(self, store):
        save_credential("site_a_client_id", "A", store)
        assert list(store.parent.glob("*.tmp")) == []


class TestCredentialsAttributes:
    def test_attribute_reads_the_prefixed_key(self, store):
        save_credentials({"site_a_client_id": "A", "site_a_client_secret": SECRET}, store)
        cred = Credentials("site_a", store)
        assert cred.client_id == "A"
        assert cred.client_secret == SECRET

    def test_prefix_switches_the_whole_set(self, store):
        save_credentials({"site_a_client_id": "本番", "site_a_test_client_id": "テスト"}, store)
        assert Credentials("site_a", store).client_id == "本番"
        assert Credentials("site_a_test", store).client_id == "テスト"

    def test_invalid_prefix_raises(self, store):
        with pytest.raises(InvalidCredentialNameError):
            Credentials("site a", store)

    def test_empty_prefix_raises(self, store):
        with pytest.raises(InvalidCredentialNameError):
            Credentials("", store)

    def test_unregistered_attribute_raises(self, store):
        save_credential("site_a_client_id", "A", store)
        with pytest.raises(CredentialNotFoundError):
            _ = Credentials("site_a", store).password

    def test_dunder_attribute_raises_attribute_error(self, store):
        """copy や pickle が探る _ 始まりの属性は、通常の AttributeError で返す。"""
        cred = Credentials("site_a", store)
        with pytest.raises(AttributeError):
            _ = cred.__deepcopy__


class TestDeleteAndList:
    def test_delete_removes_only_that_name(self, store):
        save_credentials({"site_a_client_id": "A", "site_a_client_secret": "S"}, store)
        delete_credential("site_a_client_id", store)
        assert list_names(store) == ["site_a_client_secret"]

    def test_delete_missing_name_raises(self, store):
        with pytest.raises(CredentialNotFoundError):
            delete_credential("site_a_client_id", store)

    def test_list_names_is_sorted_and_has_no_values(self, store):
        save_credentials({"site_b_client_id": "B", "site_a_client_id": SECRET}, store)
        names = list_names(store)
        assert names == ["site_a_client_id", "site_b_client_id"]
        assert SECRET not in "".join(names)


class TestImportJson:
    def _write(self, tmp_path, body) -> Path:
        json_path = tmp_path / "認証情報.json"
        json_path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return json_path

    def test_nested_json_becomes_prefixed_keys(self, tmp_path, store):
        json_path = self._write(
            tmp_path,
            {
                "site_a": {"client_id": "A-ID", "client_secret": "A-SECRET"},
                "site_b": {"client_id": "B-ID", "client_secret": "B-SECRET"},
            },
        )
        names = import_json(json_path, store)
        assert names == [
            "site_a_client_id",
            "site_a_client_secret",
            "site_b_client_id",
            "site_b_client_secret",
        ]
        assert Credentials("site_b", store).client_secret == "B-SECRET"

    def test_import_keeps_keys_not_in_the_json(self, tmp_path, store):
        """組織ごとに JSON を分けて、何回かに分けて取り込める。"""
        save_credential("site_a_client_id", "A-ID", store)
        json_path = self._write(tmp_path, {"site_b": {"client_id": "B-ID"}})
        import_json(json_path, store)
        assert list_names(store) == ["site_a_client_id", "site_b_client_id"]

    def test_import_overwrites_the_same_key(self, tmp_path, store):
        save_credential("site_a_client_id", "old", store)
        json_path = self._write(tmp_path, {"site_a": {"client_id": "new"}})
        import_json(json_path, store)
        assert load_credential("site_a_client_id", store) == "new"

    def test_missing_file_raises(self, tmp_path, store):
        with pytest.raises(CredentialImportError):
            import_json(tmp_path / "ない.json", store)

    def test_broken_json_raises(self, tmp_path, store):
        json_path = tmp_path / "壊れた.json"
        json_path.write_text('{"site_a": ', encoding="utf-8")
        with pytest.raises(CredentialImportError):
            import_json(json_path, store)

    def test_flat_json_raises(self, tmp_path, store):
        """システム名ごとにまとめる形式なので、平らな JSON は形式違いとして弾く。"""
        json_path = self._write(tmp_path, {"site_a_client_id": "A-ID"})
        with pytest.raises(CredentialImportError):
            import_json(json_path, store)

    def test_non_string_value_raises(self, tmp_path, store):
        json_path = self._write(tmp_path, {"site_a": {"client_id": 12345}})
        with pytest.raises(CredentialImportError):
            import_json(json_path, store)

    def test_empty_json_raises(self, tmp_path, store):
        json_path = self._write(tmp_path, {})
        with pytest.raises(CredentialImportError):
            import_json(json_path, store)

    def test_invalid_key_raises_and_saves_nothing(self, tmp_path, store):
        json_path = self._write(tmp_path, {"サイトA": {"client_id": "A-ID"}})
        with pytest.raises(InvalidCredentialNameError):
            import_json(json_path, store)
        assert list_names(store) == []

    def test_empty_value_raises(self, tmp_path, store):
        """空の秘密値は書き忘れなので、登録の時点で止める。"""
        json_path = self._write(tmp_path, {"site_a": {"client_id": ""}})
        with pytest.raises(CredentialImportError):
            import_json(json_path, store)

    def test_empty_field_name_raises(self, tmp_path, store):
        """項目名が空だと site_a_ という中途半端なキー名が通ってしまう。"""
        json_path = self._write(tmp_path, {"site_a": {"": "A-ID"}})
        with pytest.raises(CredentialImportError):
            import_json(json_path, store)

    def test_colliding_keys_raise(self, tmp_path, store):
        """system_field をつなぐと同じキー名になる組み合わせは、黙って上書きさせない。"""
        json_path = self._write(
            tmp_path, {"site_a": {"client_id": "X"}, "site": {"a_client_id": "Y"}}
        )
        with pytest.raises(CredentialImportError):
            import_json(json_path, store)
        assert list_names(store) == []

    def test_duplicate_json_key_raises(self, tmp_path, store):
        """JSON の重複キーは既定では後勝ちで黙って消えるので、明示的に弾く。"""
        json_path = tmp_path / "重複.json"
        json_path.write_text(
            '{"site_a": {"client_id": "A"}, "site_a": {"client_id": "B"}}', encoding="utf-8"
        )
        with pytest.raises(CredentialImportError):
            import_json(json_path, store)


class TestSetCommand:
    """画面から入力して登録する入口（保存先は既定パスなので保存処理はモックする）。"""

    def _run(self, values, argv):
        with (
            patch("comken.credentials.__main__.save_credentials") as save,
            patch("comken.credentials.__main__.load_credential", return_value="x" * 5),
            patch("getpass.getpass", side_effect=values),
        ):
            code = main(argv)
        return code, save

    def test_input_becomes_prefixed_keys(self):
        """システム名と項目名をつないだキーで保存する。"""
        code, save = self._run(
            ["ID-VALUE", "SECRET-VALUE"], ["set", "site_a", "client_id", "client_secret"]
        )
        assert code == 0
        save.assert_called_once_with(
            {"site_a_client_id": "ID-VALUE", "site_a_client_secret": "SECRET-VALUE"}
        )

    def test_empty_input_saves_nothing(self, capsys):
        """途中で空を入れたら、それまでの入力ごと保存しない。"""
        _, save = self._run(["ID-VALUE", ""], ["set", "site_a", "client_id", "client_secret"])
        save.assert_not_called()
        assert "値が空です" in capsys.readouterr().err

    def test_value_is_not_printed(self, capsys):
        """入力した値を画面に出さない（桁数だけ）。"""
        self._run(["SECRET-VALUE"], ["set", "site_a", "client_secret"])
        assert "SECRET-VALUE" not in capsys.readouterr().out


class TestCommandLine:
    """コマンドの入口が動くこと（保存先は既定のパスなので、失敗系だけを見る）。"""

    def test_missing_json_returns_failure(self, tmp_path, capsys):
        assert main(["import", str(tmp_path / "ない.json")]) == 1
        assert "エラー:" in capsys.readouterr().err

    def test_unknown_command_exits(self):
        with pytest.raises(SystemExit):
            main(["unknown"])

    def test_no_command_exits(self):
        with pytest.raises(SystemExit):
            main([])
