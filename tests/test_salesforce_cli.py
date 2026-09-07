"""確認コマンド（python -m comken sf）のテスト。"""

from unittest.mock import MagicMock, patch

from comken.exceptions import SalesforceAuthError
from comken.toolbox.salesforce.cli import main


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
