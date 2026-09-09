"""認証情報の暗号化保存を、実際に DPAPI で往復させて検証する。

DPAPI は Windows 標準機能なので、モックせず本物で暗号化・復号する。
保存先は tmp_path に逃がし、実行環境の %USERPROFILE%\\.rpa は触らない。

**保存形式は入れ子の ``{サイト名: {項目名: 値}}``**。サイト名と項目名はそれぞれ
個別に検証する。 ``solution_last_rotation_date`` のように項目名が3語以上でも
誤動作しないことが、 旧フラットキー実装から入れ子に変えた動機。
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import win32crypt

from comken.exceptions import (
    CredentialDecryptionError,
    CredentialImportError,
    CredentialNotFoundError,
    CredentialStoreCorruptedError,
    InvalidCredentialNameError,
)
from comken.toolbox.credentials import (
    Credentials,
    delete_credential,
    import_json,
    list_names,
    load_credential,
    save_credential,
    save_credentials,
)
from comken.toolbox.credentials.cli import main

SECRET = "s3cret-値-🔑"  # 日本語と絵文字を含めて UTF-8 の往復も確かめる


@pytest.fixture
def store(tmp_path) -> Path:
    return tmp_path / "system-id.enc"


class TestSaveAndLoad:
    def test_saved_value_comes_back(self, store):
        save_credential("site_a", "client_secret", SECRET, store)
        assert load_credential("site_a", "client_secret", store) == SECRET

    def test_file_does_not_contain_the_plain_value(self, store):
        save_credential("site_a", "client_secret", SECRET, store)
        assert SECRET.encode("utf-8") not in store.read_bytes()

    def test_same_pair_is_overwritten(self, store):
        save_credential("site_a", "client_id", "old", store)
        save_credential("site_a", "client_id", "new", store)
        assert load_credential("site_a", "client_id", store) == "new"

    def test_other_pairs_survive_a_save(self, store):
        save_credential("site_a", "client_id", "A", store)
        save_credential("site_b", "client_id", "B", store)
        assert load_credential("site_a", "client_id", store) == "A"

    def test_missing_pair_raises(self, store):
        save_credential("site_a", "client_id", "A", store)
        with pytest.raises(CredentialNotFoundError) as e:
            load_credential("site_a", "client_secret", store)
        # 打ち間違いに気づけるよう、登録済みのキー名を示す
        assert "site_a.client_id" in str(e.value)

    def test_missing_file_is_treated_as_empty(self, store):
        with pytest.raises(CredentialNotFoundError):
            load_credential("site_a", "client_id", store)
        assert list_names(store) == []

    def test_invalid_site_raises(self, store):
        with pytest.raises(InvalidCredentialNameError):
            save_credential("サイトA", "client_id", "A", store)

    def test_invalid_field_raises(self, store):
        """項目名側に使えない文字を入れた場合も、 サイト名が正しくても弾く。"""
        with pytest.raises(InvalidCredentialNameError):
            save_credential("site_a", "クライアントID", "A", store)

    def test_invalid_pair_is_not_saved(self, store):
        """1件でも不正なら、正しいほうも書き込まない（全部入るか1つも入らないか）。"""
        save_credential("site_a", "client_id", "A", store)
        with pytest.raises(InvalidCredentialNameError):
            save_credentials(
                {"site_b": {"client_id": "B"}, "site c": {"client_id": "C"}},
                store,
            )
        assert list_names(store) == [("site_a", "client_id")]

    def test_non_string_value_raises_type_error(self, store):
        """値の型違いは呼び出し側のバグなので、業務向けの例外にはしない。"""
        with pytest.raises(TypeError):
            save_credentials({"site_a": {"client_id": 12345}}, store)  # type: ignore

    def test_non_dict_value_raises_type_error(self, store):
        """``save_credentials`` の値は ``{サイト名: {項目名: str}}`` の入れ子前提。"""
        with pytest.raises(TypeError):
            save_credentials({"site_a": "client_id"}, store)  # type: ignore

    def test_broken_file_raises_decryption_error(self, store):
        save_credential("site_a", "client_id", "A", store)
        store.write_bytes(b"broken")
        with pytest.raises(CredentialDecryptionError):
            load_credential("site_a", "client_id", store)

    def test_decryptable_but_broken_content_is_a_different_error(self, store):
        """復号できるのに中身が JSON でない場合は、取り込み直しを促す別の例外にする。"""
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_bytes(win32crypt.CryptProtectData(b"not json", None, None, None, None, 0))
        with pytest.raises(CredentialStoreCorruptedError):
            list_names(store)

    def test_decryptable_but_wrong_shape_is_corrupted(self, store):
        """最上位が dict でない、 または値が文字列 dict でないものは壊れている。"""
        store.parent.mkdir(parents=True, exist_ok=True)
        # 値が dict ではなく list のケースは「キーと値がすべて文字列の形になっていない」
        raw = json.dumps({"site_a": ["A"]}).encode("utf-8")
        store.write_bytes(win32crypt.CryptProtectData(raw, None, None, None, None, 0))
        with pytest.raises(CredentialStoreCorruptedError):
            list_names(store)

    def test_decryptable_with_flat_shape_is_corrupted(self, store):
        """旧フラット形式 ``{"site_a_client_id": "A"}`` はもう受け付けない。"""
        store.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps({"site_a_client_id": "A"}).encode("utf-8")
        store.write_bytes(win32crypt.CryptProtectData(raw, None, None, None, None, 0))
        with pytest.raises(CredentialStoreCorruptedError):
            list_names(store)

    def test_no_temporary_file_is_left_behind(self, store):
        save_credential("site_a", "client_id", "A", store)
        assert list(store.parent.glob("*.tmp")) == []


class TestThreeWordFieldNames:
    """項目名が3語以上になっても、 旧実装の境界誤判定が再発しないことを確認する。

    旧フラットキー実装では ``solution_last_rotation_date`` を
    「サイト名 ``solution_last``、 項目名 ``rotation_date``」 と誤って分割していた
    （rotation.py が実際に ``last_rotation_date`` を保存するフィールド）。
    入れ子構造ではこの種の曖昧さが構造的に発生しないので、 同じシナリオが
    そのまま動くことをテストで担保する。
    """

    def test_round_trips(self, store):
        save_credential("solution", "last_rotation_date", "2026-01-01", store)
        assert load_credential("solution", "last_rotation_date", store) == "2026-01-01"

    def test_does_not_collide_with_two_word_field(self, store):
        """3語の項目名と2語の項目名が同じサイト内で衝突しないこと。"""
        save_credential("solution", "last_rotation_date", "DATE", store)
        save_credential("solution", "client_id", "ID", store)
        assert load_credential("solution", "last_rotation_date", store) == "DATE"
        assert load_credential("solution", "client_id", store) == "ID"


class TestCredentialsAttributes:
    def test_attribute_reads_the_value(self, store):
        save_credentials(
            {"site_a": {"client_id": "A", "client_secret": SECRET}},
            store,
        )
        cred = Credentials("site_a", store)
        assert cred.client_id == "A"
        assert cred.client_secret == SECRET

    def test_site_switches_the_whole_set(self, store):
        save_credentials(
            {"site_a": {"client_id": "本番"}, "site_a_test": {"client_id": "テスト"}},
            store,
        )
        assert Credentials("site_a", store).client_id == "本番"
        assert Credentials("site_a_test", store).client_id == "テスト"

    def test_invalid_site_raises(self, store):
        with pytest.raises(InvalidCredentialNameError):
            Credentials("site a", store)

    def test_empty_site_raises(self, store):
        with pytest.raises(InvalidCredentialNameError):
            Credentials("", store)

    def test_unregistered_attribute_raises(self, store):
        save_credential("site_a", "client_id", "A", store)
        with pytest.raises(CredentialNotFoundError):
            _ = Credentials("site_a", store).password

    def test_dunder_attribute_raises_attribute_error(self, store):
        """copy や pickle が探る _ 始まりの属性は、通常の AttributeError で返す。"""
        cred = Credentials("site_a", store)
        with pytest.raises(AttributeError):
            _ = cred.__deepcopy__

    def test_dropped_credentials_are_garbage_collected_and_registry_does_not_bloat(self, store):
        """参照を手放した ``Credentials`` が GC された後もレジストリが膨らまない。

        強参照のままだと ``Credentials`` 用済みになっても ``_cache`` の復号済み
        平文がプロセス終了まで残るため、 ``weakref.WeakSet`` にしている。
        """
        import gc

        from comken.toolbox.credentials import store as store_module

        save_credentials(
            {"site_a": {"client_id": "A", "client_secret": "S"}},
            store,
        )
        # Credentials を呼んでキャッシュを作り、レジストリに登録させる
        cred = Credentials("site_a", store)
        assert cred.client_id == "A"
        bucket_key = str(store)
        bucket = store_module._instances_by_path[bucket_key]
        assert len(bucket) == 1

        # 参照を手放して GC を促す
        del cred
        gc.collect()

        # WeakSet は参照を持たない要素を自動的に外すため、 レジストリは膨らまない
        assert len(bucket) == 0


class TestDeleteAndList:
    def test_delete_removes_only_that_pair(self, store):
        save_credentials(
            {"site_a": {"client_id": "A", "client_secret": "S"}},
            store,
        )
        delete_credential("site_a", "client_id", store)
        assert list_names(store) == [("site_a", "client_secret")]

    def test_delete_last_pair_in_site_clears_the_site(self, store):
        """サイト内の最後の項目を消したら、 サイト名ごと消える（空 dict を残さない）。"""
        save_credentials(
            {"site_a": {"client_id": "A"}, "site_b": {"client_id": "B"}},
            store,
        )
        delete_credential("site_a", "client_id", store)
        assert list_names(store) == [("site_b", "client_id")]

    def test_delete_missing_pair_raises(self, store):
        with pytest.raises(CredentialNotFoundError):
            delete_credential("site_a", "client_id", store)

    def test_list_names_is_sorted_and_has_no_values(self, store):
        save_credentials(
            {"site_b": {"client_id": "B"}, "site_a": {"client_id": SECRET}},
            store,
        )
        pairs = list_names(store)
        assert pairs == [("site_a", "client_id"), ("site_b", "client_id")]
        # 値（SECRET）がタプルの文字列表現にも Listbox の表示にも漏れていないこと
        joined = "\n".join(f"{s}.{f}" for s, f in pairs)
        assert SECRET not in joined


class TestImportJson:
    def _write(self, tmp_path, body) -> Path:
        json_path = tmp_path / "認証情報.json"
        json_path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return json_path

    def test_nested_json_is_imported_as_pairs(self, tmp_path, store):
        json_path = self._write(
            tmp_path,
            {
                "site_a": {"client_id": "A-ID", "client_secret": "A-SECRET"},
                "site_b": {"client_id": "B-ID", "client_secret": "B-SECRET"},
            },
        )
        pairs = import_json(json_path, store)
        assert pairs == [
            ("site_a", "client_id"),
            ("site_a", "client_secret"),
            ("site_b", "client_id"),
            ("site_b", "client_secret"),
        ]
        assert Credentials("site_b", store).client_secret == "B-SECRET"

    def test_import_keeps_keys_not_in_the_json(self, tmp_path, store):
        """組織ごとに JSON を分けて、何回かに分けて取り込める。"""
        save_credential("site_a", "client_id", "A-ID", store)
        json_path = self._write(tmp_path, {"site_b": {"client_id": "B-ID"}})
        import_json(json_path, store)
        assert list_names(store) == [
            ("site_a", "client_id"),
            ("site_b", "client_id"),
        ]

    def test_import_overwrites_the_same_pair(self, tmp_path, store):
        save_credential("site_a", "client_id", "old", store)
        json_path = self._write(tmp_path, {"site_a": {"client_id": "new"}})
        import_json(json_path, store)
        assert load_credential("site_a", "client_id", store) == "new"

    def test_missing_file_raises(self, tmp_path, store):
        with pytest.raises(CredentialImportError):
            import_json(tmp_path / "ない.json", store)

    def test_broken_json_raises(self, tmp_path, store):
        json_path = tmp_path / "壊れた.json"
        json_path.write_text('{"site_a": ', encoding="utf-8")
        with pytest.raises(CredentialImportError):
            import_json(json_path, store)

    def test_flat_json_raises(self, tmp_path, store):
        """入れ子ではなく平らな JSON は形式違いとして弾く。"""
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
        with pytest.raises(CredentialImportError):
            import_json(json_path, store)
        assert list_names(store) == []

    def test_empty_value_raises(self, tmp_path, store):
        """空の秘密値は書き忘れなので、登録の時点で止める。"""
        json_path = self._write(tmp_path, {"site_a": {"client_id": ""}})
        with pytest.raises(CredentialImportError):
            import_json(json_path, store)

    def test_empty_field_name_raises(self, tmp_path, store):
        """項目名が空だと登録しようがない（キーが空の dict になる）。"""
        json_path = self._write(tmp_path, {"site_a": {"": "A-ID"}})
        with pytest.raises(CredentialImportError):
            import_json(json_path, store)

    def test_duplicate_json_key_raises(self, tmp_path, store):
        """JSON の重複キーは既定では後勝ちで黙って消えるので、明示的に弾く。"""
        json_path = tmp_path / "重複.json"
        json_path.write_text(
            '{"site_a": {"client_id": "A"}, "site_a": {"client_id": "B"}}', encoding="utf-8"
        )
        with pytest.raises(CredentialImportError):
            import_json(json_path, store)


class TestCommandLine:
    """コマンドの入口が動くこと（保存先は既定のパスなので、失敗系だけを見る）。"""

    def test_gui_opens_the_window(self):
        """gui は登録画面を開くだけ（画面そのものは test_credentials_gui.py で見る）。"""
        with patch("comken.toolbox.credentials.gui.main") as open_window:
            assert main(["gui"]) == 0
        open_window.assert_called_once_with()

    def test_missing_json_returns_failure(self, tmp_path, capsys):
        assert main(["import", str(tmp_path / "ない.json")]) == 1
        assert "エラー:" in capsys.readouterr().err

    def test_unknown_command_exits(self):
        with pytest.raises(SystemExit):
            main(["unknown"])

    def test_no_command_exits(self):
        with pytest.raises(SystemExit):
            main([])
