"""`comken doctor` のテスト。

「動かない」の切り分けを 1 コマンドに集約するのが目的で、非エンジニアに
「これを打って結果を送って」と言える形にする。ライブラリ関数 ``doctor()``
と CLI エントリの両方を検証する。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import comken
import pytest


# ── comken 自体の情報 ────────────────────────────────────────────────────────


def test_comken_version_reported() -> None:
    """DoctorResult に ``comken.__version__`` が入ること。"""
    from comken.core.doctor.runner import check_comken_version

    result = check_comken_version()
    assert result.status == "ok"
    assert comken.__version__ in result.message


def test_python_version_ok() -> None:
    """3.11 以上のとき ``status="ok"``。

    テスト環境の Python で判定する。3.11 未満では意味がないため skip する。
    """
    if (sys.version_info.major, sys.version_info.minor) < (3, 11):
        pytest.skip("Python 3.11 以上でないとこの分岐を確かめられない")
    from comken.core.doctor.runner import check_python_version

    result = check_python_version()
    assert result.status == "ok"


def test_python_version_ng_below_3_11(monkeypatch: pytest.MonkeyPatch) -> None:
    """3.10 以下のとき ``status="ng"``（``sys.version_info`` を偽装）。"""
    # sys.version_info を NamedTuple 風 SimpleNamespace で差し替える。
    # frozen な実体を書き換えるより、属性ごと置き換えるほうが monkeypatch で戻しやすい。
    fake = types.SimpleNamespace(major=3, minor=10, micro=0, releaselevel="final", serial=0)
    monkeypatch.setattr(sys, "version_info", fake)
    from comken.core.doctor.runner import check_python_version

    result = check_python_version()
    assert result.status == "ng"


# ── 依存モジュール ────────────────────────────────────────────────────────────


def test_missing_dependency_ng(monkeypatch: pytest.MonkeyPatch) -> None:
    """``openpyxl`` が無いとき ``status="ng"``。

    ``sys.modules.pop`` だけだと importlib が再発見してしまうため、
    ``builtins.__import__`` を一時的に置き換えて ``ImportError`` を起こす。
    monkeypatch がテスト後に元に戻してくれるので安全。
    """
    import builtins

    real_import = builtins.__import__

    def fake_import(
        name: str,
        globals: object | None = None,
        locals: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "openpyxl" or name.startswith("openpyxl."):
            raise ImportError("No module named 'openpyxl'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from comken.core.doctor.runner import check_dependency

    result = check_dependency("openpyxl", "openpyxl")
    assert result.status == "ng"
    assert "not installed" in result.message


# ── 設定の正しさ ──────────────────────────────────────────────────────────────


def test_run_section_in_config_ng(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """config.ini に ``[RUN]`` が残っていたら ng。

    ``project_dir()`` を ``tmp_path`` に置き換えて、テスト用の config.ini を
    その場で作る。
    """
    monkeypatch.setattr("comken.core.files.ops.project_dir", lambda: tmp_path)
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[RUN]\nDRY_RUN = true\n\n[FILES]\nINPUT_FOLDER = C:\\work\n",
        encoding="utf-8",
    )
    from comken.core.doctor.runner import check_run_section

    result = check_run_section()
    assert result.status == "ng"
    assert "[RUN] section found" in result.message


def test_rpa_py_still_has_alias_ng(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """rpa.py に ``example_libs.v0000`` が残っていたら ng。

    リポジトリの実ファイルには仮名が残っているため、テスト用の偽ファイルで
    検査関数が正しく動くことを確認する。
    """
    fake_rpa = tmp_path / "rpa.py"
    fake_rpa.write_text(
        "from example_libs.v0000.rpa import backoffice\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("comken.core.doctor.runner._RPA_PATH", fake_rpa)
    from comken.core.doctor.runner import check_rpa_placeholder

    result = check_rpa_placeholder()
    assert result.status == "ng"
    assert "example_libs.v0000" in result.message


# ── Salesforce ───────────────────────────────────────────────────────────────


def test_salesforce_skip_when_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """DPAPI に認証情報が無いとき ``status="skip"``。

    ``list_names`` を空リストを返す関数で差し替えて、資格情報ゼロの状態を作る。
    Salesforce 組織クラスは ``None`` を渡して「import できない」状態を再現する。
    """
    from comken.core.doctor.runner import check_salesforce

    result = check_salesforce(
        names=[],
        sandbox_cls=None,
    )
    assert result.status == "skip"
    assert "salesforce.connectivity" in result.name


def test_does_not_load_requests_for_skipped_salesforce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Salesforce を skip するときに ``requests`` を import しない（BO 環境対応）。

    認証情報が無いなら Salesforce まで進まず SKIP で返るのが正しい。
    Salesforce の client.py は冒頭で ``import requests`` するため、ここで
    import されたら BO 環境（``requests`` が入っていない）で ``doctor`` が
    落ちることになる。

    cli.py の `_resolve_salesforce_deps()` は資格情報が空なら Salesforce を
    import しない作りなので、それを直接確かめる。
    """
    # 資格情報 0 件状態を再現。`list_names` を空リスト関数で差し替える
    monkeypatch.setattr(
        "comken.toolbox.credentials.list_names",
        lambda *args, **kwargs: [],
    )
    # Salesforce 関連のモジュールを一旦取り除く（テスト後に復元）
    saved_requests = sys.modules.pop("requests", None)
    saved_salesforce = sys.modules.pop("comken.toolbox.salesforce.client", None)
    saved_sites = sys.modules.pop("comken.toolbox.salesforce.sites", None)
    saved_sandbox = sys.modules.pop("comken.toolbox.salesforce.sites.sandbox", None)
    try:
        # cli 内部の遅延 import が走っても、list_names が空なので salesforce は import されない
        from comken.core.doctor.cli import _resolve_salesforce_deps

        list_names_fn, sandbox_cls = _resolve_salesforce_deps()
        assert sandbox_cls is None  # list_names が空なら salesforce を import しない
        assert "comken.toolbox.salesforce.client" not in sys.modules
        assert "requests" not in sys.modules

        # runner の純粋関数も直接確かめる（資格情報ゼロ + sandbox_cls=None）
        from comken.core.doctor.runner import check_salesforce

        result = check_salesforce(list_names_fn, sandbox_cls)
        assert result.status == "skip"
    finally:
        if saved_requests is not None:
            sys.modules["requests"] = saved_requests
        if saved_salesforce is not None:
            sys.modules["comken.toolbox.salesforce.client"] = saved_salesforce
        if saved_sites is not None:
            sys.modules["comken.toolbox.salesforce.sites"] = saved_sites
        if saved_sandbox is not None:
            sys.modules["comken.toolbox.salesforce.sites.sandbox"] = saved_sandbox


