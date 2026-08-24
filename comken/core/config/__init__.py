"""comken/core/config/__init__.py — INI ファイル読み込みユーティリティ

config.ini を読み込み、config.SECTION.KEY の形式でアクセスできる Config クラスを提供する。

いちばん簡単な使い方（プロジェクトに src/config.py を作らなくてよい）:

    from comken import config
    path = config.FILES.INPUT_FOLDER / config.FILES.CSV_EAST

    → 初回アクセス時にプロジェクトディレクトリの config.ini を1度だけ読む（遅延読み込み）。
      別の場所にある config.ini を読むときは ``Config(path)`` を直接使う。

明示的にインスタンスを持ちたい場合:

    from comken.core.config import Config
    config = Config()                 # または Config("path/to/config.ini")

列名の対応表セクション（``[*_MAPPING]``）は ``config.SECTION_MAPPING`` で dict 互換
オブジェクトとして読める。型は ``dict[str, str]`` で、中の値は必ず ``str``。
**列があるかないかを判別したいときは ``in`` を使う**（
``"列名" in config.SECTION_MAPPING``）。
``.get("未知の列")`` は ``str | None`` を返すので ``is None`` で判定できる。
``[*_MAPPING"]["未知の列"]`` を直接読むと、**型上は ``str`` だが実行時は ``None`` が返る**
（``_LenientDict.__missing__`` の後方互換の動作）。このため ``is None`` 判定は型上
表現されていない。型と実行時のズレの理由は ``_LenientDict`` の docstring に書いた。
公開型は ``MappingDict``（``from comken.core.config import MappingDict``）で、
``_LenientDict`` は内部実装。

``*_MAPPING`` セクションの **値（対応先）が空欄のときは読み込みエラー**にする
（``ConfigMappingEmptyValueError``）。空欄のまま進めると「対応列の最初の値が
空文字列」と解釈されて、業務データが空欄で書き戻される事故になるため、
書いた人と実行の挙動が乖離しないよう読み込み時点で止める。 ``=`` を
付け忘れた行（``cfg.get()`` が ``None`` を返す行）もまとめて空欄扱いにする。
検知は ``*_MAPPING`` に限るため、通常セクションの ``READ_PASSWORD =`` のように
「設定しない」を示す空欄はそのまま読める。

エディタの補完候補:
    属性は実行時に動的に作られるため、そのままではエディタが補完できないが、
    Config() を呼ぶたびに補完用のスタブ（src/config.pyi）が自動更新されるため、
    一度スクリプトを実行すれば config.SECTION.KEY が型付きで補完されるようになる。

※ ブラウザの設定は config.ini ではなく BrowserOptions のインスタンス
   （src/browser_options.py）で行う。config はブラウザ設定を持たない。
"""

import configparser
import logging
import math
import shutil
import types
from pathlib import Path
from typing import NoReturn

from comken.core.files.ops import project_dir
from comken.exceptions import (
    ConfigCreatedFromExampleError,
    ConfigFileNotFoundError,
    ConfigKeyNotFoundError,
    ConfigLowerCaseNameError,
    ConfigMappingEmptyValueError,
    ConfigSectionNotFoundError,
)

logger = logging.getLogger(__name__)

_is_version_logged = False
MAPPING_SECTION_SUFFIX = "MAPPING"


def _is_mapping_section(section: str) -> bool:
    """列名の対応表として扱うセクションかを返す。"""
    return section.endswith(MAPPING_SECTION_SUFFIX)


