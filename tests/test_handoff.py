"""受け渡しフォルダ（Handoff）のテスト。

リポジトリのルートで python -m pytest tests/test_handoff.py -v
"""

import datetime

import pytest

from comken.exceptions import HandoffFilesMissingError
from comken.handoff import Handoff
from comken.utils.clock import today

DATE = datetime.date(2026, 8, 14)


@pytest.fixture
def folder(tmp_path):
    """受け渡しフォルダに見立てた空のフォルダ。"""
    return tmp_path / "受け渡し"


def _place(handoff, name, text="A,B\n1,2\n"):
    """受け渡しフォルダへファイルを置く（取得側または人の操作に相当）。"""
    path = handoff.path_of(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestPathOf:
    """置き場所の組み立て。"""

    def test_name_has_date_and_suffix(self, folder):
        handoff = Handoff(folder, date=DATE)
        assert handoff.path_of("売上レポート").name == "売上レポート_20260814.csv"

    def test_suffix_can_be_changed(self, folder):
        handoff = Handoff(folder, date=DATE, suffix=".xlsx")
        assert handoff.path_of("在庫").name == "在庫_20260814.xlsx"

    def test_date_defaults_to_today(self, folder):
        """日付を省略すると今日の日付が入る。"""
        assert today().strftime("%Y%m%d") in Handoff(folder).path_of("売上").name

    def test_path_is_in_the_folder(self, folder):
        assert Handoff(folder, date=DATE).path_of("売上").parent == folder


class TestFind:
    """置かれているかの確認。"""

    def test_returns_path_when_placed(self, folder):
        handoff = Handoff(folder, date=DATE)
        placed = _place(handoff, "売上レポート")
        assert handoff.find("売上レポート") == placed

    def test_returns_none_when_not_placed(self, folder):
        assert Handoff(folder, date=DATE).find("売上レポート") is None

    def test_yesterdays_file_is_not_used(self, folder):
        """前日のファイルが残っていても、今日の分としては使わない。"""
        handoff = Handoff(folder, date=DATE)
        _place(Handoff(folder, date=DATE - datetime.timedelta(days=1)), "売上レポート")
        assert handoff.find("売上レポート") is None

    def test_folder_itself_is_not_a_file(self, folder):
        """同じ名前のフォルダがあってもファイルとは見なさない。"""
        handoff = Handoff(folder, date=DATE)
        handoff.path_of("売上レポート").mkdir(parents=True)
        assert handoff.find("売上レポート") is None


class TestRequire:
    """揃っているかの確認と受け取り。"""

    def test_returns_paths_when_all_placed(self, folder):
        handoff = Handoff(folder, date=DATE)
        _place(handoff, "売上レポート")
        _place(handoff, "在庫レポート")

        files = handoff.require("売上レポート", "在庫レポート")

        assert list(files) == ["売上レポート", "在庫レポート"]  # 渡した順を保つ
        assert files["売上レポート"] == handoff.path_of("売上レポート")

    def test_missing_files_are_all_listed(self, folder):
        """足りないものは1件目で止めず、全部まとめて知らせる。"""
        handoff = Handoff(folder, date=DATE)
        _place(handoff, "在庫レポート")

        with pytest.raises(HandoffFilesMissingError) as error:
            handoff.require("売上レポート", "在庫レポート", "顧客レポート")

        message = str(error.value)
        assert "2 件足りません" in message
        assert "売上レポート_20260814.csv" in message
        assert "顧客レポート_20260814.csv" in message
        assert "在庫レポート" not in message  # 揃っているものは挙げない

    def test_message_shows_where_to_place(self, folder):
        """置き場所がメッセージに入る（手で置く人がそれだけで分かるように）。"""
        with pytest.raises(HandoffFilesMissingError) as error:
            Handoff(folder, date=DATE).require("売上レポート")
        assert str(folder) in str(error.value)

    def test_placing_by_hand_makes_it_pass(self, folder):
        """取得が失敗しても、手で置けば次の実行から通る。"""
        handoff = Handoff(folder, date=DATE)
        with pytest.raises(HandoffFilesMissingError):
            handoff.require("売上レポート")

        _place(handoff, "売上レポート")  # 人が手で置く

        assert handoff.require("売上レポート")["売上レポート"].is_file()

    def test_no_names_requires_nothing(self, folder):
        assert Handoff(folder, date=DATE).require() == {}


class TestMissing:
    """足りない名前の一覧。"""

    def test_returns_names_in_given_order(self, folder):
        handoff = Handoff(folder, date=DATE)
        _place(handoff, "在庫レポート")
        assert handoff.missing("売上レポート", "在庫レポート", "顧客レポート") == [
            "売上レポート",
            "顧客レポート",
        ]

    def test_returns_empty_when_all_placed(self, folder):
        handoff = Handoff(folder, date=DATE)
        _place(handoff, "売上レポート")
        assert handoff.missing("売上レポート") == []
