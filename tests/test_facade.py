"""comken の公開 API 検証。

公開は2階層（仕様書 4.32）。``from comken import ...`` には
「何をするプロジェクトかに関係なく使う」土台だけを置き、部品は
``from comken.core import ...`` から取る。両方の ``__all__`` が意図どおりで、
互いに重複していないことをここで保証する。
"""

import comken
import comken.core


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


def test_core_exposes_parts() -> None:
    """comken.core は部品を公開し、その全てが実際に取れる。

    増えるべき時: core に部品を足して、利用側から使わせるとき。
    ここに書かないと `from comken.core import ...` で届かない。
    """
    expected = {
        "DateNameBuilder",
        "DateFileFinder",
        "DiffResult",
        "RowChange",
        "State",
        "Timer",
        "copy_file",
        "date_in_name",
        "delete_file",
        "delete_files",
        "diff_row",
        "diff_rows",
        "local_copy",
        "measure",
        "move_file",
        "normalize",
        "now",
        "project_dir",
        "remove_spaces",
        "retry",
        "strip_spaces",
        "today",
        "unzip",
        "wait_for_file",
        "wait_seconds",
        "wait_until",
        "wait_until_stable",
        "zip_files",
        "zip_folder",
    }
    assert set(comken.core.__all__) == expected
    for name in comken.core.__all__:
        assert hasattr(comken.core, name), f"公開名 {name} が comken.core から取れない"


def test_core_does_not_expose_internal_helpers() -> None:
    """core の内部実装は公開しない。利用側が触ると変更できなくなるため。"""
    forbidden = (
        "FileBase",
        "cleanup_stale_tmp",
        "col_to_num",
        "column_number",
    )
    for name in forbidden:
        assert name not in comken.core.__all__, f"{name} は内部実装なので公開しない"


def test_facade_and_core_do_not_overlap() -> None:
    """同じ名前が2つの入口から取れると、どちらで書くか迷う。

    書くときの優先順位は「comken 直下が第一選択、無いものだけ comken.core」
    （仕様書 4.32）。重複するとこの順序が意味を失う。
    """
    overlap = set(comken.__all__) & set(comken.core.__all__)
    assert not overlap, f"直下と core で名前が重複している: {sorted(overlap)}"


def test_facade_attributes_resolve_to_real_objects() -> None:
    """公開名前が None や空文字ではなく、対応するオブジェクトに解決される。"""
    # モジュール
    assert comken.config is not None
    # クラス
    assert comken.Config is not None
    # ログ設定モジュール
    assert comken.comken_logger is comken.core.logger
    assert comken.comken_logger.getLogger is __import__("logging").getLogger
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
