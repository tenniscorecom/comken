"""確認コマンド（python -m comken sf）のテスト。"""

from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from comken.exceptions import CredentialNotFoundError, SalesforceAuthError
from comken.toolbox.salesforce.auth.oauth_refresh import AuthorizationRequest
from comken.toolbox.salesforce.cli import main
from comken.toolbox.salesforce.sites import SITES, Solution, SolutionSandbox


def _client(**kwargs) -> MagicMock:
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    for key, value in kwargs.items():
        setattr(client, key, value)
    return client


def _site_class(client) -> MagicMock:
    """site_for() が返す「組織クラス」の代わり。呼ぶと client を返す。"""
    return MagicMock(return_value=client)


class TestPrintShape:
    def test_hides_secret_values(self, capsys):
        """応答に含まれる秘密の値を画面へ出さない。

        ``sf app`` は v1.0.0 で削除済み。``_print_shape`` は
        ``sf rotate --stage-only`` の staged 作成応答で確認する
        （``--stage-only`` は staged POST までで止めるため、副作用は限定される）。
        """
        client = _client()
        client.request.side_effect = [
            ({"consumerId": "CID"}, {}),
            ({"id": "STG1", "consumerKey": "KEY-VALUE", "consumerSecret": "SECRET-VALUE"}, {}),
        ]
        with patch("comken.toolbox.salesforce.cli.site_for", return_value=_site_class(client)):
            main(
                [
                    "rotate",
                    "--domain",
                    "https://x.my.salesforce.com",
                    "--prefix",
                    "site_a",
                    "--app-id",
                    "1CE",
                    "--stage-only",
                ]
            )

        out = capsys.readouterr().out
        assert "SECRET-VALUE" not in out
        assert "KEY-VALUE" not in out
        assert "consumerSecret: ***" in out


class TestReport:
    def test_shows_row_count_and_columns_without_values(self, capsys):
        """既定では行数と列名だけを出し、中身は出さない。"""
        client = _client()
        client.report.get.return_value = [{"案件名": "極秘案件", "金額": "1000"}]
        with patch("comken.toolbox.salesforce.cli.site_for", return_value=_site_class(client)):
            code = main(
                [
                    "report",
                    "--domain",
                    "https://x.my.salesforce.com",
                    "--prefix",
                    "site_a",
                    "--report-id",
                    "00O",
                ]
            )

        out = capsys.readouterr().out
        assert code == 0
        assert "1 行" in out
        assert "案件名" in out
        assert "極秘案件" not in out

    def test_shows_values_when_rows_requested(self, capsys):
        """--rows を指定したときだけ中身を出す。"""
        client = _client()
        client.report.get.return_value = [{"案件名": "案件A"}]
        with patch("comken.toolbox.salesforce.cli.site_for", return_value=_site_class(client)):
            main(
                [
                    "report",
                    "--domain",
                    "https://x",
                    "--prefix",
                    "site_a",
                    "--report-id",
                    "00O",
                    "--rows",
                    "1",
                ]
            )

        assert "案件A" in capsys.readouterr().out

    def test_site_flag_picks_registered_org_without_domain(self):
        """``--site`` を指定すると ``site_for()`` を経由せず組織クラスを直接使う。"""
        client = _client()
        client.report.get.return_value = []
        # --site で渡した組織クラス（SolutionSandbox）が直接呼ばれる。
        # SITES はインポート時に固定されるため、``_resolve_site`` をモックして
        # 呼び出された側だけ差し替える
        with (
            patch(
                "comken.toolbox.salesforce.cli._resolve_site",
                return_value=MagicMock(return_value=client),
            ) as resolve,
            patch("comken.toolbox.salesforce.cli.site_for") as site_for_mock,
        ):
            code = main(["report", "--site", "2", "--report-id", "00O"])

        resolve.assert_called_once_with("2")
        site_for_mock.assert_not_called()
        assert code == 0