class _LenientDict(dict[str, str]):
    """``MappingDict`` の内部実装（``MappingDict = _LenientDict``）。

    公開型は ``MappingDict``（``from comken.core.config import MappingDict``）。
    ``_LenientDict`` は実装詳細で、 ``_`` プレフィックスは「comken 内部用」を示す。
    ``Config.__init__`` が ``setattr(self, SECTION, ld)`` で公開 attribute に
    昇格させ、利用者は ``config.SECTION_MAPPING`` でこの dict 互換オブジェクトに触れる。

    型は ``dict[str, str]`` に揃えた。中身（config.ini で書いた対応表）は
    ``ConfigMappingEmptyValueError`` で空欄が拒否されているので、**値は必ず ``str``**。
    dict 互換なので ``for k, v in CONFIG.SECTION_MAPPING.items()`` のような
    既存呼び出しはそのまま動く（後方互換）。

    **型と実行時の齟齬 — 必ず読むこと:**

    ``__missing__`` は **後方互換のため**残している（``ef215ef`` 以前から
    存在していた動作を変えるな、という依頼）。dict の ``__missing__`` を
    オーバーライドしているので、未知のキー ``m["未知の列"]`` で ``KeyError`` ではなく
    ``None`` が返る。``__getitem__`` のシグネチャは ``dict[str, str]`` の ``str`` を
    返す形のままなので、 **型上は ``m["未知の列"]`` が ``str`` を返す**ことになって
    いる（pyright は ``__missing__`` の戻り値を ``__getitem__`` の戻り値型に
    反映しない）。

    - つまり ``m["未知の列"] is None`` は **型上はエラー**になる
      （``str`` を ``None`` と比較している）。
    - 実行時は実際に ``None`` が返るので、テストで書くと **実行は通る**。
    - 列の有無を判別したいときは ``in`` を使う（**型と実行時が正しく揃う**）:
      ``"列名" in config.SECTION_MAPPING``
    - ``is None`` 判定をしたいときは ``.get()`` を使う（戻り値は ``str | None``）:
      ``config.SECTION_MAPPING.get("列名") is None``

    スタブ（.pyi）でもこの ``_LenientDict`` を ``MappingDict`` として露出する。
    ``MappingDict[str, str]`` の ``__missing__`` も ``None`` を返す（後方互換）。
    """

    def __missing__(self, _key: str) -> str | None:
        # ``dict[str, str]`` の ``__getitem__`` の戻り値型は ``str`` のままなので、
        # この ``str | None`` は ``__missing__`` のシグネチャを広げただけで、
        # ``m["未知の列"]`` の戻り値型には反映されない。実行時は ``None`` を返す。
        # 詳細はクラスの docstring の「型と実行時の齟齬」節。
        return None


class _SectionNamespace(types.SimpleNamespace):
    """config.ini のセクションを表す名前空間。

    存在しないキーへのアクセスを ``ConfigKeyNotFoundError`` に変換し、
    「もしかして」の候補（そのセクションにあるキー一覧から編集距離で判定）
    とセクション名を添える。

    ``ConfigKeyNotFoundError`` は ``AttributeError`` も多重継承しているので、
    ``hasattr(namespace, key)`` は False を返す。
    この挙動を壊すと「あるはずのキーが無い」と ``hasattr`` 利用者が誤判定するため、
    キーが無いときは必ず例外を返す。
    """

    def __init__(
        self, section: str, keys: list[str], path: Path | None = None, **kwargs: object
    ) -> None:
        super().__init__(**kwargs)
        # SimpleNamespace の __dict__ へ直接入れる（setattr を経由しないことで、
        # うっかり独自の __setattr__ を定義してもここだけは通るようにしておく）。
        object.__setattr__(self, "_section", section)
        object.__setattr__(self, "_keys", keys)
        object.__setattr__(self, "_path", path)

    def __getattr__(self, name: str) -> NoReturn:
        # dunder / private は通常の AttributeError にする。pickle・copy・hasattr・
        # len() 等は dunder を期待しているので、こちらを KeyError 系に潰すと
        # 別のところで壊れる
        if name.startswith("_"):
            raise AttributeError(name)
        raise ConfigKeyNotFoundError(self._section, name, self._keys, self._path)


def _create_from_example(path: Path) -> Path | None:
    """config.ini が無いとき、隣の config.ini.example からコピーして作る。

    作らずにエラーだけ出すと、毎回「example をコピーする」手作業が要る。
    ただし作ってそのまま動かすと、ダミーの値のまま別のフォルダを読み書きしうるため、
    作るところまでで止めて確認を促す（呼び出し元で例外にする）。
    """
    example = path.with_name(f"{path.name}.example")
    if not example.is_file():
        return None
    shutil.copy2(example, path)
    return path.resolve()


