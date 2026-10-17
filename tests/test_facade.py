"""comken の公開 API 検証。

`from comken import ...` には「何をするプロジェクトかに関係なく使う」土台だけを置く
（docs/ARCHITECTURE.md §3）。`__all__` が意図どおりであることをここで保証する。
"""

import comken


def test_facade_exposes_all_names() -> None:
    """__all__ に載っている名前が comken 直下から実際に取れる。"""
    for name in comken.__all__:
        assert hasattr(comken, name), f"公開名 {name} が comken 直下から取れない"


def test_facade_does_not_expose_internal_helpers() -> None:
    """内部実装（FileBase / transfer / cleanup_stale_tmp）は facade に出さない。"""
    for forbidden in ("FileBase", "transfer", "cleanup_stale_tmp"):
        assert forbidden not in comken.__all__, f"{forbidden} は facade に出してはいけない"


def test_facade_paths_module_does_not_exist() -> None:
    """Paths は toolbox/windows/ へ移し、facade には上げない。"""
    assert "Paths" not in comken.__all__


def test_facade_only_expected_names() -> None:
    """facade は意図した土台だけ。増えた名前が入っていないことを保証する。

    増えるべき時: 新しい土台（プロジェクト横断で必須）を足したとき。
    ここに書いたら AGENTS.md の「土台」欄にも書く。
    """
    expected = {
        "Config",
        "config",
        "debug",
        "dry_run",
        "Backoffice",
        "Intranet",
        "comken_logger",
    }
    assert set(comken.__all__) == expected


def test_facade_attributes_resolve_to_real_objects() -> None:
    """公開名前が None や空文字ではなく、対応するオブジェクトに解決される。"""
    # モジュール
    assert comken.config is not None
    # クラス
    assert comken.Config is not None
    # ログ設定モジュール
    assert comken.comken_logger is comken.core.logger
    assert comken.Backoffice is comken.core.logger.Backoffice
    assert comken.Intranet is comken.core.logger.Intranet
    # contextmanager（with で使える callable）
    assert callable(comken.debug)
    assert callable(comken.dry_run)


def test_exceptions_comken_error_is_importable() -> None:
    """`from comken.exceptions import ComkenError` で comken 全体の例外基底を取れる。

    利用プロジェクトが ``except ComkenError`` で全例外を捕捉できるように、
    この import 経路が壊れないことを保証する。facade の公開名ではないが、
    例外階層の公開入口として最も広く使われる。
    """
    # import 経路が壊れていないかを検証するのが目的なので、assert で参照する
    from comken.exceptions import ComkenError

    assert ComkenError is not None
    # ComkenError は str 表現が可能（エラーメッセージとして表示される）
    assert issubclass(ComkenError, BaseException)


def test_exceptions_category_bases_are_usable_for_broad_catch() -> None:
    """カテゴリ基底（ExcelError / BrowserError など）は個別例外の束ねる親として使える。

    利用プロジェクトが ``except ExcelError`` で Excel 関連を一括捕捉できるように、
    各カテゴリ基底から個別例外が派生していることを保証する。
    """
    from comken.exceptions import BrowserError, ComkenError, ExcelError

    # カテゴリ基底は ComkenError の派生（個別例外を束ねる基底として機能する）
    assert issubclass(ExcelError, ComkenError)
    assert issubclass(BrowserError, ComkenError)
