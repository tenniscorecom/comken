"""認証情報の登録画面（GUI）のテスト。

画面の操作そのものは試さず、キー名を組み立てる純粋関数と、
画面が組み立てられること（スモーク）だけを確認する。
保存先は tmp_path へ逃がし、実際に登録済みの認証情報には触らない。
"""

import pytest

from comken.toolbox.credentials.gui import build_credential_name, split_name_for_edit
from comken.toolbox.credentials.importer import credential_name


class TestBuildCredentialName:
    """フォームの入力を検証して、保存キーを組み立てる。"""

    def test_builds_name(self):
        name, error = build_credential_name("site_a", "client_secret")
        assert name == "site_a_client_secret"
        assert error is None

    def test_strips_whitespace(self):
        """前後の空白は取る（コピペで混ざりやすい）。"""
        name, _ = build_credential_name(" site_a ", " client_id ")
        assert name == "site_a_client_id"

    def test_empty_system_returns_error(self):
        name, error = build_credential_name("", "client_id")
        assert name is None
        assert "システム名" in error

    def test_empty_field_returns_error(self):
        name, error = build_credential_name("site_a", "")
        assert name is None
        assert "項目名" in error

    def test_japanese_system_returns_error(self):
        """日本語やスペースは使えない（キー名は半角英数字とアンダースコアだけ）。"""
        name, error = build_credential_name("サイトA", "client_id")
        assert name is None
        assert "半角英数字" in error

    def test_japanese_field_returns_error(self):
        name, error = build_credential_name("site_a", "クライアントID")
        assert name is None
        assert "半角英数字" in error


class TestSplitNameForEdit:
    """登録済みキー名を、登録し直すためのフォーム入力へ戻す。

    分割そのものが「元の入力どおり」である保証はない（項目名に何語入るかは
    キー名だけからは分からない）。保証するのは、フォームへ入れ直して
    そのまま保存すると同じキー名に戻ること（上書きが狙った相手に当たること）だけ。
    """

    @pytest.mark.parametrize(
        ("system", "field"),
        [
            ("site_a", "client_secret"),  # importer 標準の2語項目名
            ("salesforce", "password"),  # 1語項目名（split_credential_name は None を返す）
            ("site_a", "token"),  # システム名にアンダースコアを含む1語項目名
            ("kintai_admin", "refresh_token"),  # 両方にアンダースコアを含む
        ],
    )
    def test_round_trips_back_to_the_same_name(self, system, field):
        """どんな組み合わせでも、フォームへ戻して組み立て直すと元のキー名に一致する。"""
        name = credential_name(system, field)

        recovered_system, recovered_field = split_name_for_edit(name)

        assert credential_name(recovered_system, recovered_field) == name

    def test_falls_back_when_standard_split_returns_none(self):
        """項目名が1語だと split_credential_name() は None を返すので、末尾の _ で割る。"""
        recovered_system, recovered_field = split_name_for_edit("salesforce_password")

        assert (recovered_system, recovered_field) == ("salesforce", "password")


class TestWindow:
    """画面が組み立てられること（表示はしない）。"""

    def test_window_builds_and_closes(self, tmp_path):
        import tkinter as tk

        from comken.toolbox.credentials.gui import CredentialsApp

        try:
            root = tk.Tk()
        except tk.TclError:
            pytest.skip("画面のない環境では GUI を起動できない")

        root.withdraw()  # 画面には出さない
        try:
            app = CredentialsApp(root, path=tmp_path / "system-id.enc")
            app._refresh()  # 一覧の更新が例外なく動くこと
            assert app.listbox.size() == 0  # 空の保存先なので1件もない
        finally:
            root.destroy()

    def test_selecting_an_existing_key_fills_the_form(self, tmp_path):
        """左の一覧から選ぶと、システム名・項目名が自動入力され、値欄は空になる。

        登録し直すときに system/field を手で打ち直させない、が狙い
        （手で打つと typo で別キーとして新規登録されてしまう）。
        """
        import tkinter as tk

        from comken.toolbox.credentials.gui import CredentialsApp
        from comken.toolbox.credentials.store import save_credential

        try:
            root = tk.Tk()
        except tk.TclError:
            pytest.skip("画面のない環境では GUI を起動できない")

        root.withdraw()
        try:
            path = tmp_path / "system-id.enc"
            save_credential("salesforce_password", "old-value", path)
            app = CredentialsApp(root, path=path)
            app.value_var.set("残っていたら失敗")

            app.listbox.selection_set(0)
            app._on_select_existing(tk.Event())

            assert app.system_var.get() == "salesforce"
            assert app.field_var.get() == "password"
            assert app.value_var.get() == ""  # 値は保持していないので空にする
        finally:
            root.destroy()