def _build_section_map(cfg: configparser.ConfigParser) -> dict[str, str]:
    """config.ini のセクション名から前後の空白（全角含む）を落として、整理した対応表を作る。

    configparser は `[FILES ]` と `[FILES]` を別セクションとして扱うため、
    手書きで空白が混じるとセクションが分かれてしまう。空白を落とした名前で
    アクセスさせることで、書かれた綴りに左右されず `config.FILES` で読めるようにする。

    Returns:
        落とした後のセクション名 → 元の cfg.sections() 内のセクション名。
        **空白を落とした結果が同じになるセクションが複数ある場合、最初に見つかった
        方だけを採用する**。衝突が起きると読み手が書いたセクションのうち
        どちらが生きているか分からなくなるため、logger.warning で WARN を出す。

    空文字列になったセクション名（`[]` や `[   ]`）はスキップする。
    """
    section_map: dict[str, str] = {}
    for original in cfg.sections():
        stripped = original.strip()
        if not stripped:  # 全て空白しかないセクション名は丸ごと無視する
            continue
        if stripped in section_map:
            logger.warning(
                "config.ini のセクション [%s] と [%s] は前後の空白を落とすと"
                "同じ名前になるため、先に書かれた [%s] を採用し"
                " [%s] は読み込みません。",
                section_map[stripped],
                original,
                section_map[stripped],
                original,
            )
            continue
        section_map[stripped] = original
    return section_map


def _validate_upper_case(
    cfg: configparser.ConfigParser, path: Path, section_map: dict[str, str]
) -> None:
    """セクション名・キー名が大文字で書かれているか確かめる。

    小文字で書かれていても読み込み自体は成功し、大文字に直して保持されるため、
    小文字のままアクセスしたときに初めて「そんなセクションはない」と言われる。
    書いた場所から遠いエラーになるので、読み込んだ時点で止める。

    空白を落とした後の名前で判定する。`[files]` の小文字検知を `ConfigSectionNotFoundError`
    の空白落としで誤って見逃すことがないように。
    """
    wrong = [
        f"[{s_strip}] → [{s_strip.upper()}]"
        for s_strip in section_map
        if s_strip != s_strip.upper()
    ]
    wrong += [
        f"[{section_map[s_strip]}] の {k} → {k.upper()}"
        for s_strip in section_map
        if not _is_mapping_section(s_strip)
        for k in cfg.options(section_map[s_strip])
        if k != k.upper()
    ]
    if wrong:
        raise ConfigLowerCaseNameError(path.resolve(), wrong)


