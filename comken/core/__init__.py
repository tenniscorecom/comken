"""comken/core/__init__.py — 直下にだけ依存する部品を置く場所。

`comken.core` には、外側（ファイル・Excel・ブラウザ・Salesforce 等）を触らない
純粋な部品だけを置く。logger / state / config / clock / text / data / files などが
ここに入る。外に触る道具は toolbox に置く。

利用者は、``comken`` 直下にない部品を ``from comken.core import ...`` で取る。
``comken`` 直下と ``comken.core`` に同じ名前は公開しない。

ただし toolbox / services パッケージの内部実装（filesystem / レジストリ等を
触る土台）は toolbox 側の正常な依存先に置く必要があるため、
``from comken.core import ...`` を toolbox 内部から行うことも許容する。
"""

from .clock import now as now
from .clock import today as today
from .data import DiffResult as DiffResult
from .data import RowChange as RowChange
from .data import diff_row as diff_row
from .data import diff_rows as diff_rows
from .files.archive import unzip as unzip
from .files.archive import zip_files as zip_files
from .files.archive import zip_folder as zip_folder
from .files.finder import FileFinder as FileFinder
from .files.finder import date_in_name as date_in_name
from .files.naming import DateNameBuilder as DateNameBuilder
from .files.ops import copy_file as copy_file
from .files.ops import local_copy as local_copy
from .files.ops import move_file as move_file
from .retry import retry as retry
from .state import State as State
from .text import normalize as normalize
from .text import remove_spaces as remove_spaces
from .text import strip_spaces as strip_spaces
from .timer import Timer as Timer
from .timer import measure as measure
from .wait import wait as wait

__all__ = [
    "DateNameBuilder",
    "DiffResult",
    "FileFinder",
    "RowChange",
    "State",
    "Timer",
    "copy_file",
    "date_in_name",
    "diff_row",
    "diff_rows",
    "local_copy",
    "measure",
    "move_file",
    "normalize",
    "now",
    "remove_spaces",
    "retry",
    "strip_spaces",
    "today",
    "unzip",
    "wait",
    "zip_files",
    "zip_folder",
]