def test_does_not_load_requests_for_skipped_salesforce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Salesforce を skip するときに ``requests`` を import しない（BO 環境対応）。

    認証情報が無いなら Salesforce まで進まず SKIP で返るのが正しい。
    Salesforce の client.py は冒頭で ``import requests`` するため、ここで
    import されたら BO 環境（``requests`` が入っていない）で ``doctor`` が
    落ちることになる。

    cli.py の `_resolve_salesforce_deps()` は資格情報が空なら Salesforce を
    import しない作りなので、それを直接確かめる。
    """
    # 資格情報 0 件状態を再現。`list_names` を空リスト関数で差し替える
    monkeypatch.setattr(
        "comken.toolbox.credentials.list_names",
        lambda *args, **kwargs: [],
    )
    # Salesforce 関連のモジュールを一旦取り除く（テスト後に復元）
    saved_requests = sys.modules.pop("requests", None)
    saved_salesforce = sys.modules.pop("comken.toolbox.salesforce.client", None)
    saved_sites = sys.modules.pop("comken.toolbox.salesforce.sites", None)
    saved_sandbox = sys.modules.pop("comken.toolbox.salesforce.sites.sandbox", None)
    try:
        # cli 内部の遅延 import が走っても、list_names が空なので salesforce は import されない
        from comken.core.doctor.cli import _resolve_salesforce_deps

        list_names_fn, names, sandbox_cls = _resolve_salesforce_deps()
        assert names == []
        assert sandbox_cls is None  # list_names が空なら salesforce を import しない
        assert "comken.toolbox.salesforce.client" not in sys.modules
        assert "requests" not in sys.modules

        # runner の純粋関数も直接確かめる（資格情報ゼロ + sandbox_cls=None）
        from comken.core.doctor.runner import check_salesforce

        result = check_salesforce(names, sandbox_cls)
        assert result.status == "skip"
    finally:
        if saved_requests is not None:
            sys.modules["requests"] = saved_requests
        if saved_salesforce is not None:
            sys.modules["comken.toolbox.salesforce.client"] = saved_salesforce
        if saved_sites is not None:
            sys.modules["comken.toolbox.salesforce.sites"] = saved_sites
        if saved_sandbox is not None:
            sys.modules["comken.toolbox.salesforce.sites.sandbox"] = saved_sandbox


# ── ファサード ────────────────────────────────────────────────────────────────


def test_doctor_is_exposed_from_comken_facade() -> None:
    """``comken.doctor`` / ``comken.DoctorResult`` が facade に追加されている。"""
    assert hasattr(comken, "doctor")
    assert hasattr(comken, "DoctorResult")
    assert "doctor" in comken.__all__
    assert "DoctorResult" in comken.__all__
    assert callable(comken.doctor)


# ── Salesforce クレデンシャル可視化 (Phase 4 改善) ──────────────────────


def _fake_sandbox() -> type:
    """テスト用の最小限の Sandbox クラス。"""

    class _FakeSandbox:
        CREDENTIAL_PREFIX = "sandbox"
        API_VERSION = "60.0"

        def __init__(self) -> None:
            pass

        def __enter__(self) -> _FakeSandbox:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def data_path(self, path: str) -> str:
            return path

        def request(self, *args: object, **kwargs: object) -> dict:
            return {}

    return _FakeSandbox


def test_salesforce_details_show_registered_keys() -> None:
    """3 つのキーが全部登録済なら details に「登録済」が並ぶ。"""
    from comken.core.doctor.runner import check_salesforce

    result = check_salesforce(
        names=["sandbox_client_id", "sandbox_client_secret", "sandbox_refresh_token"],
        sandbox_cls=_fake_sandbox(),
    )
    assert result.status == "ok"
    assert all("登録済" in line for line in result.details)
    assert any("sandbox_client_id: 登録済" in line for line in result.details)
    assert any("sandbox_client_secret: 登録済" in line for line in result.details)
    assert any("sandbox_refresh_token: 登録済" in line for line in result.details)


def test_salesforce_ng_when_refresh_token_missing() -> None:
    """refresh_token だけ未登録なら NG + details に「未登録」が見える。"""
    from comken.core.doctor.runner import check_salesforce

    result = check_salesforce(
        names=["sandbox_client_id", "sandbox_client_secret"],
        sandbox_cls=_fake_sandbox(),
    )
    assert result.status == "ng"
    assert "refresh_token" in result.message
    assert "初回認可" in result.message
    assert any("sandbox_refresh_token: 未登録" in line for line in result.details)
    assert any("sandbox_client_id: 登録済" in line for line in result.details)


def test_salesforce_skip_when_client_id_or_secret_missing() -> None:
    """client_id / client_secret が未登録なら SKIP (接続テスト不可)。"""
    from comken.core.doctor.runner import check_salesforce

    result = check_salesforce(
        names=["sandbox_refresh_token"],
        sandbox_cls=_fake_sandbox(),
    )
    assert result.status == "skip"
    assert "未登録" in result.message
    assert any("sandbox_client_id: 未登録" in line for line in result.details)
    assert any("sandbox_client_secret: 未登録" in line for line in result.details)


def test_salesforce_skip_when_no_credentials_and_no_sandbox_cls() -> None:
    """sandbox_cls も None なら SKIP (Salesforce モジュール不在)。"""
    from comken.core.doctor.runner import check_salesforce

    result = check_salesforce(names=[], sandbox_cls=None)
    assert result.status == "skip"
    assert result.details == ()