class Config:
    """config.ini を読み込み、config.SECTION.KEY の形式でアクセスできるクラス。

    値の型変換（_parse_value の変換順と同じ）:
        - true / false → bool
        - [a, b, c] → list[str]
        - 絶対パス（C:\\ / \\\\ / /）→ Path
        - 整数 → int
        - 小数 → float
        - それ以外 → str

    数値を文字列として使いたい場合はコード側で str() に変換する。

    config.ini の例（セクション名・キー名は大文字で書く）:
        [BROWSER]
        WAIT_SECONDS = 10
        HEADLESS = false

        [FILES]
        INPUT_FOLDER = C:\\作業\\input

        [REPORT]
        TARGET_SHEETS = [支店A, 支店B, 集計]

    """

    def __init__(self, path: str | Path | None = None) -> None:
        """
        Args:
            path: config.ini のパス。省略するとプロジェクトのフォルダ
                （main.py の場所）の config.ini を読む。
        """
        # 社内 RPA 基盤は C:\ など別の場所をカレントにして
        # `python <絶対パス>\main.py` と呼ぶ。カレント基準だと C:\config.ini を探してしまう
        if path is None:
            path = project_dir() / "config.ini"
        cfg = configparser.ConfigParser(interpolation=None)
        # configparser は既定でキー名を小文字に潰すため、書かれたとおりの綴りを保つ。
        # これがないと「大文字で書かれていたか」を判定できない（_validate_upper_case）。
        # `str` 型を callable として代入しているが、configparser の型スタブが
        # method slot を許容せず pyright が「No overloaded function matches」と
        # 誤検知するため残す。実行時は `str("FOO") == "FOO"` で identity として動く。
        cfg.optionxform = str  # type: ignore[method-assign]
        # utf-8-sig: メモ帳等で保存すると BOM 付き UTF-8 になるため（BOM なしも読める）
        loaded = cfg.read(path, encoding="utf-8-sig")
        if not loaded:
            # configparser はファイルがなくても黙って空になるため、明示的にエラーにする
            # （後で config.FILES 等が分かりにくい AttributeError になるのを防ぐ）
            created = _create_from_example(Path(path))
            if created is not None:
                raise ConfigCreatedFromExampleError(created)
            raise ConfigFileNotFoundError(Path(path).resolve())

        # configparser はセクション名の前後の空白（全角スペース含む）を落とさないため、
        # 手書きで `[FILES ]` のように書くと別セクション扱いになり、書いた人と
        # 読む側で名前が一致しなくなる。空白を落とした名前でアクセスさせる。
        # 重複したら黙って捨てずに WARNING を出している（同じ値が読まれているか
        # 利用者が疑わざるを得なくなるため）。
        self._path = Path(path).resolve()
        section_map = _build_section_map(cfg)
        # ↑の関数で空文字だけのセクション名は除外しているため、ここで len==0 でも
        # 例外にはせず空の Config として返す（下の _mappings 更新が起きないだけ）。
        if section_map:
            # 大文字小文字チェックは「落とした後の名前」で行う（小文字の検出は
            # 空白除去と独立なので、検出の意味は変わらない）。
            _validate_upper_case(cfg, Path(path), section_map)
            self._mappings = {}
            for stripped_section, original_section in section_map.items():
                if _is_mapping_section(stripped_section):
                    # ``*_MAPPING`` は列名が動的なので ``_SectionNamespace`` ではなく
                    # ``_LenientDict`` で attribute 化する。``Config.SECTION_MAPPING["未知の列名"]``
                    # を ``None`` で判別できるようにするため ``__missing__`` で ``None`` を返す。
                    # dict のサブクラスなので ``isinstance(x, dict)`` が True（後方互換）。
                    #
                    # 値は ``_LenientDict`` 生成前に全件走査して空欄（前後の空白だけの
                    # 値も含む）と ``=`` 無しの行（``cfg.get()`` が ``None`` を返す）を
                    # 集める。空欄のキーは **まとめて** 例外に乗せる（1 件ずつ直させる
                    # と「次はどれだっけ」のループに落ちるため）。 ``READ_PASSWORD =``
                    # のように通常セクションで空欄を「設定しない」として使う書き方は
                    # ここで **対象外**（``_is_mapping_section`` の中だけで検知する）。
                    options = cfg.options(original_section)
                    pairs: list[tuple[str, str]] = []
                    empty_keys: list[str] = []
                    for key in options:
                        value = cfg.get(original_section, key)
                        if value is None or value.strip() == "":
                            empty_keys.append(key)
                        else:
                            pairs.append((key.strip(), value.strip()))
                    if empty_keys:
                        raise ConfigMappingEmptyValueError(self._path, stripped_section, empty_keys)
                    ld = _LenientDict(pairs)
                    self._mappings[stripped_section] = ld
                    setattr(self, stripped_section.upper(), ld)
                    continue
                # configparser はキー名の前後空白を既に落とすので、二重 strip は不要
                options = cfg.options(original_section)
                ns = _SectionNamespace(
                    section=stripped_section.upper(),
                    keys=[key.upper() for key in options],
                    path=self._path,
                    **{key.upper(): _parse_value(cfg, original_section, key) for key in options},
                )
                setattr(self, stripped_section.upper(), ns)
        else:
            self._mappings = {}

        # エディタ補完用スタブ（src/config.pyi）を自動更新する。
        # config.ini を変更してもスタブが古くならない（失敗しても本処理は止めない）。
        # スタブ生成は別モジュールへ分離しており、遅延 import で循環を避ける
        from comken.core.config.stubs import update_stub

        update_stub(cfg, path, section_map)
        _log_version_once()

    def __getattr__(self, name: str) -> NoReturn:
        # 通常の属性（設定済みセクション）は __dict__ にあり、ここには来ない。
        # 未定義セクションのアクセスだけがここに来るので、分かりやすいエラーにする。
        if name.startswith("_"):  # copy/pickle 等の内部属性探索は通常の AttributeError に
            raise AttributeError(name)
        # セクション名は大文字と決まっている（ConfigLowerCaseNameError で読み込み時に止める）。
        # 小文字始まりが __getattr__ に来るのは、`Config(path).save()` のような
        # 存在しないメソッドを呼んでいるケースがほとんど。ConfigSectionNotFoundError の
        # 「セクションがありません」は完全な的外れなので、 AttributeError に変えて
        # 「セクションの話ではない」と気付けるようにする。
        if name and name[0].islower():
            raise AttributeError(
                f"Config に {name!r} という属性（セクション）はありません。"
                "config.ini のセクション名は大文字なので、"
                "小文字で始まる名前はセクションではありません。"
            )
        sections = [k for k in vars(self) if k.isupper()]
        raise ConfigSectionNotFoundError(name, sections, self._path)


