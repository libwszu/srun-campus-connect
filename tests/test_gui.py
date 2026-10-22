from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from campus_connect.config import ConfigStore, CampusProfile, Settings
from campus_connect.gui import Application


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = ConfigStore(self.folder.name)
        try:
            self.app = Application(store=self.store, language="en")
            self.app.withdraw()
        except Exception:
            self.folder.cleanup()
            raise

    def tearDown(self):
        self.app.stop_event.set()
        self.app.after_cancel(self.app.poll_id)
        self.app.update_idletasks()
        self.app.destroy()
        self.folder.cleanup()

    def test_live_language_switch_updates_widgets_and_keeps_unsaved_account(self):
        self.app.username_var.set("synthetic-account")
        self.app.password_var.set("synthetic-password")
        self.app.language_var.set("简体中文")
        self.app._change_language()
        self.assertIn("校园网助手", self.app.title())
        self.assertEqual(self.app.start_button.cget("text"), "启动监控")
        self.assertEqual(self.store.load().language, "zh-CN")
        self.assertEqual(self.app.username_var.get(), "synthetic-account")
        self.assertEqual(self.app.password_var.get(), "synthetic-password")
        self.app.language_var.set("English")
        self.app._change_language()
        self.assertEqual(self.app.start_button.cget("text"), "Start monitoring")

    def test_save_and_export_do_not_export_account_credentials(self):
        self.app._fill(Settings(profile=CampusProfile(base_url="https://campus.example.org"), username="synthetic-account", password="synthetic-password"))
        self.assertIsNotNone(self.app._save(notify=False))
        target = Path(self.folder.name) / "profile.json"
        with patch("campus_connect.gui.filedialog.asksaveasfilename", return_value=str(target)), patch("campus_connect.gui.messagebox.showinfo"):
            self.app._export_profile()
        self.assertNotIn("synthetic-password", target.read_text())
        self.assertNotIn('"username"', target.read_text())
        self.assertEqual(self.store.load().password, "synthetic-password")

    def test_missing_server_or_credentials_blocks_requests(self):
        with patch("campus_connect.gui.messagebox.showerror") as error, patch("campus_connect.gui.SrunClient") as client:
            self.app._operation("login")
            client.assert_not_called()
            error.assert_called_once()
        self.app._fill(Settings(profile=CampusProfile(base_url="https://campus.example.org")))
        with patch("campus_connect.gui.messagebox.showerror"), patch("campus_connect.gui.SrunClient") as client:
            self.app._operation("login")
            client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
