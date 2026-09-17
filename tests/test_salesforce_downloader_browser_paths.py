"""comken.services.salesforce_downloader.browser_paths のテスト。"""

from pathlib import Path

import pytest

from comken.services.salesforce_downloader.browser_paths import build_destination

BASE_BY_GROUP = {
    "営業部": r"\\server\share\営業部",
    "経理部": r"\\server\share\経理部",
}


class TestBuildDestination:
    """build_destination() — base/担当者/概要/レポート名.拡張子 の形で組み立てる。"""

    def test_builds_expected_path(self):
        dest = build_destination(BASE_BY_GROUP, "営業部", "山田", "顧客一覧", "月次顧客一覧")

        assert dest == Path(r"\\server\share\営業部") / "山田" / "顧客一覧" / "月次顧客一覧.csv"

    def test_uses_given_export_format(self):
        dest = build_destination(
            BASE_BY_GROUP, "営業部", "山田", "顧客一覧", "月次顧客一覧", export_format="xls"
        )

        assert dest.name == "月次顧客一覧.xls"

    def test_different_group_uses_different_base(self):
        dest = build_destination(BASE_BY_GROUP, "経理部", "田中", "請求一覧", "月次請求")

        assert dest == Path(r"\\server\share\経理部") / "田中" / "請求一覧" / "月次請求.csv"

    def test_unregistered_group_raises(self):
        with pytest.raises(ValueError, match="営業部"):
            build_destination(BASE_BY_GROUP, "未登録部署", "山田", "顧客一覧", "月次顧客一覧")

    def test_strips_forbidden_characters_from_names(self):
        dest = build_destination(BASE_BY_GROUP, "営業部", "山田/太郎", "顧客:一覧", "月次*顧客一覧")

        assert dest == Path(r"\\server\share\営業部") / "山田太郎" / "顧客一覧" / "月次顧客一覧.csv"

    def test_blank_name_falls_back_to_placeholder(self):
        dest = build_destination(BASE_BY_GROUP, "営業部", "", "顧客一覧", "月次顧客一覧")

        assert dest.parent.parent.name == "名称未設定"
