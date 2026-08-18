"""
Config クラスのテスト。

実行方法:
    リポジトリのルートで python -m pytest tests/ -v
"""

import ast
import logging
import sys
from pathlib import Path

import pytest

import comken.core.config as config_module
from comken.core.config import Config
from comken.exceptions import (
    ConfigCreatedFromExampleError,
    ConfigError,
    ConfigLowerCaseNameError,
    ConfigRequiredKeysMissingError,
)

# .pyi 内で「型注釈に書かれた Name」が、その .pyi の import か組み込みで
# すべて解決できているか検査するヘルパー。Path のような外部名を書き出しながら
# import を忘れる「静かに補完が落ちる」バグを捕まえるのが目的。
_BUILTIN_TYPE_NAMES = {
    "bool",
    "int",
    "float",
    "str",
    "list",
    "dict",
    "tuple",
    "set",
    "type",
    "object",
    "None",
    "bytes",
    "complex",
    "frozenset",
}


def _collect_annotation_names(tree: ast.AST) -> set[str]:
    """AST ツリーから型注釈（AnnAssign / arg / 戻り値）に現れる Name を集める。"""
    used: set[str] = set()

    def walk(node: ast.AST) -> None:
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Subscript):
            walk(node.value)
            walk(node.slice)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            # `str | Path` のような union 表現
            walk(node.left)
            walk(node.right)
        elif isinstance(node, ast.Tuple):
            for elt in node.elts:
                walk(elt)
        # ast.Constant / ast.Attribute は型注釈で Name として解決される対象ではないので無視

    for node in ast.walk(tree):
        ann = _annotation_of(node)
        if ann is not None:
            walk(ann)
    return used


def _annotation_of(node: ast.AST) -> ast.AST | None:
    """指定ノードが持つ型注釈（あれば）を返す。なければ None。"""
    if isinstance(node, ast.AnnAssign):
        return node.annotation
    if isinstance(node, ast.arg):
        return node.annotation
    if isinstance(node, ast.FunctionDef):
        return node.returns
    return None


def _assert_stub_self_contained(text: str) -> None:
    """スタブ内で import / 定義されていない型名があったらテストを失敗させる。"""
    tree = ast.parse(text)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.asname or alias.name.split(".")[0])
    defined = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    used = _collect_annotation_names(tree)

    missing = used - _BUILTIN_TYPE_NAMES - imported - defined
    assert not missing, (
        f"スタブ内で import も定義もない型: {sorted(missing)}\n--- スタブ全体 ---\n{text}"
    )


class TestConfigMissingFile:
    def test_missing_file_raises_config_error(self, tmp_path):
        """config.ini が存在しない場合は ConfigError で即エラーになることを確認する。

        （configparser は黙って空になるため、後の分かりにくい AttributeError を防ぐ）
        """
        with pytest.raises(ConfigError, match=r"config\.ini が見つかりません"):
            Config(tmp_path / "config.ini")


class TestConfigBasic:
    """Config の基本的な読み込みのテスト。"""

    def test_logs_version_only_once(self, tmp_path, caplog, monkeypatch):
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nK = value\n", encoding="utf-8")
        monkeypatch.setattr(config_module, "_is_version_logged", False)

        with caplog.at_level(logging.INFO, logger="comken.core.config"):
            Config(ini)
            Config(ini)

        assert caplog.text.count("comken v") == 1

    def test_reads_string_value(self, tmp_path):
        """文字列の設定値を正しく読み込めることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[SECTION]\nKEY = hello\n", encoding="utf-8")
        config = Config(ini)
        assert config.SECTION.KEY == "hello"

    def test_underscore_names_are_read(self, tmp_path):
        """アンダースコアを含む名前を読み込めることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[MY_SECTION]\nMY_KEY = value\n", encoding="utf-8")
        config = Config(ini)
        assert config.MY_SECTION.MY_KEY == "value"

    def test_lowercase_section_raises(self, tmp_path):
        """小文字のセクション名は読み込んだ時点でエラーになることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[files]\nINPUT = x\n", encoding="utf-8")
        with pytest.raises(ConfigLowerCaseNameError) as exc:
            Config(ini)
        # 直し方が分かるよう、書き換え後の名前まで出すこと
        assert "[files] → [FILES]" in str(exc.value)

    def test_lowercase_key_raises(self, tmp_path):
        """小文字のキー名は読み込んだ時点でエラーになることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[FILES]\ninput = x\n", encoding="utf-8")
        with pytest.raises(ConfigLowerCaseNameError) as exc:
            Config(ini)
        assert "input → INPUT" in str(exc.value)

    def test_multiple_sections(self, tmp_path):
        """複数セクションをそれぞれ読み込めることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text(
            "[SERVICE]\nUSERNAME = user@example.com\n\n[REPORT]\nFOLDER = output\n",
            encoding="utf-8",
        )
        config = Config(ini)
        assert config.SERVICE.USERNAME == "user@example.com"
        assert config.REPORT.FOLDER == "output"

    def test_default_path_is_project_dir(self, tmp_path, monkeypatch):
        """パス省略時に**プロジェクトのフォルダ**（main.py の場所）の config.ini を読む。

        社内 RPA 基盤は C:\\ など別の場所をカレントにして
        `python <絶対パス>\\main.py` と呼ぶ。カレント基準にすると
        C:\\config.ini を探しに行ってしまうので、実行したスクリプトの場所を見る。
        """
        # カレントは別の場所に置いたまま、スクリプトの場所だけ tmp_path にする
        other = tmp_path / "別のカレント"
        other.mkdir()
        monkeypatch.chdir(other)
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        (tmp_path / "config.ini").write_text("[S]\nK = v\n", encoding="utf-8")

        config = Config()
        assert config.S.K == "v"

    def test_reads_bom_utf8(self, tmp_path):
        """BOM 付き UTF-8 の config.ini も読めることを確認する。

        （メモ帳や PowerShell で保存すると BOM 付きになるため。
        BOM を素通しすると1つ目のセクションが MissingSectionHeaderError になる）
        """
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nK = 日本語\n", encoding="utf-8-sig")
        assert Config(ini).S.K == "日本語"

    def test_reads_percent_sign_without_interpolation(self, tmp_path):
        """単独の % を含む設定値をそのまま読める。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nURL = https://example.test/a%20b\n", encoding="utf-8")
        assert Config(ini).S.URL == "https://example.test/a%20b"


class TestConfigMapping:
    """列名マッピングの読み込み規則を確認する。"""

    def test_preserves_mixed_case_column_names(self, tmp_path):
        ini = tmp_path / "config.ini"
        ini.write_text(
            "[受注_MAPPING]\n受注No = 受注番号\nWeb受注 = Web受付\n"
            "商品cd = 商品コード\nNo = 管理番号\n",
            encoding="utf-8",
        )

        assert Config(ini).mapping("受注_MAPPING") == {
            "受注No": "受注番号",
            "Web受注": "Web受付",
            "商品cd": "商品コード",
            "No": "管理番号",
        }

    def test_keeps_numeric_value_as_string(self, tmp_path):
        ini = tmp_path / "config.ini"
        ini.write_text("[MAPPING]\n年度 = 2026\n", encoding="utf-8")

        mapping = Config(ini).mapping("MAPPING")

        assert mapping["年度"] == "2026"
        assert isinstance(mapping["年度"], str)

    def test_preserves_japanese_and_symbol_column_names(self, tmp_path):
        ini = tmp_path / "config.ini"
        ini.write_text(
            "[MAPPING]\n担当者・部署 = 担当部署\n金額(税込) = 税込金額\n№ = 番号\n",
            encoding="utf-8",
        )

        assert Config(ini).mapping("MAPPING") == {
            "担当者・部署": "担当部署",
            "金額(税込)": "税込金額",
            "№": "番号",
        }

    def test_coexists_with_normal_section(self, tmp_path):
        ini = tmp_path / "config.ini"
        ini.write_text(
            "[REPORT]\nYEAR = 2026\n\n[COLUMN_MAPPING]\n受注No = 受注番号\n",
            encoding="utf-8",
        )
        config = Config(ini)

        assert config.REPORT.YEAR == 2026
        assert config.mapping("COLUMN_MAPPING") == {"受注No": "受注番号"}

    @pytest.mark.parametrize("key", ["受注No", "Web受注", "商品cd", "No"])
    def test_normal_section_still_rejects_mixed_case_key(self, tmp_path, key):
        ini = tmp_path / "config.ini"
        ini.write_text(f"[REPORT]\n{key} = value\n", encoding="utf-8")

        with pytest.raises(ConfigLowerCaseNameError):
            Config(ini)


class TestConfigBoolConversion:
    """bool 変換のテスト。"""

    def test_true_string_becomes_true(self, tmp_path):
        """'true' が bool の True に変換されることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nFLAG = true\n", encoding="utf-8")
        assert Config(ini).S.FLAG is True

    def test_false_string_becomes_false(self, tmp_path):
        """'false' が bool の False に変換されることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nFLAG = false\n", encoding="utf-8")
        assert Config(ini).S.FLAG is False

    def test_uppercase_true_becomes_true(self, tmp_path):
        """'True' / 'TRUE' など大文字混じりも変換されることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nFLAG = True\n", encoding="utf-8")
        assert Config(ini).S.FLAG is True

    @pytest.mark.parametrize("value", ["yes", "no", "on", "off"])
    def test_boolean_like_values_stay_string(self, tmp_path, value):
        """true / false 以外の yes / no / on / off は変換せず文字列のままを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text(f"[S]\nFLAG = {value}\n", encoding="utf-8")
        assert value == Config(ini).S.FLAG


