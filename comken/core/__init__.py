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

from comken.core.clock import now as now
from comken.core.clock import today as today
from comken.core.data import DiffResult as DiffResult
from comken.core.data import RowChange as RowChange
from comken.core.data import diff_row as diff_row
from comken.core.data import diff_rows as diff_rows
from comken.core.files.archive import unzip as unzip
from comken.core.files.archive import zip_files as zip_files
from comken.core.files.archive import zip_folder as zip_folder
from comken.core.files.finder import FileFinder as FileFinder
from comken.core.files.finder import date_in_name as date_in_name
from comken.core.files.naming import DateNameBuilder as DateNameBuilder
from comken.core.files.ops import copy_file as copy_file
from comken.core.files.ops import local_copy as local_copy
from comken.core.files.ops import move_file as move_file
from comken.core.files.ops import project_dir as project_dir
from comken.core.retry import retry as retry
from comken.core.state import State as State
from comken.core.text import normalize as normalize
from comken.core.text import remove_spaces as remove_spaces
from comken.core.text import strip_spaces as strip_spaces
from comken.core.timer import Timer as Timer
from comken.core.timer import measure as measure
from comken.core.wait import wait as wait

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
    "project_dir",
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
