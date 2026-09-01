"""comken/internal/base.py — 社内ライブラリ呼び出しを束ねる基底クラス。"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from types import TracebackType
from typing import Any, TypeAlias

from comken.internal.exceptions import InternalLibraryNotFoundError

logger = logging.getLogger(__name__)

# 社内 RPA 等の import 先は動的境界で型情報が無い。  ``object`` だと属性アクセスが
# Any に広がらないため、局所の Any 別名として明示しておく（CONVENTIONS.md「型ヒント」）。
ModuleType: TypeAlias = Any


class InternalLibraryBase:
    """社内ライブラリのモジュールを束ねるラッパークラス。

    利用例::

        with InternalLibraryBase("example_libs.v0000.rpa") as rpa:
            rpa.backoffice(main, "project")
    """

    def __init__(self, library_name: str) -> None:
        self._library_name = library_name
        self._module: ModuleType | None = None

    @property
    def library_name(self) -> str:
        """社内ライブラリの正式名称(例: ``example_libs.v0000.rpa``)を返す。"""
        return self._library_name

    def find_spec(self) -> bool:
        """社内ライブラリが import 可能なら True。

        親パッケージ (``example_libs.v0000`` など) が見つからない場合も False を返す。
        """
        return _is_available(self._library_name)

    def load(self) -> ModuleType:
        """社内ライブラリを import して返す。

        「対象モジュール自身、またはその親パッケージが見つからない」ときだけ
        ``InternalLibraryNotFoundError`` に変換する。 モジュール内に別の依存が
        あって ``ImportError`` / ``ModuleNotFoundError`` が出た場合はそのまま伝搬する
        （依存不足を対象ライブラリの不在と誤変換しないため）。
        """
        try:
            return importlib.import_module(self._library_name)
        except ModuleNotFoundError as exc:
            # 例外が指す名前を直接見ることで、存在確認のために親パッケージを
            # もう一度 import せず、対象内部の依存不足も誤変換しない。
            if _is_target_or_parent_missing(self._library_name, exc):
                raise InternalLibraryNotFoundError(self._library_name) from exc
            raise

    def __enter__(self) -> ModuleType:
        if not self.find_spec():
            logger.warning("社内ライブラリ %s は見つかりません。", self._library_name)
        self._module = self.load()
        return self._module

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._module = None


def _is_target_or_parent_missing(library_name: str, exc: BaseException) -> bool:
    """``library_name`` 自体またはその親パッケージが見つからないとき True。

    ``ModuleNotFoundError.name`` を調べ、次のいずれかに該当する場合だけ True:
    - 要求した ``library_name`` そのものが見つからない
    - ``library_name`` の親部分（``library_name.startswith(missing_name + '.')``）が
      見つからない

    その他の依存不足（モジュール内に別の依存が無いケースなど）は False を返し、
    元の例外を呼び出し側へ伝える。
    """
    missing_name = getattr(exc, "name", None)
    if not missing_name:
        return False
    if missing_name == library_name:
        return True
    return library_name.startswith(missing_name + ".")


def _is_available(library_name: str) -> bool:
    """``importlib.util.find_spec`` が None でなければ import 可能とみなす。

    「モジュールが見つからない」ときは ``find_spec`` が None を返す。
    親パッケージが見つからない等の理由で ``find_spec`` 自身が
    ``ModuleNotFoundError`` を送出する場合は、対象モジュール自身か親パッケージが
    見つからないときに限り「利用不可（False）」とみなす。それ以外の依存不足の
    例外はそのまま呼び出し側へ伝搬する。
    """
    try:
        return importlib.util.find_spec(library_name) is not None
    except ModuleNotFoundError as exc:
        if _is_target_or_parent_missing(library_name, exc):
            return False
        # モジュール自体（または親）は見つかるが、内部依存が見つからない等の
        # 理由で find_spec 自身が落ちた場合は、利用可否の判定材料として使えない。
        # 握り潰すと依存不足を「対象不在」に誤変換するため、そのまま伝える。
        raise
    except ImportError:
        # ``ImportError`` のうち ``ModuleNotFoundError`` 以外のものは、内部依存の
        # 不在など別要因のもの。誤って False を返さないために伝搬する。
        raise