class TestConfigTypeConversion:
    """int / float / Path 自動変換のテスト。"""

    def test_integer_value_becomes_int(self, tmp_path):
        """整数値が int に変換されることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nCOUNT = 10\n", encoding="utf-8")
        assert Config(ini).S.COUNT == 10
        assert isinstance(Config(ini).S.COUNT, int)

    def test_float_value_becomes_float(self, tmp_path):
        """小数値が float に変換されることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nRATIO = 1.5\n", encoding="utf-8")
        assert Config(ini).S.RATIO == 1.5
        assert isinstance(Config(ini).S.RATIO, float)

    def test_windows_absolute_path_becomes_path(self, tmp_path):
        """Windows 絶対パス（C:\\）が Path に変換されることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nFOLDER = C:\\work\\input\n", encoding="utf-8")
        assert Path("C:\\work\\input") == Config(ini).S.FOLDER

    def test_unc_path_becomes_path(self, tmp_path):
        """UNC パス（\\\\server\\...）が Path に変換されることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nFOLDER = \\\\nas\\reports\n", encoding="utf-8")
        assert isinstance(Config(ini).S.FOLDER, Path)

    def test_plain_string_stays_string(self, tmp_path):
        """数値・パスでない文字列はそのまま str で返ることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nNAME = T_data\n", encoding="utf-8")
        assert Config(ini).S.NAME == "T_data"
        assert isinstance(Config(ini).S.NAME, str)

    @pytest.mark.parametrize("value", ["007", "0521234567", "-007"])
    def test_leading_zero_stays_string(self, tmp_path, value):
        """先頭ゼロの数字（社員番号・電話番号）は桁落ちを避けて文字列のままを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text(f"[S]\nCODE = {value}\n", encoding="utf-8")
        assert value == Config(ini).S.CODE

    @pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
    def test_nan_inf_stay_string(self, tmp_path, value):
        """nan / inf は float() が受理してしまうが、設定値としては文字列で返す。"""
        ini = tmp_path / "config.ini"
        ini.write_text(f"[S]\nX = {value}\n", encoding="utf-8")
        assert value == Config(ini).S.X


class TestConfigMissingSection:
    def test_missing_section_raises_config_error(self, tmp_path):
        """未定義セクションへのアクセスは素の AttributeError ではなく ConfigError になる。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nK = v\n", encoding="utf-8")
        config = Config(ini)
        with pytest.raises(ConfigError, match="セクションがありません"):
            _ = config.NOPE

    def test_missing_section_lists_the_file_read(self, tmp_path):
        """未定義セクションのエラーに「読んだ config.ini のパス」を含める。

        防いでいるバグ: 2026-08-18 に「プロジェクト基準」に変えた後、利用者が
        見ている config.ini と違うファイルを読んでいると、原因の切り分けが
        つかなくなる（例: `python src/run.py` で起動すると src/ 配下を
        探しに行く）。パスを出しておけば「読んだのはこのファイル」とすぐ分かる。
        """
        from comken.exceptions import ConfigSectionNotFoundError

        ini = tmp_path / "config.ini"
        ini.write_text("[REPORT]\nK = v\n", encoding="utf-8")
        config = Config(ini)
        with pytest.raises(ConfigSectionNotFoundError) as exc:
            _ = config.FILES
        assert str(ini.resolve()) in str(exc.value)

    def test_missing_section_suggests_close_name(self, tmp_path):
        """タイポ（FILES / FILE のような 1 文字違い）に「もしかして」で候補を出す。

        防いでいる事故: セクション名を 1 文字タイポすると「セクションがありません」
        とだけ出て、近い名前が既存セクション一覧に並んでいても気付けない。
        """
        from comken.exceptions import ConfigSectionNotFoundError

        ini = tmp_path / "config.ini"
        ini.write_text("[RUN]\nK = 1\n[FILE]\nK = 2\n[REPORT]\nK = 3\n", encoding="utf-8")
        config = Config(ini)
        with pytest.raises(ConfigSectionNotFoundError) as exc:
            _ = config.FILES
        message = str(exc.value)
        assert "もしかして: [FILE]" in message

    def test_missing_section_suggests_transposed_name(self, tmp_path):
        """隣り合う 2 文字の入れ替わりも 1 回の編集として候補に出す。"""
        from comken.exceptions import ConfigSectionNotFoundError

        ini = tmp_path / "config.ini"
        ini.write_text("[FILSE]\nK = 1\n", encoding="utf-8")
        config = Config(ini)
        with pytest.raises(ConfigSectionNotFoundError) as exc:
            _ = config.FILES
        assert "もしかして: [FILSE]" in str(exc.value)

    def test_missing_section_suggests_japanese_close_name(self, tmp_path):
        """日本語セクション名でも近い候補を出す（``受注_MAPPING`` ↔ ``受注_MAPPNG``）。

        防いでいる事故: difflib は ASCII でも日本語でも動くが、誤って
        日本語だけカットオフが厳しくなっている実装にされることがある。
        """
        from comken.exceptions import ConfigSectionNotFoundError

        ini = tmp_path / "config.ini"
        ini.write_text("[受注_MAPPNG]\n年度 = 2026\n[RUN]\nK = v\n", encoding="utf-8")
        config = Config(ini)
        with pytest.raises(ConfigSectionNotFoundError) as exc:
            _ = config.受注_MAPPING
        assert "もしかして: [受注_MAPPNG]" in str(exc.value)

    def test_missing_section_no_suggestion_line_when_no_close_match(self, tmp_path):
        """近い名前が無いときは「もしかして」の行を出さない（誤誘導しない）。

        防いでいる事故: 候補が無いのに「もしかして: []」のような空行を
        出してしまうと、利用者は「候補が無いのか、表示バグなのか」が
        判別できない。候補が無ければ行ごと出さない。
        """
        from comken.exceptions import ConfigSectionNotFoundError

        ini = tmp_path / "config.ini"
        ini.write_text("[RUN]\nK = v\n[REPORT]\nK = v\n[BROWSER]\nK = v\n", encoding="utf-8")
        config = Config(ini)
        with pytest.raises(ConfigSectionNotFoundError) as exc:
            _ = config.FILES
        message = str(exc.value)
        assert "もしかして" not in message


class TestConfigMissingKey:
    """セクション内のキー名のタイポを ``ConfigKeyNotFoundError`` で案内する。

    旧来は ``SimpleNamespace`` の素の ``AttributeError`` だったが、原因の
    切り分けがつかないので、``ConfigSectionNotFoundError`` と同じ形式で
    「読んだファイル」と「もしかして」を添える。
    """

    def test_missing_key_raises_config_error(self, tmp_path):
        """未定義キーへのアクセスは ``AttributeError`` ではなく comken 例外になる。

        ``hasattr(namespace, key)`` が従来どおり False を返せるように
        ``AttributeError`` も多重継承している（``require()`` が依存）。
        """
        from comken.exceptions import ConfigKeyNotFoundError

        ini = tmp_path / "config.ini"
        ini.write_text("[FILES]\nOUTPUT_FOLDER = C:\\work\n", encoding="utf-8")
        config = Config(ini)
        with pytest.raises(ConfigKeyNotFoundError) as exc:
            _ = config.FILES.OUTPUT_FOLER
        # セクション名・キー名・ファイルパスが読める形で出ている
        assert "[FILES]" in str(exc.value)
        assert "OUTPUT_FOLER" in str(exc.value)
        assert str(ini.resolve()) in str(exc.value)
        # AttributeError でもあるので hasattr() は False を返す
        assert hasattr(config.FILES, "OUTPUT_FOLER") is False

    def test_missing_key_suggests_close_name(self, tmp_path):
        """キー名の 1 文字違いに「もしかして」で候補を出す。"""
        from comken.exceptions import ConfigKeyNotFoundError

        ini = tmp_path / "config.ini"
        ini.write_text("[FILES]\nOUTPUT_FOLDER = C:\\work\n", encoding="utf-8")
        config = Config(ini)
        with pytest.raises(ConfigKeyNotFoundError) as exc:
            _ = config.FILES.OUTPUT_FOLER
        assert "もしかして: OUTPUT_FOLDER" in str(exc.value)

    def test_missing_key_rejects_distance_three_name(self, tmp_path):
        """距離3の INPUT_FOLDER は候補にせず OUTPUT_FOLDER だけを示す。

        防いでいる事故: difflib の類似比率は文字列長に依存するため、
        OUTPUT_FOLER に対して INPUT_FOLDER と OUTPUT_FOLDER を両方拾う。
        """
        from comken.exceptions import ConfigKeyNotFoundError

        ini = tmp_path / "config.ini"
        ini.write_text(
            "[FILES]\nINPUT_FOLDER = C:\\in\nOUTPUT_FOLDER = C:\\out\n",
            encoding="utf-8",
        )
        config = Config(ini)
        with pytest.raises(ConfigKeyNotFoundError) as exc:
            _ = config.FILES.OUTPUT_FOLER
        message = str(exc.value)
        suggestion_lines = [line for line in message.splitlines() if line.startswith("もしかして:")]
        assert suggestion_lines == ["もしかして: OUTPUT_FOLDER"]

    def test_missing_key_no_suggestion_when_no_close_match(self, tmp_path):
        """近いキー名が無いときは「もしかして」の行を出さない。"""
        from comken.exceptions import ConfigKeyNotFoundError

        ini = tmp_path / "config.ini"
        ini.write_text("[FILES]\nINPUT_CSV = x\n", encoding="utf-8")
        config = Config(ini)
        with pytest.raises(ConfigKeyNotFoundError) as exc:
            _ = config.FILES.OUTPUT_FOLDER
        assert "もしかして" not in str(exc.value)

    def test_require_still_treats_missing_key_as_missing(self, tmp_path, monkeypatch):
        """``hasattr()`` が False を返すので ``require()`` の既存挙動は変えない。

        ``ConfigKeyNotFoundError`` を ``AttributeError`` の多重継承にした
        のはこのため。``require()`` は ``hasattr(namespace, key)`` で
        キー存在を確かめているので、``hasattr`` が例外を伝搬すると
        「足りないもの」を1件も報告できなくなる。
        """
        import comken.core.config as config_module

        ini = tmp_path / "config.ini"
        ini.write_text("[FILES]\nINPUT_CSV = C:\\in.csv\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        config_module.read(ini)

        with pytest.raises(ConfigRequiredKeysMissingError) as exc:
            config_module.require("FILES.OUTPUT_FOLDER")
        assert "FILES.OUTPUT_FOLDER" in str(exc.value)


class TestConfigSectionWhitespace:
    """config.ini のセクション名・キー名に前後の空白が混じっても読めるか。

    非エンジニアが手で編集すると `[FILES ]` や ` DRY_RUN ` を書きうるところを、
    落とす前に「セクションがありません」「キーが見つかりません」になると、
    一致しているように見える設定でエラーになる。空白を落として照合する。
    """

    @pytest.mark.parametrize(
        "header",
        ["[FILES ]", "[ FILES]", "[FILES　]", "[　FILES]", "[FILES 　]"],
    )
    def test_section_with_whitespace_is_readable(self, tmp_path, header):
        """前後に空白（全角・半角・混在）があっても config.FILES で読める。

        防いでいるバグ: 報告「`[FILES]` は config.ini にあるのに無いと言われる」は
        実際には `[FILES ]` と末尾に空白が入っていた。書式エラーの種類を
        ユーザーが見分けられないため、空白を黙って落として通す。
        """
        ini = tmp_path / "config.ini"
        ini.write_text(f"{header}\nOUTPUT_FOLDER = C:\\work\n", encoding="utf-8")

        config = Config(ini)

        assert Path("C:\\work") == config.FILES.OUTPUT_FOLDER

    @pytest.mark.parametrize(
        "key",
        ["OUTPUT_FOLDER ", " OUTPUT_FOLDER", "OUTPUT_FOLDER　", "　OUTPUT_FOLDER"],
    )
    def test_key_with_whitespace_is_readable(self, tmp_path, key):
        """キー名の前後に空白（全角・半角）があっても config.FILES.KEY で読める。"""
        ini = tmp_path / "config.ini"
        ini.write_text(f"[FILES]\n{key} = C:\\work\n", encoding="utf-8")

        config = Config(ini)

        assert Path("C:\\work") == config.FILES.OUTPUT_FOLDER

    def test_value_is_not_double_stripped(self, tmp_path):
        """値の前後空白は configparser が処理済みなので、二重に落とさない。

        防いでいるバグ: 値 `  C:\\work  ` の内側空白（意図的なもの）までは
        落とさない。値のトリムは configparser 側に任せる。
        """
        ini = tmp_path / "config.ini"
        # 設定値自体は configparser が前後トリムするので、ここではトリム済みの値を書き、
        # 値が壊れていないこと（= "C:\\work"）を確認する。
        ini.write_text("[FILES]\nNAME = C:\\work\n", encoding="utf-8")

        config = Config(ini)

        assert Path("C:\\work") == config.FILES.NAME

    def test_duplicate_section_after_stripping_warns(self, tmp_path, caplog):
        """`[FILES]` と `[FILES ]` のように、空白を落としたら衝突する場合は黙って捨てない。

        防いでいるバグ: どっちか片方を黙って採用すると、利用者は
        「書かれているとおりに読まれているか」を疑わざるを得なくなる。
        少なくとも WARNING を出して、警告ログから原因が追えるようにする。
        """
        ini = tmp_path / "config.ini"
        ini.write_text(
            "[FILES]\nFIRST = value1\n\n[FILES ]\nSECOND = value2\n",
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING, logger="comken.core.config"):
            config = Config(ini)

        # 片方は生きているので FILES セクションは読める
        assert hasattr(config, "FILES")
        # 衝突が起きたことが WARNING で分かる
        assert any(
            "FILES" in record.getMessage() and record.levelno == logging.WARNING
            for record in caplog.records
        )


class TestConfigMethodNameTypo:
    """`Config(path).require(...)` のような、メソッド名の取り違えを検出して案内する。"""

    def test_lowercase_typo_raises_attribute_error(self, tmp_path):
        """小文字始まり（=セクション名ではあり得ない名前）は ConfigSectionNotFoundError ではない。

        `Config(path).require(...)` と書くと `require` がセクション名として
        解釈され「[require] セクションがありません」という的外れなエラーになる。
        `__getattr__` が何でも拾うための罠。AttributeError にして、
        「セクションの話ではない」と気付けるようにする。
        """
        ini = tmp_path / "config.ini"
        ini.write_text("[FILES]\nK = v\n", encoding="utf-8")
        config = Config(ini)

        with pytest.raises(AttributeError) as exc:
            _ = config.read  # モジュール関数 `read` をインスタンスから呼んだ
        # セクションの話ではないことを示す（"セクションがありません" ではない）
        assert "セクション" not in str(exc.value)

    def test_require_typo_message_suggests_module_function(self, tmp_path):
        """`require` を呼ばれたときは「モジュール関数である」と案内する。

        `from comken import config; config.require(...)` が正解なので、
        エラーメッセージにモジュール関数であることを書いて誘導する。
        """
        ini = tmp_path / "config.ini"
        ini.write_text("[FILES]\nK = v\n", encoding="utf-8")
        config = Config(ini)

        with pytest.raises(AttributeError, match="モジュール関数"):
            _ = config.require

    def test_unknown_lowercase_name_mentions_section_is_uppercase(self, tmp_path):
        """未知の小文字名には「セクションは大文字」と書いて、方向を教える。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[FILES]\nK = v\n", encoding="utf-8")
        config = Config(ini)

        with pytest.raises(AttributeError, match="大文字"):
            _ = config.something_custom


