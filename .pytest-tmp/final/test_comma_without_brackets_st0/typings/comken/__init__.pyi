"""config.ini から自動生成されたエディタ補完用スタブ。手で編集しない。

Config() を呼ぶたびに自動更新される（手動生成 CLI `python -m comken config` は v1.0.0 で削除済み）。
"""

from pathlib import Path


from comken.core.config import (
    Config as Config,
)
from comken.core.logger import (
    setup_logging as setup_logging,
)
from comken.runtime import (
    debug as debug,
    dry_run as dry_run,
)
class MappingDict(dict[str, str | None]):
    def __missing__(self, key: str) -> str | None: ...


class _S:
    QUERY: str

class _ConfigFacade:
    S: _S

config: _ConfigFacade

__version__: str
