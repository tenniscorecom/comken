"""認証情報の登録画面（GUI）のテスト。

画面の操作そのものは試さず、入力値を検証する純粋関数と、
画面が組み立てられること（スモーク）だけを確認する。
保存先は tmp_path へ逃がし、実際に登録済みの認証情報には触らない。
"""

import pytest

from comken.toolbox.credentials.gui import build_credential_name


class TestBuildCredentialName:
    """フォームの入力を検証して、 ``(サイト名, 項目名)`` を組み立てる。"""

    def test_builds_pair(self):
        pair, error = build_credential_name("site_a", "client_secret")
        assert pair == ("site_a", "client_secret")
        assert error is None

    def test_strips_whitespace(self):
        """前後の空白は取る（コピペで混ざりやすい）。"""
        pair, _ = build_credential_name(" site_a ", " client_id ")
        assert pair == ("site_a", "client_id")

    def test_empty_site_returns_error(self):
        pair, error = build_credential_name("", "client_id")
        assert pair is None
        assert error is not None
        assert "サイト名" in error

    def test_empty_field_returns_error(self):
        pair, error = build_credential_name("site_a", "")
        assert pair is None
        assert error is not None
        assert "項目名" in error

    def test_japanese_site_returns_error(self):
        """日本語やスペースは使えない（名前は半角英数字とアンダースコアだけ）。"""
        pair, error = build_credential_name("サイトA", "client_id")
        assert pair is None
        assert error is not None
        assert "半角英数字" in error

    def test_japanese_field_returns_error(self):
        pair, error = build_credential_name("site_a", "クライアントID")
        assert pair is None
        assert error is not None
        assert "半角英数字" in error


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
            assert app.tree.get_children() == ()  # 空の保存先なので1件もない
        finally:
            root.destroy()

    def test_selecting_an_existing_pair_fills_the_form(self, tmp_path):
        """左の一覧から ``site.field`` を選ぶと、 サイト名・項目名が自動入力され、 値欄は空になる。

        登録し直すときに site/field を手で打ち直させない、が狙い
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
            save_credential("salesforce", "password", "old-value", path)
            app = CredentialsApp(root, path=path)
            app.value_var.set("残っていたら失敗")

            app.tree.selection_set("salesforce.password")
            app._on_select_existing(tk.Event())

            assert app.system_var.get() == "salesforce"
            assert app.field_var.get() == "password"
            assert app.value_var.get() == ""  # 値は保持していないので空にする
        finally:
            root.destroy()

    def test_grouping_multiple_fields_under_one_site(self, tmp_path):
        """同じサイトの複数項目は、1つの親ノードの下にまとまる。"""
        import tkinter as tk

        from comken.toolbox.credentials.gui import CredentialsApp
        from comken.toolbox.credentials.store import save_credentials

        try:
            root = tk.Tk()
        except tk.TclError:
            pytest.skip("画面のない環境では GUI を起動できない")

        root.withdraw()
        try:
            path = tmp_path / "system-id.enc"
            save_credentials(
                {
                    "salesforce": {"client_id": "a", "client_secret": "b"},
                    "kintai": {"password": "c"},
                },
                path,
            )
            app = CredentialsApp(root, path=path)

            # list_names() は (サイト名, 項目名) でソートして返すため、
            # サイト名のアルファベット順（kintai → salesforce）で並ぶ
            assert app.tree.get_children() == ("kintai", "salesforce")
            assert app.tree.get_children("salesforce") == (
                "salesforce.client_id",
                "salesforce.client_secret",
            )
            assert app.tree.item("salesforce", "text") == "salesforce（2件）"
        finally:
            root.destroy()

    def test_selecting_a_site_node_fills_only_the_site_name(self, tmp_path):
        """サイト行（親）を選んだだけでは項目名は定まらないので、空のままにする。"""
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
            save_credential("salesforce", "password", "old-value", path)
            app = CredentialsApp(root, path=path)

            app.tree.selection_set("salesforce")
            app._on_select_existing(tk.Event())

            assert app.system_var.get() == "salesforce"
            assert app.field_var.get() == ""
        finally:
            root.destroy()