class TestRotate:
    def test_stops_before_switching_with_stage_only(self, capsys):
        """--stage-only では切り替えの PATCH を送らない。"""
        client = _client()
        client.request.side_effect = [
            ({"consumerId": "CID"}, {}),
            ({"id": "STG1", "consumerKey": "K", "consumerSecret": "S"}, {}),
        ]
        with patch("comken.toolbox.salesforce.cli.site_for", return_value=_site_class(client)):
            main(
                [
                    "rotate",
                    "--domain",
                    "https://x",
                    "--prefix",
                    "site_a",
                    "--app-id",
                    "1CE",
                    "--stage-only",
                ]
            )

        methods = [call.args[0] for call in client.request.call_args_list]
        assert methods == ["GET", "POST"]
        assert "まだ切り替えていません" in capsys.readouterr().out

    def test_aborts_when_not_confirmed(self, capsys):
        """確認に y 以外を入れたら何もしない。"""
        with (
            patch("comken.toolbox.salesforce.cli.site_for") as site_for_mock,
            patch("builtins.input", return_value="n"),
        ):
            main(["rotate", "--domain", "https://x", "--prefix", "site_a", "--app-id", "1CE"])

        site_for_mock.assert_not_called()
        assert "中止しました" in capsys.readouterr().out

    def test_site_flag_picks_registered_org_without_domain(self):
        """``--site`` を指定すると ``site_for()`` を経由せず組織クラスを直接使う。"""
        client = _client()
        client.request.side_effect = [
            ({"consumerId": "CID"}, {}),
            ({"id": "STG1", "consumerKey": "K", "consumerSecret": "S"}, {}),
        ]
        # SITES はインポート時に固定されるため、``_resolve_site`` をモックして
        # 呼び出された側だけ差し替える
        with (
            patch(
                "comken.toolbox.salesforce.cli._resolve_site",
                return_value=MagicMock(return_value=client),
            ) as resolve,
            patch("comken.toolbox.salesforce.cli.site_for") as site_for_mock,
        ):
            code = main(
                [
                    "rotate",
                    "--site",
                    "2",
                    "--app-id",
                    "1CE",
                    "--stage-only",
                ]
            )

        resolve.assert_called_once_with("2")
        site_for_mock.assert_not_called()
        assert code == 0


class TestErrors:
    def test_returns_1_with_message(self, capsys):
        """接続に失敗したら、traceback ではなくメッセージを出して 1 を返す。"""
        with patch(
            "comken.toolbox.salesforce.cli.site_for",
            return_value=MagicMock(side_effect=SalesforceAuthError(401, "invalid_client")),
        ):
            code = main(
                ["report", "--domain", "https://x", "--prefix", "site_a", "--report-id", "00O"]
            )

        assert code == 1
        assert "エラー:" in capsys.readouterr().err


class TestDefaultOrg:
    def test_omits_domain_to_use_solution_sandbox(self):
        """``--domain`` を省略したら安全側の ``SolutionSandbox`` が既定で選ばれる。"""
        client = _client()
        client.report.get.return_value = []
        with patch(
            "comken.toolbox.salesforce.cli.SolutionSandbox", return_value=client
        ) as solution_sandbox_mock:
            code = main(["report", "--prefix", "site_a", "--report-id", "00O"])

        solution_sandbox_mock.assert_called_once_with(prefix="site_a")
        assert code == 0


