"""
Config クラスのテスト。

実行方法:
    リポジトリのルートで python -m pytest tests/ -v
"""

import logging
from pathlib import Path

import pytest

import comken.config as config_module
from comken.config import Config
from comken.exceptions import (
    ConfigCreatedFromExampleError,
    ConfigError,
    ConfigLowerCaseNameError,
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

        with caplog.at_level(logging.INFO, logger="comken.config"):
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

    def test_default_path_is_config_ini(self, tmp_path, monkeypatch):
        """パス省略時にカレントディレクトリの config.ini を読むことを確認する。"""
        monkeypatch.chdir(tmp_path)
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
        import comken.config as config_mod

        config_mod._singleton = None
        yield
        config_mod._singleton = None

    def test_read_points_at_given_ini(self, tmp_path):
        """config.read(path) で指定した config.ini のセクションにアクセスできる。"""
        import comken.config as config_mod

        ini = tmp_path / "myconf.ini"
        ini.write_text("[FILES]\nINPUT_FOLDER = C:\\work\\input\n", encoding="utf-8")

        config_mod.read(ini)
        assert Path("C:\\work\\input") == config_mod.FILES.INPUT_FOLDER

    def test_lazy_default_reads_cwd(self, tmp_path, monkeypatch):
        """read を呼ばない場合、初回アクセス時にカレントの config.ini を読む。"""
        import comken.config as config_mod

        (tmp_path / "config.ini").write_text("[REPORT]\nMAX = 5\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        assert config_mod.REPORT.MAX == 5

    def test_unknown_lowercase_attr_raises(self):
        """大文字でない未知の属性は通常の AttributeError（config.ini を読みに行かない）。"""
        import comken.config as config_mod

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
        from comken.config.stubs import generate_stub

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
        from comken.config.stubs import generate_stub

        text = generate_stub(ini, tmp_path / "config.pyi").read_text(encoding="utf-8")

        assert "class Config:" in text
        assert "    BROWSER: _BROWSER" in text
        assert "config: Config" in text

    def test_mapping_section_uses_dictionary_api_only(self, tmp_path):
        """動的な列名は列挙せず、辞書取得 API の型だけをスタブに出す。"""
        from comken.config.stubs import generate_stub

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
        from comken.config.stubs import generate_stub

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "config.py").write_text(
            "from comken.config import Config\nCONFIG = Config()\n", encoding="utf-8"
        )

        out = generate_stub(ini)

        assert out == tmp_path / "src" / "config.pyi"
        assert out.exists()

    def test_no_src_generates_typings(self, ini, tmp_path, monkeypatch):
        """src/config.py がない場合は typings/comken/ にスタブ一式が生成される。

        from comken import config 方式（src/config.py なし）でも補完が効くように、
        Pylance の typings 上書き用スタブ（config.pyi + __init__.pyi）を作る。
        """
        from comken.config.stubs import generate_stub

        monkeypatch.chdir(tmp_path)
        out = generate_stub(ini)

        assert out == tmp_path / "typings" / "comken" / "config.pyi"
        assert out.exists()
        assert (tmp_path / "typings" / "comken" / "__init__.pyi").exists()
        # config.pyi は module レベルにセクションを持つ（from comken import config 用）
        text = out.read_text(encoding="utf-8")
        assert "BROWSER: _BROWSER" in text
        # __init__.pyi は comken の公開 API を再エクスポートする
        init_text = (tmp_path / "typings" / "comken" / "__init__.pyi").read_text(encoding="utf-8")
        assert "dry_run as dry_run" in init_text
        assert "is_debug as is_debug" in init_text

    def test_missing_ini_raises(self, tmp_path):
        """config.ini がない場合は ConfigError になることを確認する。"""
        from comken.config.stubs import generate_stub

        with pytest.raises(ConfigError):
            generate_stub(tmp_path / "config.ini", tmp_path / "config.pyi")

    def test_stub_is_valid_python(self, ini, tmp_path):
        """生成されたスタブが Python として構文エラーにならないことを確認する。"""
        import ast

        from comken.config.stubs import generate_stub

        text = generate_stub(ini, tmp_path / "config.pyi").read_text(encoding="utf-8")
        ast.parse(text)  # 構文エラーなら例外になる


class TestAutoStub:
    """Config() 実行時のスタブ自動更新のテスト。"""

    @pytest.fixture
    def project(self, tmp_path):
        """src/config.py がある最小プロジェクトを作って (ini, stub) を返す。"""
        ini = tmp_path / "config.ini"
        ini.write_text("[REPORT]\nCOUNT = 10\n", encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "config.py").write_text(
            "from comken.config import Config\nCONFIG = Config()\n", encoding="utf-8"
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

        from comken.toolbox.utils.files.ops import _cleanup_stale_tmp

        target = tmp_path / "config.pyi"
        stale = tmp_path / "config.pyi.99999.tmp"
        stale.write_text("残骸", encoding="utf-8")
        os.utime(stale, (0, 0))  # 大昔の更新日時にする
        fresh = tmp_path / "config.pyi.88888.tmp"
        fresh.write_text("書き込み中かもしれない", encoding="utf-8")

        _cleanup_stale_tmp(target)

        assert not stale.exists()
        assert fresh.exists()

    def test_unrelated_files_not_touched(self, tmp_path):
        """対象と無関係のファイルは削除されないことを確認する。"""
        import os

        from comken.toolbox.utils.files.ops import _cleanup_stale_tmp

        target = tmp_path / "config.pyi"
        other = tmp_path / "data.csv"
        other.write_text("業務データ", encoding="utf-8")
        os.utime(other, (0, 0))

        _cleanup_stale_tmp(target)

        assert other.exists()

    def test_config_cleans_stale_stub_tmp(self, tmp_path):
        """Config() 実行時にスタブの .tmp 残骸が掃除されることを確認する。"""
        import os

        ini = tmp_path / "config.ini"
        ini.write_text("[S]\nK = v\n", encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "config.py").write_text(
            "from comken.config import Config\nCONFIG = Config()\n", encoding="utf-8"
        )
        stale = tmp_path / "src" / "config.pyi.12345.tmp"
        stale.write_text("残骸", encoding="utf-8")
        os.utime(stale, (0, 0))

        Config(ini)

        assert not stale.exists()
        assert (tmp_path / "src" / "config.pyi").exists()