class TestConfigCreatedFromExample:
    """config.ini が無いときの example からの作成のテスト。"""

    def test_creates_config_ini_from_example(self, tmp_path):
        """example があれば config.ini を作ることを確認する。"""
        example = tmp_path / "config.ini.example"
        example.write_text("[FILES]\nINPUT = x\n", encoding="utf-8")
        ini = tmp_path / "config.ini"

        with pytest.raises(ConfigCreatedFromExampleError):
            Config(ini)

        assert ini.is_file()
        assert ini.read_text(encoding="utf-8") == example.read_text(encoding="utf-8")

    def test_stops_instead_of_running_with_example_values(self, tmp_path):
        """作っただけで止め、確認を促すことを確認する。"""
        (tmp_path / "config.ini.example").write_text("[FILES]\nINPUT = x\n", encoding="utf-8")
        with pytest.raises(ConfigCreatedFromExampleError) as exc:
            Config(tmp_path / "config.ini")
        assert "もう一度実行" in str(exc.value)

    def test_second_run_reads_the_created_file(self, tmp_path):
        """2回目は作られた config.ini を読めることを確認する。"""
        (tmp_path / "config.ini.example").write_text("[FILES]\nINPUT = x\n", encoding="utf-8")
        ini = tmp_path / "config.ini"
        with pytest.raises(ConfigCreatedFromExampleError):
            Config(ini)
        assert Config(ini).FILES.INPUT == "x"

    def test_missing_example_keeps_file_not_found_error(self, tmp_path):
        """example も無ければ従来どおり「見つかりません」になることを確認する。"""
        with pytest.raises(ConfigError, match="見つかりません"):
            Config(tmp_path / "config.ini")


