"""認証情報の登録画面（GUI）のテスト。

画面の操作そのものは試さず、キー名を組み立てる純粋関数と、
画面が組み立てられること（スモーク）だけを確認する。
保存先は tmp_path へ逃がし、実際に登録済みの認証情報には触らない。
"""

import pytest

from comken.toolbox.credentials.gui import build_credential_name


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
            app = CredentialsApp(root, path=tmp_path / "credentials.enc")
            app._refresh()  # 一覧の更新が例外なく動くこと
            assert app.listbox.size() == 0  # 空の保存先なので1件もない
        finally:
            root.destroy()