# ── `from comken import config` 用の遅延シングルトン ──────────────────────────
# プロジェクトごとに src/config.py（config = Config()）を書く手間を省く。
# config.SECTION.KEY への初回アクセス時にカレントディレクトリの config.ini を
# 1度だけ読む（import 時ではないので、config.ini を持たないプロジェクトやテストで
# comken を import しても失敗しない）。
#
# `__getattr__` で初回呼び出し時に `Config()` を生成し委譲する。専用 global 変数
# は持たず、__getattr__ のたびに `Config()` を呼ぶ（configparser の読み込みは
# 軽量なので、シングルトン管理のための状態を持たない方を採る）。

# 公開型 ``MappingDict`` = 実装 ``_LenientDict``。
# ``*_MAPPING`` セクションの戻り値は dict 互換（``isinstance(x, dict)`` が True）
# で、型は ``dict[str, str]``。 ``__missing__`` が ``None`` を返す後方互換の動作は
# ``_LenientDict`` の docstring に書いた。利用者向けの名前は ``MappingDict`` で、
# ``_LenientDict`` は内部実装として ``_`` プレフィックスで残す。
MappingDict = _LenientDict


def __getattr__(name: str) -> types.SimpleNamespace:
    # PEP 562: `comken.core.config.FILES` のようにモジュール属性として見つからない名前で呼ばれる。
    # セクションは大文字なので、大文字名のときだけ Config() を生成して委譲する
    # （Config / MappingDict などの実体は通常の属性解決で見つかるためここには来ない）。
    if name.isupper():
        return getattr(Config(), name)
    raise AttributeError(f"module 'comken.core.config' has no attribute {name!r}")


# ── 内部ヘルパー：ini 値の型変換 ───────────────────────────────────────────────


def _split_list_items(text: str) -> list[str]:
    """カンマまたは改行区切りの文字列をリストに変換する。空文字は除外する。"""
    items = text.replace("\n", ",").split(",")
    return [s.strip() for s in items if s.strip()]


def _log_version_once() -> None:
    """設定の初回読み込み後に障害調査用のバージョンを1回だけ記録する。"""
    global _is_version_logged
    if not _is_version_logged:
        # 親パッケージ側の __version__ は comken/__init__.py で定義されるため、
        # モジュール先頭で `from ... import __version__` すると import 順序に
        # 依存した循環が起きる。関数の内側で取る形にすることで循環を断つ。
        from comken import __version__

        logger.info("comken v%s", __version__)
        _is_version_logged = True


def _parse_value(
    cfg: configparser.ConfigParser, section: str, key: str
) -> bool | int | float | Path | list[str] | str:
    """ini の値を適切な Python 型に変換して返す。

    変換の優先順位:
        1. true / false（大文字小文字問わず）→ bool
        2. [a, b, c] → list[str]（改行区切りも可）
        3. 絶対パス（C:\\ / \\\\ / / で始まる）→ Path
        4. 整数に変換できる → int（ただし先頭ゼロの数字は文字列のまま）
        5. 小数に変換できる → float（ただし nan / inf は文字列のまま）
        6. それ以外 → str

    文字列として使いたい数値（例: 管理番号 "123"）はコード側で str() に変換する。
    先頭ゼロ（電話番号 "0521234567"・社員番号 "007" 等）は int にすると桁落ちするため
    文字列で返す。nan / inf は float() が受理してしまうので数値化しない。
    """
    value = cfg.get(section, key).strip()
    lower = value.lower()

    if lower == "true":
        return True
    if lower == "false":
        return False

    if value.startswith("[") and value.endswith("]"):
        return _split_list_items(value[1:-1])

    if len(value) >= 2 and (value[1:3] == ":\\" or value[:2] == "\\\\" or value[0] == "/"):
        return Path(value)

    # 先頭ゼロの数字は電話番号・社員番号等とみなし、桁落ちを避けて文字列のまま返す
    unsigned = value[1:] if value[:1] in ("+", "-") else value
    if len(unsigned) > 1 and unsigned[0] == "0" and unsigned.isdigit():
        return value

    try:
        return int(value)
    except ValueError:
        pass
    try:
        parsed = float(value)
        if math.isfinite(parsed):  # nan / inf は設定値として無効なので文字列扱い
            return parsed
    except ValueError:
        pass

    return value
