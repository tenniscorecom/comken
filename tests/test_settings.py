"""comken 自身の設定（settings.ini）の読み込みを検証する。

実ファイル（リポジトリ直下の settings.ini）には触らず、パスを差し替えて確かめる。
"""

from pathlib import Path

import pytest

from comken import settings
from comken.exceptions import (
    SettingsCreatedFromExampleError,
    SettingsKeyNotFoundError,
    SettingsSectionNotFoundError,
)

BODY = """[SALESFORCE_DOWNLOADER]
MASTER_PATH = \\server\\share\\レポート管理表.xlsx
HISTORY_PATH = \\server\\share\\ダウンロード履歴.csv
"""


@pytest.fixture
def ini(tmp_path, monkeypatch):
    """settings.ini と example を tmp_path に用意する。"""
    path = tmp_path / "settings.ini"
    monkeypatch.setattr(settings, "SETTINGS_PATH", path)
    monkeypatch.setattr(settings, "EXAMPLE_PATH", tmp_path / "settings.ini.example")
    settings.reload()
    yield path
    settings.reload()  # 実ファイルの読み込み結果を持ち越さない


class TestGet:
    def test_reads_the_value(self, ini):
        ini.write_text(BODY, encoding="utf-8")
        assert settings.get("SALESFORCE_DOWNLOADER", "MASTER_PATH").endswith("レポート管理表.xlsx")

    def test_get_path_returns_a_path(self, ini):
        ini.write_text(BODY, encoding="utf-8")
        assert isinstance(settings.get_path("SALESFORCE_DOWNLOADER", "HISTORY_PATH"), Path)

    def test_keys_keep_their_case(self, ini):
        """config.ini と同じく、書いたとおりの大文字で引く。"""
        ini.write_text(BODY, encoding="utf-8")
        with pytest.raises(SettingsKeyNotFoundError):
            settings.get("SALESFORCE_DOWNLOADER", "master_path")

    def test_missing_section_raises(self, ini):
        ini.write_text(BODY, encoding="utf-8")
        with pytest.raises(SettingsSectionNotFoundError):
            settings.get("無いセクション", "MASTER_PATH")

    def test_missing_key_raises(self, ini):
        ini.write_text(BODY, encoding="utf-8")
        with pytest.raises(SettingsKeyNotFoundError) as e:
            settings.get("SALESFORCE_DOWNLOADER", "無いキー")
        assert "MASTER_PATH" in str(e.value)  # 今あるキーを示して打ち間違いに気づかせる


class TestMissingFile:
    def test_creates_from_example_and_stops(self, ini):
        """仮の値のまま動かさないよう、作った時点で止める。"""
        settings.EXAMPLE_PATH.write_text(BODY, encoding="utf-8")
        with pytest.raises(SettingsCreatedFromExampleError):
            settings.get("SALESFORCE_DOWNLOADER", "MASTER_PATH")
        assert ini.is_file()  # 次に開いて書き換えられるよう、ファイルは作っておく

    def test_without_example_reports_the_missing_template(self, ini):
        with pytest.raises(SettingsCreatedFromExampleError) as e:
            settings.get("SALESFORCE_DOWNLOADER", "MASTER_PATH")
        assert "雛形" in str(e.value)


class TestRealExample:
    def test_repository_example_has_the_downloader_section(self):
        """リポジトリの settings.ini.example が、実際に使うキーを含んでいる。"""
        text = (Path(__file__).resolve().parent.parent / "settings.ini.example").read_text(
            encoding="utf-8"
        )
        assert "[SALESFORCE_DOWNLOADER]" in text
        assert "MASTER_PATH" in text
        assert "HISTORY_PATH" in text
