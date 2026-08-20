"""comken/core/state.py — 実行と実行のあいだで状態を持ち越すユーティリティ。

config.ini は人が書く設定なのでプログラムから変更しない。一方、state.ini は
プログラムが前回の処理結果を保存するために使う。初回に state.ini が無いことは
正常なので、config.ini と異なり空の状態として処理を続ける。
"""

import configparser
import json
import logging
from pathlib import Path

from comken.core.files.atomic import atomic_write
from comken.core.files.ops import cleanup_stale_tmp, project_dir
from comken.exceptions import StateFileCorruptedError, StateLowerCaseNameError, StateValueTypeError
from comken.runtime import dry_run_log, is_dry_run

logger = logging.getLogger(__name__)

STATE_SECTION = "STATE"

StateValue = bool | int | float | str | list[str]

__all__ = ["State"]


class State:
    """プログラムが次回実行へ持ち越す値を state.ini に保存する。

    ``set()`` は呼び出すたびに UTF-8 で原子的に保存する。dry-run 中に状態を
    書くと、試運転したファイルが本番で処理済みと判断されうるため、ファイルは
    変更せず、書く予定だった内容だけをログへ出す。

    保存できる値は、真偽値・整数・小数・文字列・文字列のリスト。

    Args:
        path: state.ini のパス。省略するとプロジェクトのフォルダ（main.py の場所）の
              state.ini。
    """

    def __init__(self, path: str | Path | None = None) -> None:
        # 社内 RPA 基盤は C:\ など別の場所をカレントにして
        # `python <絶対パス>\main.py` と呼ぶ。カレント基準だと C:\state.ini になってしまう
        self._path = Path(path) if path is not None else project_dir() / "state.ini"
        self._values = self._read()

    def get(self, key: str, default: StateValue | None = None) -> StateValue | None:
        """保存済みの値を返す。無い場合は default を返す。"""
        self._validate_key(key)
        return self._values.get(key, default)

    def set(self, key: str, value: StateValue) -> None:
        """値を保存する。dry-run 中はファイルもメモリ上の状態も変更しない。"""
        self._validate_key(key)
        if not _is_state_value(value):
            raise StateValueTypeError(value)
        if is_dry_run():
            # dry-run が本番の「処理済み」判定を変えないことを最優先する。
            dry_run_log("状態を保存: %s = %r (%s)", key, value, self._path)
            return
        updated_values = {**self._values, key: value}
        self._write(updated_values)
        self._values = updated_values

    def _read(self) -> dict[str, StateValue]:
        logger.debug("State読み込み開始: %s", self._path)
        if not self._path.exists():
            logger.debug("State読み込み完了: ファイルなし")
            return {}
        parser = _new_parser()
        try:
            with self._path.open(encoding="utf-8-sig") as state_file:
                parser.read_file(state_file)
            if parser.sections() != [STATE_SECTION]:
                raise StateFileCorruptedError(self._path.resolve())
            values: dict[str, StateValue] = {}
            for key, raw_value in parser.items(STATE_SECTION):
                self._validate_key(key)
                value = json.loads(raw_value)
                if not _is_state_value(value):
                    raise StateFileCorruptedError(self._path.resolve())
                values[key] = value
            logger.debug("State読み込み完了: 件数=%d", len(values))
            return values
        except (configparser.Error, UnicodeError, json.JSONDecodeError) as error:
            raise StateFileCorruptedError(self._path.resolve()) from error

    def _write(self, values: dict[str, StateValue]) -> None:
        logger.debug("State書き込み開始: %s 件数=%d", self._path, len(values))
        # 置き場所はここで用意する。atomic_write は勝手に作らない
        self._path.parent.mkdir(parents=True, exist_ok=True)
        cleanup_stale_tmp(self._path)
        parser = _new_parser()
        parser[STATE_SECTION] = {
            key: json.dumps(value, ensure_ascii=False) for key, value in values.items()
        }
        with (
            atomic_write(self._path) as tmp,
            tmp.open(mode="w", encoding="utf-8", newline="") as file,
        ):
            parser.write(file)
        logger.debug("State書き込み完了: %s 件数=%d", self._path, len(values))

    @staticmethod
    def _validate_key(key: str) -> None:
        if key != key.upper():
            raise StateLowerCaseNameError(key)


def _new_parser() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[method-assign]
    return parser


def _is_state_value(value: object) -> bool:
    if isinstance(value, (bool, int, float, str)):
        return True
    return isinstance(value, list) and all(isinstance(item, str) for item in value)