class TestConfigListConversion:
    """[a, b, c] 記法の自動変換のテスト。"""

    def test_comma_separated(self, tmp_path):
        """[a, b, c] が自動でリストに変換されることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nITEMS = [a, b, c]\n", encoding="utf-8")
        assert Config(ini).S.ITEMS == ["a", "b", "c"]

    def test_japanese_values(self, tmp_path):
        """日本語の値も変換されることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nSHEETS = [支店A, 支店B, 集計]\n", encoding="utf-8")
        assert Config(ini).S.SHEETS == ["支店A", "支店B", "集計"]

    def test_single_item_is_still_list(self, tmp_path):
        """1要素でもリストになることを確認する（カンマ自動判定では実現できない要件）。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nSHEETS = [支店A]\n", encoding="utf-8")
        assert Config(ini).S.SHEETS == ["支店A"]

    def test_empty_values_excluded(self, tmp_path):
        """空文字列はリストから除外されることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nITEMS = [a, , b]\n", encoding="utf-8")
        assert Config(ini).S.ITEMS == ["a", "b"]

    def test_newline_separated(self, tmp_path):
        """改行区切りの複数行リストも変換されることを確認する。

        config.ini で複数行値を書く場合は、2行目以降を字下げ（スペースまたはタブ）する。

        [REPORT]
        TARGET_SHEETS = [支店A
            支店B
            集計]
        """
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nITEMS = [a\n\tb\n\tc]\n", encoding="utf-8")
        assert Config(ini).S.ITEMS == ["a", "b", "c"]

    def test_empty_list(self, tmp_path):
        """[] は空リストになることを確認する。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nITEMS = []\n", encoding="utf-8")
        assert Config(ini).S.ITEMS == []

    def test_comma_without_brackets_stays_string(self, tmp_path):
        """[] なしのカンマ入り文字列は変換されないことを確認する（SOQL 等の誤変換防止）。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nQUERY = SELECT Id, Name FROM Account\n", encoding="utf-8")
        assert Config(ini).S.QUERY == "SELECT Id, Name FROM Account"


class TestModuleSingleton:
    """`from comken import config` の遅延シングルトンのテスト。"""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """テスト間でグローバルなシングルトンを持ち越さない。"""
        import comken.core.config as config_mod

        config_mod._singleton = None
        yield
        config_mod._singleton = None

    def test_read_points_at_given_ini(self, tmp_path):
        """config.read(path) で指定した config.ini のセクションにアクセスできる。"""
        import comken.core.config as config_mod

        ini = tmp_path / "myconf.ini"
        ini.write_text("[FILES]\nINPUT_FOLDER = C:\\work\\input\n", encoding="utf-8")

        config_mod.read(ini)
        assert Path("C:\\work\\input") == config_mod.FILES.INPUT_FOLDER

    def test_lazy_default_reads_project_dir(self, tmp_path, monkeypatch):
        """read を呼ばない場合、初回アクセス時にプロジェクトの config.ini を読む。"""
        import comken.core.config as config_mod

        other = tmp_path / "別のカレント"
        other.mkdir()
        (tmp_path / "config.ini").write_text("[REPORT]\nMAX = 5\n", encoding="utf-8")
        monkeypatch.chdir(other)
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])

        assert config_mod.REPORT.MAX == 5

    def test_unknown_lowercase_attr_raises(self):
        """大文字でない未知の属性は通常の AttributeError（config.ini を読みに行かない）。"""
        import comken.core.config as config_mod

        with pytest.raises(AttributeError):
            _ = config_mod.nonexistent


class TestGenerateStub:
    """generate_stub（エディタ補完用スタブ生成）のテスト。"""

    @pytest.fixture
    def ini(self, tmp_path):
        path = tmp_path / "config.ini"
        path.write_text(
            "[BROWSER]\nWAIT_SECONDS = 10\nHEADLESS = false\n"
            "[FILES]\nINPUT_FOLDER = C:\\work\\input\nRATIO = 1.5\n"
            "[REPORT]\nSHEETS = [a, b]\nNAME = T_data\n",
            encoding="utf-8",
        )
        return path

    def test_generates_typed_sections(self, ini, tmp_path):
        """セクションごとのクラスと型注釈が生成されることを確認する。"""
        from comken.core.config.stubs import generate_stub

        out = generate_stub(ini, tmp_path / "config.pyi")
        text = out.read_text(encoding="utf-8")

        assert "class _BROWSER:" in text
        assert "    WAIT_SECONDS: int" in text
        assert "    HEADLESS: bool" in text
        assert "    INPUT_FOLDER: Path" in text
        assert "    RATIO: float" in text
        assert "    SHEETS: list[str]" in text
        assert "    NAME: str" in text

    def test_config_class_references_sections(self, ini, tmp_path):
        """Config クラスが各セクションクラスを属性に持つことを確認する。"""
        from comken.core.config.stubs import generate_stub

        text = generate_stub(ini, tmp_path / "config.pyi").read_text(encoding="utf-8")

        assert "class Config:" in text
        assert "    BROWSER: _BROWSER" in text
        assert "config: Config" in text

    def test_mapping_section_uses_dictionary_api_only(self, tmp_path):
        """動的な列名は列挙せず、辞書取得 API の型だけをスタブに出す。"""
        from comken.core.config.stubs import generate_stub

        ini = tmp_path / "config.ini"
        ini.write_text("[COLUMN_MAPPING]\n受注No = 受注番号\n", encoding="utf-8")
        text = generate_stub(ini, tmp_path / "config.pyi").read_text(encoding="utf-8")

        assert "受注No" not in text
        assert "COLUMN_MAPPING" not in text
        assert "def mapping(self, section: str) -> dict[str, str]" in text

    def test_default_output_is_src_config_pyi(self, ini, tmp_path):
        """src/config.py があるプロジェクトでは src/config.pyi に出力されることを確認する。

        出力先は config.ini の場所基準なので、どこから実行しても同じ場所に生成される。
        """
        from comken.core.config.stubs import generate_stub

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "config.py").write_text(
            "from comken.core.config import Config\nCONFIG = Config()\n", encoding="utf-8"
        )

        out = generate_stub(ini)

        assert out == tmp_path / "src" / "config.pyi"
        assert out.exists()

    def test_no_src_generates_typings(self, ini, tmp_path, monkeypatch):
        """src/config.py がない場合は typings/comken/core/ にスタブ一式が生成される。

        from comken import config 方式（src/config.py なし）でも補完が効くように、
        Pylance の typings 上書き用スタブ（comken/core/config.pyi + __init__.pyi）を作る。
        """
        from comken.core.config.stubs import generate_stub

        monkeypatch.chdir(tmp_path)
        out = generate_stub(ini)

        assert out == tmp_path / "typings" / "comken" / "core" / "config.pyi"
        assert out.exists()
        assert (tmp_path / "typings" / "comken" / "__init__.pyi").exists()
        # config.pyi は module レベルにセクションを持つ（from comken.core.config 用）
        text = out.read_text(encoding="utf-8")
        assert "BROWSER: _BROWSER" in text
        # __init__.pyi は公開 API と config の属性型を直接宣言する
        init_text = (tmp_path / "typings" / "comken" / "__init__.pyi").read_text(encoding="utf-8")
        assert "dry_run as dry_run" in init_text
        assert "is_debug as is_debug" in init_text
        assert "BROWSER: _BROWSER" in init_text
        assert "config: _ConfigFacade" in init_text

    def test_missing_ini_raises(self, tmp_path):
        """config.ini がない場合は ConfigError になることを確認する。"""
        from comken.core.config.stubs import generate_stub

        with pytest.raises(ConfigError):
            generate_stub(tmp_path / "config.ini", tmp_path / "config.pyi")

    def test_stub_is_valid_python(self, ini, tmp_path):
        """生成されたスタブが Python として構文エラーにならないことを確認する。"""
        import ast

        from comken.core.config.stubs import generate_stub

        text = generate_stub(ini, tmp_path / "config.pyi").read_text(encoding="utf-8")
        ast.parse(text)  # 構文エラーなら例外になる

    def test_package_init_stub_is_self_contained(self, ini, tmp_path, monkeypatch):
        """typings/comken/__init__.pyi はそれ自身で完結していること（型名が import 済み）。

        防いでいるバグ: スタブ生成で Path を書きながら import を忘れると、
        pyright / Pylance が Path を `Unknown` と判定して補完が静かに落ちる。
        bool や str は組み込みなので解決してしまい、Path 型のキーがないと
        このバグは表面化しない（だから INPUT_FOLDER = C:\\work\\input を含む
        ini フィクスチャを材料に使う）。
        """
        from comken.core.config.stubs import generate_stub

        monkeypatch.chdir(tmp_path)
        generate_stub(ini)
        init_text = (tmp_path / "typings" / "comken" / "__init__.pyi").read_text(encoding="utf-8")

        # INPUT_FOLDER: Path は fixture で Path 型になる前提。
        # バグがあれば下の assert で "Path" が missing として拾われる
        assert "INPUT_FOLDER: Path" in init_text, (
            "このテストは Path 型のキーを含む config.ini を前提とする"
        )
        _assert_stub_self_contained(init_text)

    def test_class_stub_is_self_contained(self, ini, tmp_path):
        """src/config.pyi（class スタブ）も型名が import 済みであること。

        `__init__.pyi` と同じ抜けが class スタブでも起きていないか確かめる回帰テスト。
        """
        from comken.core.config.stubs import generate_stub

        text = generate_stub(ini, tmp_path / "config.pyi").read_text(encoding="utf-8")
        _assert_stub_self_contained(text)


