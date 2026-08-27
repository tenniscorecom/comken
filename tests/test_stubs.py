"""stubs.generate_stub() の相対パス処理のテスト。

``_parse_value`` に ``base_dir`` を渡したことで、 ``./input`` のような
相対パスを書いた ini からスタブを生成したときも、 ``Path`` 型ヒントが
出ること（=実行時とスタブの型が揃うこと）を確かめる。
"""


class TestStubRelativePath:
    """スタブ生成が ``_parse_value`` と同じ判定で ``Path`` を返すことを確認する。"""

    def test_relative_path_in_stub_uses_path_type(self, tmp_path):
        """相対パス（``./input``）が書かれた ini から ``generate_stub`` し、
        生成された ``.pyi`` に ``Path`` 型ヒントが出ていることを確認する。

        依頼前は ``_parse_value`` が ``base_dir`` を受け取らず相対パスを
        ``str`` のまま返していたため、スタブも ``INPUT: str`` となり、
        実行時が ``Path`` なら補完が嘘になる。 修正後は ``Path`` が出る。
        """
        from comken.core.config.stubs import generate_stub

        ini = tmp_path / "config.ini"
        ini.write_text(
            "[FILES]\nINPUT = ./input\nPLAIN = T_data\n",
            encoding="utf-8",
        )

        out = generate_stub(ini, tmp_path / "config.pyi")
        text = out.read_text(encoding="utf-8")

        # 相対パスは ``Path`` 型ヒントで出ている（実行時と一致）
        assert "INPUT: Path" in text
        # 区切りなしの値は変わらず ``str``
        assert "PLAIN: str" in text

    def test_absolute_path_in_stub_is_path(self, tmp_path):
        """絶対パス（``C:\\work``）が書かれた ini も従来どおり ``Path`` 型ヒントで出る。"""
        from comken.core.config.stubs import generate_stub

        ini = tmp_path / "config.ini"
        ini.write_text("[FILES]\nINPUT = C:\\work\\input\n", encoding="utf-8")

        out = generate_stub(ini, tmp_path / "config.pyi")
        text = out.read_text(encoding="utf-8")

        assert "INPUT: Path" in text
