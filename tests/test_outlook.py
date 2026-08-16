"""Classic Outlook の COM 配線をモックで検証する。"""

import datetime
import inspect
from unittest.mock import MagicMock, patch

import pytest

from comken import dry_run
from comken.exceptions import (
    ClassicOutlookNotAvailableError,
    OutlookAttachmentNotFoundError,
    OutlookFolderNotFoundError,
)
from comken.toolbox.outlook import MailMessage, Outlook


def _outlook():
    application = MagicMock()
    namespace = application.GetNamespace.return_value
    inbox = namespace.GetDefaultFolder.return_value
    restricted_items = inbox.Items.Restrict.return_value
    restricted_items.__iter__.return_value = iter(())
    with patch("comken.toolbox.outlook.handler.win32com.client.Dispatch", return_value=application):
        outlook = Outlook()
    return outlook, application, inbox


class TestOutlook:
    def test_uses_dispatch_and_does_not_quit(self):
        application = MagicMock()
        with (
            patch(
                "comken.toolbox.outlook.handler.win32com.client.Dispatch", return_value=application
            ) as dispatch,
            Outlook(),
        ):
            pass
        dispatch.assert_called_once_with("Outlook.Application")
        application.Quit.assert_not_called()

    def test_missing_classic_outlook_has_guidance(self):
        with (
            patch(
                "comken.toolbox.outlook.handler.win32com.client.Dispatch",
                side_effect=OSError("COM error"),
            ),
            pytest.raises(
                ClassicOutlookNotAvailableError,
                match=r"Classic.*新しい Outlook.*管理者",
            ),
        ):
            Outlook()

    def test_messages_is_generator_and_restricts_and_sorts(self):
        outlook, _, inbox = _outlook()
        messages = outlook.read_messages(subject_contains="日次", days=7)
        assert inspect.isgenerator(messages)
        assert list(messages) == []
        condition = inbox.Items.Restrict.call_args.args[0]
        assert "ReceivedTime" in condition
        assert "Subject" in condition
        assert "日次" in condition
        inbox.Items.Restrict.return_value.Sort.assert_called_once_with("[ReceivedTime]", True)

    def test_reading_does_not_change_unread(self):
        outlook, _, inbox = _outlook()
        item = MagicMock()
        item.Subject = "件名"
        item.SenderName = "差出人"
        item.SenderEmailType = "SMTP"
        item.SenderEmailAddress = "sender@example.com"
        item.ReceivedTime = datetime.datetime(2026, 7, 29, 10, 0, tzinfo=datetime.UTC)
        item.Body = "本文"
        item.Attachments.Count = 0
        inbox.Items.Restrict.return_value.__iter__.return_value = iter((item,))
        assert len(list(outlook.read_messages())) == 1
        assert "UnRead" not in item.__dict__

    def test_missing_folder_lists_existing_names(self):
        outlook, _, inbox = _outlook()
        inbox.Folders.Count = 2
        inbox.Folders.Item.side_effect = [
            MagicMock(Name="処理済み"),
            MagicMock(Name="共有"),
        ]
        with pytest.raises(OutlookFolderNotFoundError, match=r"処理済み.*共有"):
            list(outlook.read_messages(folder="なし"))

    def test_save_draft_saves_but_does_not_send(self, tmp_path):
        outlook, application, _ = _outlook()
        attachment = tmp_path / "report.csv"
        attachment.touch()
        draft = application.CreateItem.return_value
        outlook.save_draft(
            ["a@example.com", "b@example.com"],
            "件名",
            "本文",
            [attachment],
            cc="c@example.com",
        )
        draft.Save.assert_called_once()
        draft.Send.assert_not_called()
        draft.Attachments.Add.assert_called_once_with(str(attachment.resolve()))

    def test_missing_attachment_does_not_create_draft(self, tmp_path):
        outlook, application, _ = _outlook()
        with pytest.raises(OutlookAttachmentNotFoundError):
            outlook.save_draft("a@example.com", "件名", "本文", [tmp_path / "missing.csv"])
        application.CreateItem.assert_not_called()

    def test_dry_run_does_not_create_draft(self):
        outlook, application, _ = _outlook()
        with dry_run():
            outlook.save_draft("a@example.com", "件名", "本文")
        application.CreateItem.assert_not_called()

    def test_received_at_has_timezone(self):
        outlook, _, inbox = _outlook()
        item = MagicMock(
            Subject="件名",
            SenderName="差出人",
            SenderEmailType="SMTP",
            SenderEmailAddress="sender@example.com",
            ReceivedTime=datetime.datetime(2026, 7, 29, 10, 0, tzinfo=datetime.UTC),
            Body="本文",
        )
        item.Attachments.Count = 1
        inbox.Items.Restrict.return_value.__iter__.return_value = iter((item,))
        message = next(outlook.read_messages())
        assert isinstance(message, MailMessage)
        assert message.received_at.tzinfo is not None


class TestReceivedAttachmentsAndLinksAreNotReachable:
    """受信メールの添付とリンクへ、プログラムから到達できないことを固定する。

    社内ルールで受信メールの添付とリンクを開くことは禁止されている（仕様書 4.17）。
    プログラムから開けてしまうと、人が守っているルールを自動処理が迂回することになり、
    しかも自動なので誰も気づかない。

    禁止を文章だけに置くと、必要になった誰かが善意で足してしまう。
    ここで「生えていないこと」を検証して、足された瞬間に落とす。
    """

    # 受信物を取り出す・開く意図の名前。save_draft の attachments 引数（送る側）は対象外
    FORBIDDEN = (
        "save_attachment",
        "save_attachments",
        "download_attachment",
        "download_attachments",
        "extract_attachment",
        "extract_attachments",
        "open_attachment",
        "open_attachments",
        "get_attachment",
        "get_attachments",
        "open_link",
        "open_links",
        "open_url",
    )

    def test_outlook_has_no_attachment_or_link_opening_methods(self):
        """Outlook に受信添付・リンクを開くメソッドを足していない。"""
        for name in self.FORBIDDEN:
            assert not hasattr(Outlook, name), (
                f"Outlook.{name}() は実装しない（仕様書 4.17）。"
                "添付の中身が要るなら、共有サーバー経由での受け渡しを送信元へ依頼する"
            )

    def test_mail_message_exposes_only_the_presence_of_attachments(self):
        """MailMessage は添付の有無だけを持ち、添付そのものへは到達させない。"""
        fields = set(MailMessage.__dataclass_fields__)

        assert "has_attachments" in fields
        assert not [f for f in fields if f != "has_attachments" and "attach" in f], (
            "MailMessage に添付そのものを持たせない（仕様書 4.17）。"
            f"現在のフィールド: {sorted(fields)}"
        )

    def test_mail_message_has_no_attachment_accessor(self):
        """MailMessage 側にも添付を取り出すメソッドを足していない。"""
        for name in self.FORBIDDEN:
            assert not hasattr(MailMessage, name), (
                f"MailMessage.{name}() は実装しない（仕様書 4.17）"
            )