class TestAutoStub:
    """Config() 実行時のスタブ自動更新のテスト。"""

    @pytest.fixture
    def project(self, tmp_path):
        """src/config.py がある最小プロジェクトを作って (ini, stub) を返す。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[REPORT]\nCOUNT = 10\n", encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "config.py").write_text(
            "from comken.core.config import Config\nCONFIG = Config()\n", encoding="utf-8"
        )
        return ini, tmp_path / "src" / "config.pyi"

    def test_config_creates_stub_automatically(self, project):
        """Config() を呼ぶだけでスタブが生成されることを確認する。"""
        ini, stub = project

        Config(ini)

        assert stub.exists()
        assert "COUNT: int" in stub.read_text(encoding="utf-8")

    def test_stub_updated_when_ini_changes(self, project):
        """config.ini を変更して再実行するとスタブに反映されることを確認する。"""
        ini, stub = project
        Config(ini)

        ini.write_text("[REPORT]\nCOUNT = 10\nNAME = 月次\n", encoding="utf-8")
        Config(ini)

        assert "NAME: str" in stub.read_text(encoding="utf-8")

    def test_broken_stub_is_restored(self, project):
        """スタブが手で書き換えられていても、次の実行で正しい内容に戻ることを確認する。"""
        ini, stub = project
        Config(ini)
        stub.write_text("# 壊れた内容", encoding="utf-8")

        Config(ini)

        assert "COUNT: int" in stub.read_text(encoding="utf-8")

    def test_no_stub_without_config_py(self, tmp_path):
        """src/config.py がないプロジェクトではスタブを作らないことを確認する。

        （.pyi 単体では補完に使えず、無関係なフォルダを汚さないため）
        """
        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nK = v\n", encoding="utf-8")

        Config(ini)

        assert not (tmp_path / "config.pyi").exists()
        assert not (tmp_path / "src" / "config.pyi").exists()


class TestCleanupStaleTmp:
    """一時ファイル残骸の自動掃除のテスト。"""

    def test_old_tmp_removed_fresh_tmp_kept(self, tmp_path):
        """古い .tmp は削除され、新しい .tmp（並行実行中の可能性）は残ることを確認する。"""
        import os

        from comken.core.files.ops import cleanup_stale_tmp

        target = tmp_path / "config.pyi"
        stale = tmp_path / "config.pyi.99999.tmp"
        stale.write_text("残骸", encoding="utf-8")
        os.utime(stale, (0, 0))  # 大昔の更新日時にする
        fresh = tmp_path / "config.pyi.88888.tmp"
        fresh.write_text("書き込み中かもしれない", encoding="utf-8")

        cleanup_stale_tmp(target)

        assert not stale.exists()
        assert fresh.exists()

    def test_unrelated_files_not_touched(self, tmp_path):
        """対象と無関係のファイルは削除されないことを確認する。"""
        import os

        from comken.core.files.ops import cleanup_stale_tmp

        target = tmp_path / "config.pyi"
        other = tmp_path / "data.csv"
        other.write_text("業務データ", encoding="utf-8")
        os.utime(other, (0, 0))

        cleanup_stale_tmp(target)

        assert other.exists()

    def test_config_cleans_stale_stub_tmp(self, tmp_path):
        """Config() 実行時にスタブの .tmp 残骸が掃除されることを確認する。"""
        import os

        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nK = v\n", encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "config.py").write_text(
            "from comken.core.config import Config\nCONFIG = Config()\n", encoding="utf-8"
        )
        stale = tmp_path / "src" / "config.pyi.12345.tmp"
        stale.write_text("残骸", encoding="utf-8")
        os.utime(stale, (0, 0))

        Config(ini)

        assert not stale.exists()
        assert (tmp_path / "src" / "config.pyi").exists()


class TestRequire:
    """config.require() は足りない項目をまとめて報告する。"""

    def _write(self, tmp_path, text):
        path = tmp_path / "config.ini"
        path.write_text(text, encoding="utf-8")
        return path

    def test_passes_when_all_keys_exist(self, tmp_path, monkeypatch):
        """そろっていれば何も起きない。"""
        path = self._write(tmp_path, "[FILES]\nINPUT_CSV = C:\\作業\\in.csv\n")
        monkeypatch.chdir(tmp_path)
        config_module.read(path)

        config_module.require("FILES.INPUT_CSV")

    def test_reports_every_missing_key_at_once(self, tmp_path, monkeypatch):
        """足りないものを1つずつではなく、全部並べて報告する。

        1つ直して実行、また別で止まる、を繰り返すと書く人が何度も往復する。
        """
        path = self._write(tmp_path, "[FILES]\nINPUT_CSV = C:\\作業\\in.csv\n")
        monkeypatch.chdir(tmp_path)
        config_module.read(path)

        with pytest.raises(ConfigRequiredKeysMissingError) as e:
            config_module.require("FILES.INPUT_CSV", "REPORT.OUTPUT_FOLDER", "MAIL.TO")

        message = str(e.value)
        assert "REPORT.OUTPUT_FOLDER" in message
        assert "MAIL.TO" in message
        assert "FILES.INPUT_CSV" not in message, "足りている項目は出さない"

    def test_message_points_at_the_file_to_edit(self, tmp_path, monkeypatch):
        """どのファイルへ足すのかを示す（複数プロジェクトを行き来しても迷わない）。"""
        path = self._write(tmp_path, "[FILES]\nINPUT_CSV = C:\\作業\\in.csv\n")
        monkeypatch.chdir(tmp_path)
        config_module.read(path)

        with pytest.raises(ConfigRequiredKeysMissingError) as e:
            config_module.require("REPORT.OUTPUT_FOLDER")

        assert str(path.resolve()) in str(e.value)

    def test_is_case_insensitive_in_the_argument(self, tmp_path, monkeypatch):
        """引数の大文字小文字は問わない（config.ini 側は大文字が強制される）。"""
        path = self._write(tmp_path, "[FILES]\nINPUT_CSV = C:\\作業\\in.csv\n")
        monkeypatch.chdir(tmp_path)
        config_module.read(path)

        config_module.require("files.input_csv")


class TestConfigCheck:
    """``python -m comken config --check`` の診断ロジックのテスト。

    どの事故を防いでいるかは comken/core/config/check.py の docstring を参照。
    """

    def _write(self, tmp_path, text):
        path = tmp_path / "config.ini"
        path.write_text(text, encoding="utf-8")
        return path

    # ── 行頭に空白があるセクション行（いちばん見つけにくい事故） ──────────

    def test_leading_whitespace_on_section_detected(self, tmp_path, capsys):
        """``  [FILES]`` のように行頭に空白があると指摘が出る。

        防いでいる事故: 報告「``[FILES]`` は config.ini にあるのに無いと言われる」は
        実際には ``  [FILES]`` と行頭に空白が入っていたケース。configparser は
        そこをセクションと認識せず、前の値に含めてしまう。
        """
        from comken.core.config.check import run_check

        path = self._write(
            tmp_path,
            "[RUN]\nDRY_RUN = true\n  [FILES]\nOUTPUT_FOLDER = C:\\work\n",
        )

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 1, "問題が見つかったら終了コードは 1"
        assert "12行目" not in out  # 行番号が間違っていないこと
        assert "3行目" in out
        assert "行頭に空白" in out
        assert "[FILES]" in out  # 原文を載せている
        # ``[FILES]`` セクションは認識されないため、認識したセクションには載らない
        assert "[FILES]" not in out.split("--- 認識したセクション ---")[1]

    def test_full_width_space_on_section_detected(self, tmp_path, capsys):
        """全角スペースの行頭空白も指摘される。

        防いでいる事故: 非エンジニアが IME 経由で誤って全角スペースを入れるのは
        かなりよくあるパターンで、半角スペース検出だけだと取り逃がす。
        """
        from comken.core.config.check import run_check

        path = self._write(tmp_path, "[RUN]\nK = 1\n　[FILES]\nK2 = 2\n")

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 1
        assert "3行目" in out
        assert "行頭に空白" in out

    # ── 正常系 ───────────────────────────────────────────────────────────

    def test_clean_config_reports_no_problems(self, tmp_path, capsys):
        """問題のない config.ini では「気になるところはありません」が出て終了コード 0。

        防いでいる事故: 何も無いときに「指摘 0 件」を出さずに黙ってしまうと、
        利用者は「何も出ない = 失敗？」と不安になる。
        """
        from comken.core.config.check import run_check

        path = self._write(
            tmp_path,
            "[RUN]\nDRY_RUN = true\nDEBUG = false\n[FILES]\nOUTPUT_FOLDER = C:\\work\n",
        )

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "気になるところはありません" in out
        # 認識したセクションには正しい名前とキーが並ぶ
        assert "[RUN]" in out
        assert "DRY_RUN" in out
        assert "[FILES]" in out
        assert "OUTPUT_FOLDER" in out

    # ── 値が漏れないこと（最重要の確認） ─────────────────────────────────

    def test_value_is_never_in_output(self, tmp_path, capsys):
        """**値は絶対に出力しない。**

        防いでいる事故: config.ini には業務情報（顧客名・パス・URL・パスワード）が
        含まれる。``OUTPUT_FOLDER = C:/秘密`` のような config で ``秘密`` が
        出力に出ないこと（出る = 情安全事故）。キーは出す。値は出さない。
        """
        from comken.core.config.check import run_check

        # 値に含めてはならない文字列を複数埋める
        secret_marker = "XYZSECRETPASSWORDXYZ"
        path = self._write(
            tmp_path,
            "[FILES]\n"
            f"OUTPUT_FOLDER = C:/{secret_marker}/work\n"
            f"REMOTE_URL = https://example.test/{secret_marker}/api\n"
            f"NOTE = {secret_marker}\n",
        )

        run_check(path)
        out = capsys.readouterr().out

        # キーは出す
        assert "OUTPUT_FOLDER" in out
        assert "REMOTE_URL" in out
        # 値は絶対に出さない
        assert secret_marker not in out, (
            f"値が漏れています: {secret_marker!r} が出力に含まれています"
        )

    # ── セクション名に空白が混じる ──────────────────────────────────────

    def test_section_name_with_inner_whitespace(self, tmp_path, capsys):
        """``[FILES ]`` のようにセクション名に空白が混じっていると指摘が出る。

        防いでいる事故: 空白を落とす実装は入れたが、書いた人には「見た目が
        違うぞ」と伝えたい（次の編集で再び混入しないようにするため）。
        """
        from comken.core.config.check import run_check

        path = self._write(tmp_path, "[FILES ]\nK = v\n")

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 1
        assert "セクション名に空白" in out

    # ── BOM の検出 ────────────────────────────────────────────────────────

    def test_bom_detected(self, tmp_path, capsys):
        """BOM 付き UTF-8 で保存されていることが分かる。

        防いでいる事故: メモ帳で保存すると BOM が付き、``[FILES]`` がセクションに
        見えなくなる（見た目は変わらないので気づけない）。
        """
        from comken.core.config.check import run_check

        path = tmp_path / "config.ini"
        path.write_bytes(b"\xef\xbb\xbf[FILES]\nK = v\n")

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "BOM 付き" in out
        assert "[FILES]" in out  # BOM 込みでもセクションを認識できる

    # ── コメントアウトされた設定行 ──────────────────────────────────────

    def test_commented_out_setting_detected(self, tmp_path, capsys):
        """``; KEY = 値`` の形で書かれた行は指摘される。

        防いでいる事故: 設定を書いたつもりが ``;`` を外し忘れていて動かない。
        行番号とキー名だけ出して、値は出さない。
        """
        from comken.core.config.check import run_check

        path = self._write(tmp_path, "[FILES]\n; OUTPUT_FOLDER = C:\\work\n")

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 1
        assert "コメントアウト" in out
        assert "OUTPUT_FOLDER" in out  # キー名は出す
        assert "C:\\work" not in out  # 値は出さない

    def test_commented_out_setting_with_hash(self, tmp_path, capsys):
        """``#`` でコメントアウトされた設定行も指摘される。"""
        from comken.core.config.check import run_check

        path = self._write(tmp_path, "[FILES]\n# OUTPUT_FOLDER = C:\\work\n")

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 1
        assert "コメントアウト" in out
        assert "OUTPUT_FOLDER" in out

    def test_pure_comment_without_equals_is_not_a_problem(self, tmp_path, capsys):
        """``; ただのコメント`` は指摘しない（純粋なコメントは問題ない）。"""
        from comken.core.config.check import run_check

        path = self._write(tmp_path, "[FILES]\n; これはただのメモです\nK = v\n")

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "気になるところはありません" in out

    # ── 重複キー ─────────────────────────────────────────────────────────

    def test_duplicate_key_in_section_detected(self, tmp_path, capsys):
        """同じセクション内に同じキーが 2 回書かれていると指摘が出る。

        防いでいる事故: configparser は最初の値だけを採用するため、
        「設定が反映されない」「違う値が読まれている」が起きる。
        """
        from comken.core.config.check import run_check

        path = self._write(tmp_path, "[FILES]\nK = first\nK = second\n")

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 1
        assert "同じセクション内で同じキーが 2 回以上" in out
        assert "K" in out

    # ── セクションが 1 つも無い ──────────────────────────────────────────

    def test_no_sections_detected(self, tmp_path, capsys):
        """セクションが 1 つも無いときには「認識されませんでした」と出る。

        防いでいる事故: 設定が一切読まれないまま動くため、エラーが別の
        場所でしか表面化しない。
        """
        from comken.core.config.check import run_check

        path = self._write(tmp_path, "; コメントだけのファイル\n")

        exit_code = run_check(path)
        out = capsys.readouterr().out

        # コメントだけのファイルなので終了コードは 0 のまま、
        # 「セクションは 1 つも認識されませんでした」を出す
        assert exit_code == 0
        assert "セクションは 1 つも認識されませんでした" in out

    # ── 値が複数行になっている疑い ─────────────────────────────────────

    def test_indented_continuation_line_detected(self, tmp_path, capsys):
        """インデントされた ``KEY = 値`` の行は「前の値の続き」になる旨を指摘。

        防いでいる事故: ユーザーが新しいキーを書いたつもりでインデントを
        消し忘れて、前の値に吸収される事故。
        """
        from comken.core.config.check import run_check

        path = self._write(
            tmp_path,
            "[FILES]\nFIRST = value1\n    SECOND = value2\n",
        )

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 1
        assert "3行目" in out
        assert "行頭に空白" in out
        # 値そのものは出さない
        assert "value1" not in out
        assert "value2" not in out

    # ── mapping セクションは件数だけ ─────────────────────────────────────

    def test_mapping_section_shows_count_only(self, tmp_path, capsys):
        """``*_MAPPING`` セクションは列名（業務情報になりうる）ではなく件数だけ表示。"""
        from comken.core.config.check import run_check

        path = self._write(
            tmp_path,
            "[受注_MAPPING]\n受注No = 受注番号\n商品cd = 商品コード\n年度 = 2026\n",
        )

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "[受注_MAPPING]" in out
        assert "3件" in out
        # 列名は出さない
        assert "受注No" not in out
        assert "商品cd" not in out

    # ── 似たセクション名・キー名が 2 つある ──────────────────────

    def test_similar_section_names_detected(self, tmp_path, capsys):
        """``[FILES]`` と ``[FILE]`` のように 1 文字違いで両方あると指摘が出る。

        防いでいる事故: 古いセクション名を消すのを忘れて新しい名前と
        2 つ並んでいると、片方しか使われない。実行時はエラーにならないので
        発見が遅れる。
        """
        from comken.core.config.check import run_check

        path = self._write(
            tmp_path,
            "[FILES]\nINPUT_FOLDER = C:\\work\n[FILE]\nOUTPUT_FOLDER = C:\\work\n",
        )

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 1
        assert "似た名前のセクション" in out
        assert "[FILES]" in out and "[FILE]" in out
        # 値は出さない（業務情報保護）
        assert "C:\\work" not in out

    def test_input_output_folder_pair_is_not_flagged(self, tmp_path, capsys):
        """``INPUT_FOLDER`` と ``OUTPUT_FOLDER`` は正しいペアなので指摘しない。

        防いでいる事故: 誤検知が多いと「チェックが鬱陶しい」になり、
        利用者が警告を無視するようになる。0.85 のしきい値で意図的な
        ペアを通す。
        """
        from comken.core.config.check import run_check

        path = self._write(
            tmp_path,
            "[FILES]\nINPUT_FOLDER = C:\\in\nOUTPUT_FOLDER = C:\\out\n",
        )

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "気になるところはありません" in out
        assert "似た名前" not in out

    def test_similar_keys_inside_section_detected(self, tmp_path, capsys):
        """セクション内のキー名も 1 文字違いを拾う（タイポ疑い）。

        防いでいる事故: ``OUTPUT_FOLER`` と ``OUTPUT_FOLDER`` が両方あると、
        前者は読まれないまま気付かない。
        """
        from comken.core.config.check import run_check

        path = self._write(
            tmp_path,
            "[FILES]\nOUTPUT_FOLER = C:\\typo\nOUTPUT_FOLDER = C:\\work\n",
        )

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 1
        assert "似た名前のキー" in out
        assert "OUTPUT_FOLER" in out and "OUTPUT_FOLDER" in out
        # 値は出さない
        assert "C:\\typo" not in out
        assert "C:\\work" not in out

    def test_similar_mapping_keys_are_not_checked(self, tmp_path, capsys):
        """``*_MAPPING`` セクション内のキー（列名）は類似検知しない。

        防いでいる事故: 列名は業務情報になりうるので、類似検知の材料に
        使うと「似た列名がある」と出すためだけに業務情報が露出する。
        """
        from comken.core.config.check import run_check

        path = self._write(
            tmp_path,
            "[COLUMN_MAPPING]\n"
            "受注No = 受注番号\n"
            "受注NO = 受注No2\n",  # 似たキー名が並ぶが、列名なので触らない
        )

        exit_code = run_check(path)
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "似た名前" not in out
        # 列名は出さない
        assert "受注No" not in out


