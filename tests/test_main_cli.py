"""``python -m comken`` のサブコマンド振り分けと ``holidays`` の入口を検証する。

CLI の入口は ``comken/__main__.py`` 1か所に集約されている（`docs/HISTORY.md` の
「15. v2.0.0 に向けた整理」参照）。このテストはその約束を固定する:

- 既存のサブコマンド（``init`` / ``sf`` / ``cred`` / ``sfdl``）が
  ``python -m comken --help`` の一覧に出ること
- 新設の ``holidays``（別名 ``holiday``）が CLI 経由で ``build.main()`` を
  呼び、``company_calendar.csv`` がバイト単位で再現されること
- 「あるはずの登録」を消す（=登録漏れの回帰）と ``--help`` の一覧から消えて
  検知できることを示す（実装を壊して落ちる代表例）

サブコマンドの処理本体は ``sfdl check`` などと別ファイルで検証する
（``tests/test_sfdl_cli.py`` 等）。ここでは「``__main__`` が正しく名前を
受けるか」「``--help`` で利用者に見せる一覧に名前が出るか」だけを見る。
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, cast

import pytest

import comken
from comken.__main__ import _build_parser
from comken.__main__ import main as main_cli


class TestHelpListing:
    """``python -m comken --help`` の一覧。"""

    def test_help_lists_known_subcommands(self, capsys: pytest.CaptureFixture[str]) -> None:
        """``--help`` に既存のサブコマンドが全部並ぶ。

        「何を防いでいるか」: サブコマンドを追加するときに ``add_parser`` を
        呼び忘れると、利用者が ``python -m comken <新コマンド>`` を打ったときに
        「unknown command」になる。help 一覧は利用者が最初に読む場所なので、
        ここで名前を固定する。
        """
        main_cli(["--help"])
        out = capsys.readouterr().out
        for name in ("init", "sf", "cred", "sfdl", "holidays"):
            assert name in out, f"--help に {name} が無い: {out!r}"

    def test_help_lists_holidays_alias(self) -> None:
        """``--help`` に ``holidays`` の別名 ``holiday`` も並ぶ。

        ``sf`` / ``cred`` / ``sfdl`` と同じ ``aliases=[...]`` の流儀に合わせる。
        argparse は ``aliases=[...]`` で渡した名前を ``choices`` dict に
        元の名前と同じ parser オブジェクトで登録するので、両方が keys に
        入っていることを確認する。
        """
        parser = _build_parser()
        command_action = next(
            action
            for action in parser._actions  # type: ignore[attr-defined]
            if getattr(action, "dest", None) == "command"
        )
        choices = cast("dict[str, Any]", command_action.choices)
        assert "holidays" in choices, "holidays サブコマンドが choices に無い"
        assert "holiday" in choices, (
            f"holidays の別名 'holiday' が choices に無い: keys={list(choices.keys())!r}"
        )
        # 元の名前と別名が同じ parser を指している
        assert choices["holidays"] is choices["holiday"]


class TestHolidaysSubcommand:
    """``python -m comken holidays`` の動作。"""

    def test_holidays_writes_csv_identical_to_bundled(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """``holidays --path`` が ``company_calendar.csv`` をバイト単位で再現する。

        「何を防いでいるか」: 入口が ``comken.core.holidays.build.main()`` へ
        委譲されていること -- ここで日付フォーマットや改行コードが変わると
        VBA 側の ``ADODB.Stream`` が読めなくなり、業務が止まる。
        """
        out_path = tmp_path / "out.csv"
        with caplog.at_level(logging.INFO, logger="comken.core.holidays.build"):
            code = main_cli(["holidays", "--path", str(out_path)])
        assert code == 0, "holidays の終了コードが 0 ではない"

        bundled = (
            Path(comken.__file__).parent / "core" / "holidays" / "data" / "company_calendar.csv"
        )
        assert out_path.is_file(), f"holidays の書き出し先が無い: {out_path}"
        assert out_path.read_bytes() == bundled.read_bytes(), (
            "holidays の出力とバンドル済みの company_calendar.csv がバイト単位で一致しない"
        )

        # 「書き出し完了」が logging 経由で出ること（root に handler が既にある
        # ときは basicConfig をしない方針）。caplog は logging レベルで捕捉するので
        # stream 差し替えに左右されない
        messages = [record.getMessage() for record in caplog.records]
        assert any("書き出し完了" in m for m in messages), (
            f"holidays が「書き出し完了」ログを出していない: {messages!r}"
        )

    def test_holiday_alias_works(self, tmp_path: Path) -> None:
        """別名 ``holiday`` でも ``holidays`` と同じく動く。"""
        out_path = tmp_path / "out.csv"
        assert main_cli(["holiday", "--path", str(out_path)]) == 0
        assert out_path.is_file()

    def test_holidays_default_path_overwrites_bundled_without_change(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--path`` を渡さなくても、既定（バンドル先）とバイト単位で同じ結果が出る。

        ``--path`` 省略時に ``build.main()`` の既定パスがそのまま使われること
        を確かめる。書き出し先を ``tmp_path`` へ差し替えて、本体ファイルが
        変わらないことを確認する。
        """
        # 既定パスを tmp_path 配下へ差し替える（バンドル先を汚さないため）
        target = tmp_path / "default_company_calendar.csv"
        from comken.core.holidays import build as build_mod

        monkeypatch.setattr(build_mod, "COMPANY_HOLIDAYS_CSV_PATH", target)
        assert main_cli(["holidays"]) == 0

        bundled = (
            Path(comken.__file__).parent / "core" / "holidays" / "data" / "company_calendar.csv"
        )
        assert target.read_bytes() == bundled.read_bytes(), (
            "既定パスへの出力とバンドル済み company_calendar.csv が一致しない"
        )


