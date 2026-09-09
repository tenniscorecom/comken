"""認証情報の登録画面（GUI）のテスト。

画面の操作そのものは試さず、入力値を検証する純粋関数と、
画面が組み立てられること（スモーク）だけを確認する。
保存先は tmp_path へ逃がし、実際に登録済みの認証情報には触らない。
"""

import pytest

from comken.toolbox.credentials.gui import build_credential_name, split_name_for_edit


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


class TestSplitNameForEdit:
    """``list_names()`` が返した ``(サイト名, 項目名)`` をフォーム入力へ戻す。

    入れ子構造では ``list_names()`` の戻り値がそのまま ``(サイト名, 項目名)`` の
    タプルなので、 変換は不要。 ただし画面側では表示用に ``site.field`` 形式へ
    連結しているので、 テストでも同じ連結ルールを確認する。
    """

    def test_round_trips_through_display_format(self):
        """どの組み合わせでも表示形式に戻して組み立て直すと ``(サイト名, 項目名)`` が一致する。"""
        # ``(site, field)`` を作って、 実際の画面表示と同じ連結→分割を一周する
        pair = ("kintai_admin", "refresh_token")
        display = f"{pair[0]}.{pair[1]}"

        recovered_site, recovered_field = split_name_for_edit(pair)

        assert (recovered_site, recovered_field) == pair
        # 表示形式と ``(サイト, 項目)`` が矛盾しないことを確認
        assert display == f"{recovered_site}.{recovered_field}"

    def test_works_for_one_word_field_name(self):
        """1語の項目名でも ``(サイト名, 項目名)`` として素直に返る。"""
        pair = ("salesforce", "password")
        recovered_site, recovered_field = split_name_for_edit(pair)
        assert (recovered_site, recovered_field) == ("salesforce", "password")


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

            app.listbox.selection_set(0)
            app._on_select_existing(tk.Event())

            assert app.system_var.get() == "salesforce"
            assert app.field_var.get() == "password"
            assert app.value_var.get() == ""  # 値は保持していないので空にする
        finally:
            root.destroy()