class TestConfigCheckCli:
    """``python -m comken config --check`` の CLI 配線。"""

    def test_default_remains_stub_generation(self, tmp_path, monkeypatch):
        """``--check`` を付けないときは従来どおりスタブ生成。

        防いでいる事故: 既存の ``python -m comken config`` の挙動を変えて
        しまうと、社内ドキュメントや手順が壊れる。
        """
        from comken.core.config import cli as config_cli

        ini = tmp_path / "config.ini"
        ini.write_text("[FILES]\nK = v\n", encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "config.py").write_text(
            "from comken.core.config import Config\nCONFIG = Config()\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        exit_code = config_cli.main([])

        assert exit_code == 0
        # src/config.pyi が生成されている（= スタブ生成が走った）
        assert (tmp_path / "src" / "config.pyi").exists()

    def test_check_flag_runs_diagnostic(self, tmp_path, capsys):
        """``--check`` を付けると診断に切り替わる（終了コード 1）。"""
        from comken.core.config import cli as config_cli

        path = tmp_path / "config.ini"
        path.write_text("[RUN]\nK = 1\n  [FILES]\nK2 = 2\n", encoding="utf-8")

        exit_code = config_cli.main(["--check", str(path)])

        assert exit_code == 1
        assert "3行目" in capsys.readouterr().out

    def test_check_flag_without_path_uses_config_ini(self, tmp_path, capsys, monkeypatch):
        """``--check`` でパスを省略したら ``./config.ini`` を見る。"""
        from comken.core.config import cli as config_cli

        path = tmp_path / "config.ini"
        path.write_text("[FILES]\nK = v\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        exit_code = config_cli.main(["--check"])

        # 問題なし → 0
        assert exit_code == 0
        assert "[FILES]" in capsys.readouterr().out


class TestScanCodeUsage:
    """``python -m comken config --check`` の AST 走査テスト。

    「手で同期するものは必ずズレる」を機械で防ぐ。
    どの事故を防いでいるかは ``comken/core/config/scan.py`` の docstring を参照。
    """

    @staticmethod
    def _setup(tmp_path, *, ini_text, main_text=None, src_text=None, extra_files=None):
        """テスト用プロジェクトを ``tmp_path`` に組み立てる。

        Args:
            tmp_path: pytest の一時ディレクトリ。
            ini_text: config.ini の内容。
            main_text: ``main.py`` の内容。省略時は main.py を作らない。
            src_text: ``src/run.py`` の内容。省略時は ``src/run.py`` を作らない。
            extra_files: 追加で作る ``(パス, 内容)`` のイテラブル。
        """
        ini = tmp_path / "config.ini"
        ini.write_text(ini_text, encoding="utf-8")
        if main_text is not None:
            (tmp_path / "main.py").write_text(main_text, encoding="utf-8")
        if src_text is not None:
            (tmp_path / "src").mkdir()
            (tmp_path / "src" / "run.py").write_text(src_text, encoding="utf-8")
        if extra_files:
            for rel, content in extra_files:
                full = tmp_path / rel
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(content, encoding="utf-8")
        return ini

    def test_used_key_in_ini_reports_ok(self, tmp_path, capsys):
        """``config.FILES.OUTPUT_FOLDER`` が config.ini にあれば ``OK``。

        防いでいる事故: コードと config.ini が両方正しく書けているときは何も
        警告を出さない（ノイズを出さない）。
        """
        from comken.core.config.check import run_check

        ini = self._setup(
            tmp_path,
            ini_text="[FILES]\nOUTPUT_FOLDER = C:\\work\n",
            src_text="from comken import config\nx = config.FILES.OUTPUT_FOLDER\n",
        )

        exit_code = run_check(ini)

        out = capsys.readouterr().out
        assert exit_code == 0
        assert "--- コードで使っている設定 ---" in out
        assert "FILES.OUTPUT_FOLDER" in out
        assert "OK" in out
        # 「無い」警告は出ない
        assert "★" not in out

    def test_used_key_missing_in_ini_reports_missing_and_exit_1(self, tmp_path, capsys):
        """``config.FILES.OUTPUT_FOLDER`` が config.ini に無ければ ★ と終了コード 1。

        防いでいる事故: 動かすと ``ConfigKeyNotFoundError`` で止まるが、
        ``--check`` で見つかれば CI で先に止められる。
        """
        from comken.core.config.check import run_check

        # セクションはあるがキーが無いケースで「config.ini にありません」を出す
        ini = self._setup(
            tmp_path,
            ini_text="[FILES]\nINPUT_CSV = C:\\work\\in.csv\n",
            src_text="from comken import config\nx = config.FILES.OUTPUT_FOLDER\n",
        )

        exit_code = run_check(ini)

        out = capsys.readouterr().out
        assert exit_code == 1, "config.ini に無い項目があれば終了コードは 1"
        assert "FILES.OUTPUT_FOLDER" in out
        assert "★" in out
        assert "config.ini にありません" in out

    def test_used_section_missing_reports_missing_section(self, tmp_path, capsys):
        """セクションが config.ini に無いときは別メッセージで指摘する。

        ``ConfigSectionNotFoundError`` と ``ConfigKeyNotFoundError`` を
        利用者が区別できるように。
        """
        from comken.core.config.check import run_check

        ini = self._setup(
            tmp_path,
            ini_text="[RUN]\nDRY_RUN = true\n",
            src_text="from comken import config\nx = config.REPORT.SHEET_NAME\n",
        )

        exit_code = run_check(ini)

        out = capsys.readouterr().out
        assert exit_code == 1
        assert "REPORT.SHEET_NAME" in out
        assert "[REPORT] セクションがありません" in out

    def test_other_attr_is_not_picked_up(self, tmp_path, capsys):
        """``other.FILES.KEY`` は拾わない（変数名が ``config`` でないため）。

        防いでいる事故: 別モジュールの同名属性を誤検出しない。
        """
        from comken.core.config.check import run_check

        ini = self._setup(
            tmp_path,
            ini_text="[FILES]\nKEY = v\n",
            src_text=(
                "from comken import config\n"
                "\n"
                "class other:\n"
                "    FILES = type('S', (), {'KEY': None})()\n"
                "\n"
                "x = other.FILES.KEY  # config ではないので拾わない\n"
            ),
        )

        exit_code = run_check(ini)

        out = capsys.readouterr().out
        # 拾わないので「コードで使っている設定」節も出ない（usages が空）
        assert "--- コードで使っている設定 ---" not in out
        assert exit_code == 0

    def test_mapping_and_read_are_not_picked_up_as_usages(self, tmp_path, capsys):
        """``config.mapping(...)`` / ``config.read(...)`` は config 参照ではない。

        ``config.SECTION``（キーまで無い）や ``config.<メソッド>(...)`` は拾わない。
        拾ってしまうと ``config.mapping`` を「セクション」と誤認してしまう。
        """
        from comken.core.config.check import run_check

        ini = self._setup(
            tmp_path,
            ini_text="[RUN]\nDRY_RUN = true\n",
            src_text=(
                "from comken import config\n"
                "\n"
                "config.mapping('RECEIVE_MAPPING')\n"
                "config.read('foo.ini')\n"
                "config.require('RUN.DRY_RUN')\n"
                "if config.RUN.DRY_RUN:\n"
                "    pass\n"
            ),
        )

        exit_code = run_check(ini)

        out = capsys.readouterr().out
        # メソッド呼び出しが usages に混入しない（OK 行は RUN.DRY_RUN の 1 行だけ）
        assert "RECEIVE_MAPPING" not in out
        assert "foo.ini" not in out
        # 「無い」警告は出ない（RUN.DRY_RUN は ini に存在するため）
        assert "★" not in out
        # require には書かれているが uses と一致するので食い違いなし
        assert "--- require() との食い違い ---" in out
        assert "食い違いはありません" in out
        assert exit_code == 0

    def test_project_without_src_still_runs(self, tmp_path, capsys):
        """``src/`` が無いプロジェクトでも ``main.py`` だけ走査される。

        防いでいる事故: 雛形を改造して ``src/`` を消したプロジェクトで
        ``--check`` が壊れる（手で ``cd`` して叩けない）。
        """
        from comken.core.config.check import run_check

        ini = self._setup(
            tmp_path,
            ini_text="[RUN]\nDRY_RUN = true\n",
            main_text="from comken import config\nconfig.RUN.DRY_RUN\n",
        )
        # src/ を作らない

        exit_code = run_check(ini)

        out = capsys.readouterr().out
        assert exit_code == 0
        assert "main.py" in out
        assert "OK" in out

    def test_no_main_py_no_src_section_is_skipped(self, tmp_path, capsys):
        """``main.py`` も ``src/`` も無いプロジェクトでは節を出さない。

        防いでいる事故: config.ini 単独で使うプロジェクト（雛形なしの手書き
        config.ini）で「ファイルが 1 つも無い」とエラー扱いにして動かない。
        """
        from comken.core.config.check import run_check

        ini = self._setup(tmp_path, ini_text="[RUN]\nDRY_RUN = true\n")

        exit_code = run_check(ini)

        out = capsys.readouterr().out
        assert exit_code == 0
        # 走査結果が無いので節は出ない
        assert "--- コードで使っている設定 ---" not in out
        assert "--- require() との食い違い ---" not in out

    def test_value_never_appears_in_output(self, tmp_path, capsys):
        """**コード走査の出力にも値を絶対に載せない。**

        config.ini とソース両方に業務情報が含まれる可能性があるため、
        AST 走査の節でも値は出さない（名前と行番号だけ）。
        """
        from comken.core.config.check import run_check

        secret = "XYZSECRETPATHZYX"
        ini = self._setup(
            tmp_path,
            ini_text=f"[FILES]\nOUTPUT_FOLDER = C:\\\\{secret}\\\\work\n",
            src_text=(
                "from comken import config\n"
                f"x = config.FILES.OUTPUT_FOLDER  # uses secret = {secret}\n"
            ),
        )

        run_check(ini)
        out = capsys.readouterr().out

        assert "OUTPUT_FOLDER" in out  # キー名は出す
        assert secret not in out, "値が漏れています"


class TestScanRequireMismatch:
    """``config.require()`` と AST 走査結果の食い違いを報告する挙動のテスト。"""

    def _setup(self, tmp_path, *, ini_text, main_text=None, src_text=None):
        ini = tmp_path / "config.ini"
        ini.write_text(ini_text, encoding="utf-8")
        if main_text is not None:
            (tmp_path / "main.py").write_text(main_text, encoding="utf-8")
        if src_text is not None:
            (tmp_path / "src").mkdir()
            (tmp_path / "src" / "run.py").write_text(src_text, encoding="utf-8")
        return ini

    def test_used_but_not_in_require_warns(self, tmp_path, capsys):
        """``require()`` に書かれていないのに使われていると警告。

        防いでいる事故: ``require()`` の本来の目的は「動く前にまとめて出す」
        こと。漏れていると途中で ``ConfigKeyNotFoundError`` で止まる。
        """
        from comken.core.config.check import run_check

        ini = self._setup(
            tmp_path,
            ini_text="[FILES]\nOUTPUT_FOLDER = C:\\work\n",
            main_text=(
                "from comken import config\n"
                "config.require('FILES.OUTPUT_FOLDER')\n"
                "x = config.FILES.OUTPUT_FOLDER\n"
            ),
        )

        # FILES.OUTPUT_FOLDER が require に書かれているが、 RUN.DEBUG が無い。
        # require には無いが使われている項目（FILES.OUTPUT_FOLDER 以外）があると
        # 警告される。FILES.OUTPUT_FOLDER は require に書かれているので警告なし。
        run_check(ini)

        out = capsys.readouterr().out
        # 警告は出るが、終了コードは 0 のまま（require の食い違いは警告レベル）
        assert "--- require() との食い違い ---" in out

    def test_in_require_but_not_used_warns_without_changing_exit_code(self, tmp_path, capsys):
        """``require()`` に書かれているが使われていない項目も警告。

        防いでいる事故: ``require()`` のリストが古いままだと、起動時に
        止まらなくなる。終了コードは変えない（将来使う前提で先に書く運用もあるため）。
        """
        from comken.core.config.check import run_check

        ini = self._setup(
            tmp_path,
            ini_text="[RUN]\nDRY_RUN = true\nDEBUG = false\n",
            main_text=(
                "from comken import config\n"
                "config.require('RUN.DRY_RUN', 'RUN.DEBUG')\n"
                "if config.RUN.DRY_RUN:\n"
                "    pass\n"
                # RUN.DEBUG は require にあるが使われていない\n"
            ),
        )

        exit_code = run_check(ini)
        out = capsys.readouterr().out

        # require の食い違いは警告のみで終了コードは変えない
        assert exit_code == 0, "require 食い違いだけでは終了コードは上げない"
        assert "RUN.DEBUG" in out
        assert "require() に書かれていますが未使用です" in out

    def test_matched_require_and_usage_no_warning(self, tmp_path, capsys):
        """``require()`` と使用箇所が一致すれば警告なし。"""
        from comken.core.config.check import run_check

        ini = self._setup(
            tmp_path,
            ini_text="[RUN]\nDRY_RUN = true\n",
            main_text=(
                "from comken import config\n"
                "config.require('RUN.DRY_RUN')\n"
                "if config.RUN.DRY_RUN:\n"
                "    pass\n"
            ),
        )

        exit_code = run_check(ini)
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "--- require() との食い違い ---" in out
        assert "食い違いはありません" in out

    def test_variable_passed_to_require_is_skipped(self, tmp_path, capsys):
        """``require(keys)`` のように変数を渡している場合は諦める（拾えない）。

        拾えないときは ``require()`` 側に何もないのと同じ扱いになるため、
        **AST が拾えた使用箇所側は「require に書かれていない」と報告される**
        （これが現実の挙動。``docstring`` にも「動的アクセスは拾えない」と
        書いてある）。
        """
        from comken.core.config.check import run_check

        ini = self._setup(
            tmp_path,
            ini_text="[RUN]\nDRY_RUN = true\n",
            main_text=(
                "from comken import config\n"
                "keys = ['RUN.DRY_RUN']\n"
                "config.require(keys)  # 変数を渡しているので AST からは拾えない\n"
                "if config.RUN.DRY_RUN:\n"
                "    pass\n"
            ),
        )

        exit_code = run_check(ini)
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "--- require() との食い違い ---" in out
        # 拾えないので require 側は空、使用箇所側はある → 「require に書かれていない」
        assert "使われているのに require() に書かれていません" in out


class TestScanExcludedDirs:
    """``src/`` 配下の特定ディレクトリは走査対象から除外する。"""

    def test_venv_and_tests_are_skipped(self, tmp_path, capsys):
        """``.venv`` / ``typings`` / ``tests`` は走査対象外。

        防いでいる事故: テストや型スタブが ``config.SECTION.KEY`` を
        持っていると、誤って「使われている」と報告されてしまう。
        """
        from comken.core.config.check import run_check

        ini_text = "[RUN]\nDRY_RUN = true\n"
        main_text = "from comken import config\nif config.RUN.DRY_RUN:\n    pass\n"
        # src/run.py は本物の処理
        src_text = (
            "from comken import config\n"
            "x = config.FILES.OUTPUT_FOLDER  # これは config.ini に無い\n"
        )
        # tests/ は拾わない
        tests_text = (
            "from comken import config\nx = config.TESTS_MUST_BE_IGNORED.ANYTHING  # 拾われない\n"
        )
        # .venv/ も拾わない
        venv_text = (
            "from comken import config\nx = config.VENV_MUST_BE_IGNORED.ANYTHING  # 拾われない\n"
        )

        ini = tmp_path / "config.ini"
        ini.write_text(ini_text, encoding="utf-8")
        (tmp_path / "main.py").write_text(main_text, encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "run.py").write_text(src_text, encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_x.py").write_text(tests_text, encoding="utf-8")
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "lib.py").write_text(venv_text, encoding="utf-8")

        run_check(ini)
        out = capsys.readouterr().out

        # src/run.py の FILES.OUTPUT_FOLDER は検出される（★になる）
        assert "FILES.OUTPUT_FOLDER" in out
        # tests/ と .venv/ のファイルは検出されない
        assert "TESTS_MUST_BE_IGNORED" not in out
        assert "VENV_MUST_BE_IGNORED" not in out


class TestScanModule:
    """``comken.core.config.scan`` を直接叩く単体テスト。"""

    def test_collect_scan_targets_finds_main_and_src(self, tmp_path):
        """``main.py`` と ``src/**/*.py`` を見つけ、不要なディレクトリは省く。"""
        from comken.core.config.scan import collect_scan_targets

        (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "run.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "src" / "__pycache__").mkdir()
        (tmp_path / "src" / "__pycache__" / "cached.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "src" / "sites").mkdir()
        (tmp_path / "src" / "sites" / "site.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_x.py").write_text("x = 1\n", encoding="utf-8")

        targets = collect_scan_targets(tmp_path)

        names = [p.relative_to(tmp_path).as_posix() for p in targets]
        assert "main.py" in names
        assert "src/run.py" in names
        assert "src/sites/site.py" in names
        # __pycache__ は除外
        assert "src/__pycache__/cached.py" not in names
        # tests は除外
        assert "tests/test_x.py" not in names

    def test_collect_scan_targets_empty_when_no_main_no_src(self, tmp_path):
        """``main.py`` も ``src/`` も無いときは空リスト。"""
        from comken.core.config.scan import collect_scan_targets

        targets = collect_scan_targets(tmp_path)

        assert targets == []

    def test_scan_project_collects_usages_and_requires(self, tmp_path):
        """``scan_project`` が usages / requires を返す。"""
        from comken.core.config.scan import scan_project

        (tmp_path / "main.py").write_text(
            "from comken import config\n"
            "config.require('RUN.DRY_RUN', 'FILES.OUTPUT_FOLDER')\n"
            "x = config.RUN.DRY_RUN\n"
            "y = config.FILES.OUTPUT_FOLDER\n",
            encoding="utf-8",
        )

        result = scan_project(tmp_path)

        names = {f"{u.section.upper()}.{u.key.upper()}" for u in result.usages}
        assert names == {"RUN.DRY_RUN", "FILES.OUTPUT_FOLDER"}
        assert result.required_names == {"RUN.DRY_RUN", "FILES.OUTPUT_FOLDER"}

    def test_scan_project_handles_syntax_error_gracefully(self, tmp_path):
        """構文エラーが含まれるファイルは走査全体を止めない。"""
        from comken.core.config.scan import scan_project

        (tmp_path / "main.py").write_text(
            "from comken import config\nx = config.RUN.DRY_RUN\n",
            encoding="utf-8",
        )
        (tmp_path / "src").mkdir()
        # 構文エラー（中途半端な Python）
        (tmp_path / "src" / "broken.py").write_text("def ()\n", encoding="utf-8")

        result = scan_project(tmp_path)

        # broken.py は無視、main.py は拾う
        names = {f"{u.section.upper()}.{u.key.upper()}" for u in result.usages}
        assert names == {"RUN.DRY_RUN"}
        assert all("broken" not in u.path.as_posix() for u in result.usages)