class TestLoggingGuard:
    """``build.main()`` のログ設定が root に handler を勝手に付けないこと。"""

    def test_does_not_clobber_existing_root_handler(self, tmp_path: Path) -> None:
        """呼び出し前に root に handler がある環境では、basicConfig が走らない。

        「何を防いでいるか」: 社内基盤が root に logger を設定している状態で
        ``python -m comken holidays`` を呼ぶと、利用者が期待するログ形式が
        勝手に上書きされる。``build.main()`` は「root に handler が無いとき
        だけ basicConfig する」形なので、既存 handler を保持できる。
        """
        root = logging.getLogger()
        sentinel = logging.NullHandler()
        root.addHandler(sentinel)
        try:
            main_cli(["holidays", "--path", str(tmp_path / "out.csv")])
            # sentinel が消えていないこと（basicConfig は呼ばれない方針）
            assert sentinel in root.handlers, (
                "既存 handler が消えている（basicConfig が走った可能性がある）"
            )
        finally:
            root.removeHandler(sentinel)


class TestRegressionGuard:
    """実装を壊したら落ちる代表例。"""

    def test_removing_holidays_registration_is_caught_by_help(self) -> None:
        """``holidays`` サブコマンドの登録を消すと ``--help`` の一覧から消える。

        同じ「登録漏れ」を防ぐ検査を ``TestHelpListing.test_help_lists_known_subcommands``
        で先に置いてあるので、ここで「実装を壊したら本当に落ちる」ことを
        確かめて検査が生きていないと検知できない状態になっていないか確認する。
        具体的には、parser から holidays を一時的に消した状態を作り、
        help 出力の「サブコマンド一覧」行に ``holidays`` が含まれないことを確認する。
        argparse は choices dict と ``_choices_actions`` の両方に登録を持つので、
        両方から外す。
        """
        parser = _build_parser()
        command_action = next(
            action
            for action in parser._actions  # type: ignore[attr-defined]
            if getattr(action, "dest", None) == "command"
        )
        # 実装を壊したシミュレーション: holidays を choices と _choices_actions の
        # 両方から抜く
        choices = cast("dict[str, Any]", command_action.choices)
        removed_choice = choices.pop("holidays")
        removed_alias = choices.pop("holiday", None)
        removed_actions = [
            a
            for a in command_action._choices_actions
            if a.dest == "holidays"  # type: ignore[attr-defined]
        ]
        for action in removed_actions:
            command_action._choices_actions.remove(action)  # type: ignore[attr-defined]
        try:
            buffer = io.StringIO()
            parser.print_help(buffer)
            out = buffer.getvalue()
            # 「holidays (holiday)」の行が無くなっていることを見る
            assert "会社用カレンダー CSV" not in out, (
                f"holidays を登録から外したのに help に残っている: {out!r}"
            )
        finally:
            choices["holidays"] = removed_choice
            if removed_alias is not None:
                choices["holiday"] = removed_alias
            command_action._choices_actions.extend(removed_actions)  # type: ignore[attr-defined]