class TestSetup:
    """`sf setup` — 組織を選んで Refresh Token Flow の初回認可を行う。"""

    def _credentials_mock(self):
        """`Credentials(prefix)` の戻り値を差し替えるための MagicMock。"""
        credentials = MagicMock()
        credentials.api_client_id = "CID"
        credentials.api_client_secret = "CSECRET"
        return credentials

    def test_selects_site_by_number(self, capsys):
        """`2` を入れたら SITES の2番目（SolutionSandbox）が選ばれる。

        認可 URL と exchange の domain_url が SolutionSandbox のものになることで確認する。
        """
        with (
            patch(
                "comken.toolbox.salesforce.cli.Credentials", return_value=self._credentials_mock()
            ),
            patch(
                "comken.toolbox.salesforce.cli.RefreshTokenOAuth.authorization_url",
                return_value=AuthorizationRequest(
                    "https://example.test/authorize", "STATE", "VERIFIER"
                ),
            ),
            patch("comken.toolbox.salesforce.cli.RefreshTokenOAuth.exchange_code") as exchange,
            # 番号選択 → 確認プロンプト (`y`) → リダイレクトURLの貼り付け
            patch(
                "builtins.input",
                side_effect=["2", "y", "http://localhost:8080/callback?code=AUTH-CODE&state=STATE"],
            ),
        ):
            code = main(["setup"])

        assert code == 0
        # SITES は Solution / SolutionSandbox の順なので、2番目 = SolutionSandbox
        assert SolutionSandbox in SITES
        assert SITES.index(SolutionSandbox) == 1
        # exchange_code の domain_url が SolutionSandbox のドメインであることを確認
        exchange_mock = cast(MagicMock, exchange)
        exchange_call = exchange_mock.call_args
        assert exchange_call.args[4] == SolutionSandbox.DOMAIN_URL

    def test_selects_site_by_name_case_insensitive(self, capsys):
        """`solution`（小文字）を入れたら Solution（小文字を許容）が選ばれる。"""
        with (
            patch(
                "comken.toolbox.salesforce.cli.Credentials", return_value=self._credentials_mock()
            ),
            patch(
                "comken.toolbox.salesforce.cli.RefreshTokenOAuth.authorization_url",
                return_value=AuthorizationRequest(
                    "https://example.test/authorize", "STATE", "VERIFIER"
                ),
            ),
            patch("comken.toolbox.salesforce.cli.RefreshTokenOAuth.exchange_code") as exchange,
            patch(
                "builtins.input",
                side_effect=[
                    "solution",
                    "y",
                    "http://localhost:8080/callback?code=AUTH-CODE&state=STATE",
                ],
            ),
        ):
            code = main(["setup"])

        assert code == 0
        exchange_mock = cast(MagicMock, exchange)
        exchange_call = exchange_mock.call_args
        assert exchange_call.args[4] == Solution.DOMAIN_URL
        assert exchange_call.kwargs["prefix"] == Solution.CREDENTIAL_PREFIX

    @pytest.mark.parametrize("bad_answer", ["99", "nonexistent", ""])
    def test_invalid_answer_exits_with_error(self, capsys, bad_answer):
        """範囲外の番号・存在しない名前を入れると、終了コード1でstderr にメッセージ。"""
        with patch("builtins.input", return_value=bad_answer):
            code = main(["setup"])

        captured = capsys.readouterr()
        assert code == 1
        assert "エラー:" in captured.err
        # 登録済みの組織名は候補として表示される
        for site_class in SITES:
            assert site_class.__name__ in captured.err

    def test_full_flow_shows_url_and_saves_refresh_token(self, capsys):
        """一連の流れ — URL 表示・code 受け渡し・完了メッセージを確認。"""
        credentials = self._credentials_mock()
        with (
            patch("comken.toolbox.salesforce.cli.Credentials", return_value=credentials),
            patch(
                "comken.toolbox.salesforce.cli.RefreshTokenOAuth.authorization_url",
                return_value=AuthorizationRequest(
                    "https://example.test/authorize?client_id=CID", "STATE", "VERIFIER"
                ),
            ),
            patch("comken.toolbox.salesforce.cli.RefreshTokenOAuth.exchange_code") as exchange,
            patch(
                "builtins.input",
                side_effect=[
                    "1",
                    "y",
                    "http://localhost:8080/callback?code=AUTH-CODE-VALUE&state=STATE",
                ],
            ),
        ):
            code = main(["setup"])

        assert code == 0
        out = capsys.readouterr().out
        # 認可 URL が標準出力に出ている
        assert "https://example.test/authorize?client_id=CID" in out
        exchange_mock = cast(MagicMock, exchange)
        # exchange_code に貼り付けた code がそのまま渡されている
        assert exchange_mock.call_args.args[2] == "AUTH-CODE-VALUE"
        # prefix は組織クラスの CREDENTIAL_PREFIX
        assert exchange_mock.call_args.kwargs["prefix"] == SITES[0].CREDENTIAL_PREFIX
        # 完了メッセージ
        assert "refresh_token を DPAPI に保存しました" in out
        # --site に渡す番号を案内する行も出る
        assert "--site 1 --report-id" in out

    def test_site_flag_skips_interactive_selection_by_number(self, capsys):
        """``--site 2`` を指定すると対話選択をスキップして SolutionSandbox が選ばれる。

        input は確認プロンプト・URL貼り付けの2回だけになる。
        """
        with (
            patch(
                "comken.toolbox.salesforce.cli.Credentials", return_value=self._credentials_mock()
            ),
            patch(
                "comken.toolbox.salesforce.cli.RefreshTokenOAuth.authorization_url",
                return_value=AuthorizationRequest(
                    "https://example.test/authorize", "STATE", "VERIFIER"
                ),
            ),
            patch("comken.toolbox.salesforce.cli.RefreshTokenOAuth.exchange_code") as exchange,
            patch(
                "builtins.input",
                side_effect=["y", "http://localhost:8080/callback?code=AUTH-CODE&state=STATE"],
            ),
        ):
            code = main(["setup", "--site", "2"])

        assert code == 0
        exchange_mock = cast(MagicMock, exchange)
        # SolutionSandbox が選ばれたことを domain_url / prefix で確認
        assert exchange_mock.call_args.args[4] == SolutionSandbox.DOMAIN_URL
        assert exchange_mock.call_args.kwargs["prefix"] == SolutionSandbox.CREDENTIAL_PREFIX
        # 選択プロンプトは出ていない
        out = capsys.readouterr().out
        assert "番号または組織名を入力してください" not in out

    def test_site_flag_accepts_lowercase_name(self, capsys):
        """``--site solution``（小文字）でも Solution クラスが引ける。"""
        with (
            patch(
                "comken.toolbox.salesforce.cli.Credentials", return_value=self._credentials_mock()
            ),
            patch(
                "comken.toolbox.salesforce.cli.RefreshTokenOAuth.authorization_url",
                return_value=AuthorizationRequest(
                    "https://example.test/authorize", "STATE", "VERIFIER"
                ),
            ),
            patch("comken.toolbox.salesforce.cli.RefreshTokenOAuth.exchange_code") as exchange,
            patch(
                "builtins.input",
                side_effect=["y", "http://localhost:8080/callback?code=AUTH-CODE&state=STATE"],
            ),
        ):
            code = main(["setup", "--site", "solution"])

        assert code == 0
        exchange_mock = cast(MagicMock, exchange)
        assert exchange_mock.call_args.args[4] == Solution.DOMAIN_URL

    def test_state_mismatch_raises(self, capsys):
        """貼り付けたURLのstateが authorization_url のものと違えば、CSRF検証として弾く。"""
        with (
            patch(
                "comken.toolbox.salesforce.cli.Credentials", return_value=self._credentials_mock()
            ),
            patch(
                "comken.toolbox.salesforce.cli.RefreshTokenOAuth.authorization_url",
                return_value=AuthorizationRequest(
                    "https://example.test/authorize", "STATE", "VERIFIER"
                ),
            ),
            patch("comken.toolbox.salesforce.cli.RefreshTokenOAuth.exchange_code") as exchange,
            patch(
                "builtins.input",
                side_effect=[
                    "1",
                    "y",
                    "http://localhost:8080/callback?code=AUTH-CODE&state=WRONG-STATE",
                ],
            ),
        ):
            code = main(["setup"])

        assert code == 1
        assert "state が一致しません" in capsys.readouterr().err
        cast(MagicMock, exchange).assert_not_called()

    def test_manual_paste_retries_on_unparsable_url(self, capsys):
        """貼り付けたURLにcodeが含まれなければ、もう一度貼り付けさせる。"""
        with (
            patch(
                "comken.toolbox.salesforce.cli.Credentials", return_value=self._credentials_mock()
            ),
            patch(
                "comken.toolbox.salesforce.cli.RefreshTokenOAuth.authorization_url",
                return_value=AuthorizationRequest(
                    "https://example.test/authorize", "STATE", "VERIFIER"
                ),
            ),
            patch("comken.toolbox.salesforce.cli.RefreshTokenOAuth.exchange_code") as exchange,
            patch(
                "builtins.input",
                side_effect=[
                    "1",
                    "y",
                    "http://localhost:8080/callback?error=access_denied",  # codeが無い
                    "http://localhost:8080/callback?code=RETRY-CODE&state=STATE",
                ],
            ),
        ):
            code = main(["setup"])

        assert code == 0
        out = capsys.readouterr().out
        assert "読み取れませんでした" in out
        exchange_mock = cast(MagicMock, exchange)
        assert exchange_mock.call_args.args[2] == "RETRY-CODE"

    def test_aborts_when_confirmation_is_rejected(self, capsys):
        """確認プロンプトで ``n`` と答えると認可フローを始めずに終わる。"""
        with (
            patch(
                "comken.toolbox.salesforce.cli.Credentials", return_value=self._credentials_mock()
            ),
            patch(
                "comken.toolbox.salesforce.cli.RefreshTokenOAuth.authorization_url"
            ) as authorization_url,
            patch("comken.toolbox.salesforce.cli.RefreshTokenOAuth.exchange_code") as exchange,
            patch("builtins.input", side_effect=["1", "n"]),
        ):
            code = main(["setup"])

        assert code == 0
        out = capsys.readouterr().out
        assert "中止しました" in out
        authorization_url.assert_not_called()
        exchange.assert_not_called()

    def test_warns_about_missing_credentials_and_guides_to_cred_gui(self, capsys):
        """``Credentials`` が ``CredentialNotFoundError`` を出すとき、
        ``cred gui`` への案内を出し、main() の戻り値は 1 で stderr にもメッセージが出る。
        """
        with (
            patch(
                "comken.toolbox.salesforce.cli.Credentials",
                side_effect=CredentialNotFoundError(
                    f"{Solution.CREDENTIAL_PREFIX}.api_client_id", []
                ),
            ),
            patch(
                "comken.toolbox.salesforce.cli.RefreshTokenOAuth.authorization_url"
            ) as authorization_url,
            patch("builtins.input", side_effect=["1", "y"]),
        ):
            code = main(["setup"])

        captured = capsys.readouterr()
        authorization_url.assert_not_called()
        assert code == 1
        assert "未登録" in captured.out
        assert "python -m comken cred gui" in captured.out
        assert "エラー:" in captured.err


class TestSites:
    """`python -m comken sf sites` で登録済み組織を一覧表示する。"""

    def test_lists_each_site_with_name_and_settings(self, capsys):
        """`sf sites` を実行すると ``SITES`` の各組織の
        クラス名・表示名・DOMAIN_URL・CREDENTIAL_PREFIX が標準出力に出る。
        """
        code = main(["sites"])

        out = capsys.readouterr().out
        assert code == 0
        # 番号付きのサマリ
        assert "登録済みの組織:" in out
        for index, site_class in enumerate(SITES, start=1):
            assert f"{index}. {site_class.__name__}" in out
        # 詳細（DOMAIN_URL / CREDENTIAL_PREFIX）
        for site_class in SITES:
            assert site_class.__name__ in out
            assert site_class.DOMAIN_URL in out
            assert site_class.CREDENTIAL_PREFIX in out
            # display_name() の値も出る
            assert site_class.display_name() in out
