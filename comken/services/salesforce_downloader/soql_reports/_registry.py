"""comken/services/salesforce_downloader/soql_reports/_registry.py — SOQLレポート登録の置き場所。

``__init__.py`` から ``runner`` を import するので、``runner`` から
``__init__.py`` を逆に import すると循環する。``registered_reports()`` は
``runner.download_soql_reports()`` が「``reports=None`` のときの既定値」
として参照するため、**循環を切れる別のモジュール**に置く。
"""

from __future__ import annotations

import importlib
import pkgutil

from comken.exceptions import DownloaderError
from comken.services.salesforce_downloader.soql_reports import reports
from comken.services.salesforce_downloader.soql_reports.base import SoqlReport


def registered_reports() -> tuple[type[SoqlReport], ...]:
    """``reports/`` パッケージに置かれた ``SoqlReport`` サブクラスを集めて返す。

    走査は ``pkgutil.iter_modules(reports.__path__)`` で ``reports/`` 直下の
    ``.py`` を1つずつ ``importlib.import_module`` し、そのモジュール自身で
    定義された ``SoqlReport`` のサブクラス（``cls.__module__ == module.__name__``
    を満たすもの）だけを拾う。**ファイル名が ``_`` で始まるモジュールは
    走査対象外**（``_template.py`` のような雛形を登録せずに済む）。

    ``KEY`` の昇順で返す。**キャッシュはしない** — ``importlib.import_module``
    は既に import 済みなら再 load しない（``sys.modules`` 経由で軽い）ので、
    呼ぶたびに ``reports/`` を全走査し直してもコストは無視できる。
    ファイル追加のたびに再起動は不要。

    Raises:
        DownloaderError: ``KEY`` が空のレポートが含まれているか、複数の
            レポートが同じ ``KEY`` を持っている。メッセージには
            ``reports/<ファイル>.py`` のパスとクラス名を含め、
            対処（``KEY`` を埋める／重複を直す）を併記する。
    """
    found: list[tuple[str, type[SoqlReport], str]] = []
    for module_info in pkgutil.iter_modules(reports.__path__):
        module_name = module_info.name
        if module_name.startswith("_"):
            # ``_template.py`` のような雛形は登録しない
            continue
        module = importlib.import_module(f"{reports.__name__}.{module_name}")
        for cls in vars(module).values():
            if not isinstance(cls, type) or not issubclass(cls, SoqlReport):
                continue
            if cls is SoqlReport:
                continue
            # 他モジュールから ``from ... import`` しただけのクラスは拾わない
            if cls.__module__ != module.__name__:
                continue
            found.append((cls.KEY, cls, module.__name__))

    _validate_keys(found)
    found.sort(key=lambda item: item[0])
    return tuple(item[1] for item in found)


def _validate_keys(found: list[tuple[str, type[SoqlReport], str]]) -> None:
    """``KEY`` の空と重複を検査し、問題があれば ``DownloaderError`` を送出する。

    Args:
        found: ``(KEY, クラス, モジュール名)`` のリスト（ソート前）。
    """
    by_key: dict[str, list[tuple[type[SoqlReport], str]]] = {}
    for key, cls, module_name in found:
        by_key.setdefault(key, []).append((cls, module_name))

    empties = [(cls, module_name) for key, cls, module_name in found if not key]
    if empties:
        cls, module_name = empties[0]
        path = _report_path(module_name)
        raise DownloaderError(
            f"SOQLレポートの KEY が空です: {cls.__name__}（{path}）\n"
            f"対処: {path} のクラス {cls.__name__} の KEY に、社内で決める管理番号"
            f'（例: "9001"）を埋めてください。空のままでは登録できません。'
        )

    duplicates = {key: entries for key, entries in by_key.items() if len(entries) > 1}
    if duplicates:
        # メッセージに「全件のファイル名」を入れる（最初にぶつかった1件だけだと直せないため）
        lines: list[str] = []
        for key, entries in duplicates.items():
            paths = ", ".join(
                f"{cls.__name__}（{_report_path(module_name)}）" for cls, module_name in entries
            )
            lines.append(f"  KEY={key!r}: {paths}")
        joined = "\n".join(lines)
        raise DownloaderError(
            f"SOQLレポートの KEY が重複しています:\n{joined}\n"
            f"対処: 同じ KEY を別の管理番号に直すか、片方のレポートを reports/ から"
            f"取り除いてください。1つの管理番号には1つの SoqlReport だけ紐付けてください。"
        )


def _report_path(module_name: str) -> str:
    """``reports.<name>`` 形式のモジュール名から ``reports/<name>.py`` 相当のパス表記を返す。"""
    short = module_name.removeprefix(f"{reports.__name__}.")
    return f"reports/{short}.py"
