import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from campus_connect.client import SrunClient, SrunError, check_connectivity, parse_response
from campus_connect.config import CampusProfile, ConfigStore, ProfileError, Settings, export_profile, load_profile
from campus_connect.i18n import Translator, ZH
from campus_connect.monitor import run_monitor


def response(data, status=200):
    text = "srunCallback(" + json.dumps(data) + ");"
    return SimpleNamespace(status_code=status, text=text, content=text.encode())


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = CampusProfile(base_url="https://campus.example.org", ac_id="9", username_suffix="@campus")

    def test_profile_accepts_custom_values_and_preserves_explicit_account_domain(self):
        self.profile.validate()
        self.assertEqual(self.profile.account("student"), "student@campus")
        self.assertEqual(self.profile.account("student@isp"), "student@isp")

    def test_unsafe_or_unsupported_profile_settings_are_rejected(self):
        invalid = [
            {"base_url": "file:///etc/passwd"}, {"base_url": "https://account:secret@example.org"},
            {"base_url": "https://example.org/?ac_id=1"}, {"portal_path": "//other.example.org/login"},
            {"ac_id": "not-a-number"}, {"enc_ver": "unsupported"}, {"base64_alphabet": "A" * 64},
            {"client_ip": "invalid-ip"}, {"probe_status": 302}, {"probe_text": "   "},
            {"base_url": "https://["}, {"base_url": "https://example.org:70000"}, {"portal_path": "//["},
        ]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ProfileError):
                CampusProfile.from_dict({**self.profile.to_dict(), **values}).validate()

    def test_profile_export_import_never_includes_account_fields(self):
        settings = Settings(profile=self.profile, username="test-account", password="synthetic-password")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "campus.json"
            export_profile(path, settings.profile)
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("synthetic-password", content)
            self.assertNotIn('"username"', content)
            self.assertEqual(load_profile(path), self.profile)
        with self.assertRaises(ProfileError):
            CampusProfile.from_dict({**self.profile.to_dict(), "password": "synthetic-password"})

    def test_settings_roundtrip_preserves_credentials_and_language(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ConfigStore(folder)
            settings = Settings(profile=self.profile, username="test-account", password="synthetic-password", language="zh-CN")
            store.save(settings)
            self.assertEqual(store.load(), settings)
            self.assertFalse(store.path.with_suffix(".json.tmp").exists())
            store.path.write_text("invalid-json", encoding="utf-8")
            with self.assertRaises(ProfileError):
                store.load()
            self.assertEqual(store.path.read_text(), "invalid-json")

    def test_settings_bounds_and_wrong_account_type(self):
        settings = Settings.from_dict({"check_interval": 0, "reconnect_retries": 500, "retry_delay": -1})
        self.assertEqual((settings.check_interval, settings.reconnect_retries, settings.retry_delay), (10, 10, 1))
        with self.assertRaises(ProfileError):
            Settings.from_dict({"password": None})


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.profile = CampusProfile(base_url="http://net.szu.edu.cn", ac_id="12", username_suffix="@hlw")
        self.session = Mock()

    def test_payload_matches_the_previous_szu_implementation(self):
        client = SrunClient(self.profile, "test-account", "synthetic-test-password", session=self.session)
        client.token = "0123456789abcdef"
        client.ip = "192.0.2.1"
        with patch("campus_connect.client.time.time", return_value=1234567890):
            payload = client.build_login_params()
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        self.assertEqual(digest, "9164a1cabc312d81f3c603c51faa8d92be9f9ba0643cc211e19dde72bf5cb9d5")

    def test_custom_server_paths_domain_and_protocol_values_are_used(self):
        profile = CampusProfile(base_url="https://campus.example.org/proxy", ac_id="7", username_suffix="@isp", n="201", type="2", portal_path="/auth/login", challenge_path="/auth/challenge")
        self.session.get.side_effect = [response({"challenge": "0123456789abcdef", "client_ip": "192.0.2.55"}), response({"res": "ok"})]
        client = SrunClient(profile, "test-account", "synthetic-password", session=self.session)
        with patch("campus_connect.client.local_ip", return_value="192.0.2.1"):
            client.login()
        first, second = self.session.get.call_args_list
        self.assertEqual(first.args[0], "https://campus.example.org/proxy/auth/challenge")
        self.assertEqual(second.args[0], "https://campus.example.org/proxy/auth/login")
        params = second.kwargs["params"]
        self.assertEqual((params["username"], params["ac_id"], params["n"], params["type"], params["ip"]), ("test-account@isp", "7", "201", "2", "192.0.2.55"))
        self.assertFalse(self.session.trust_env)
        self.assertFalse(second.kwargs["allow_redirects"])

    def test_server_errors_and_connection_errors_do_not_echo_credentials(self):
        client = SrunClient(self.profile, "test-account", "synthetic-password", session=self.session)
        self.session.get.side_effect = requests.ConnectionError("synthetic-password")
        with patch("campus_connect.client.local_ip", return_value="192.0.2.1"), self.assertRaises(SrunError) as result:
            client.login()
        self.assertNotIn("synthetic-password", str(result.exception))
        self.session.get.side_effect = [response({"challenge": "token"}), response({"res": "fail", "error_msg": "synthetic-password"})]
        with patch("campus_connect.client.local_ip", return_value="192.0.2.1"), self.assertRaises(SrunError) as result:
            client.login()
        self.assertNotIn("synthetic-password", str(result.exception))

    def test_plain_json_jsonp_and_invalid_payload(self):
        self.assertEqual(parse_response('{"res":"ok"}')["res"], "ok")
        self.assertEqual(parse_response('cb({"res":"ok"});')["res"], "ok")
        for text in ("<html>login</html>", "callback([])", "callback(__import__('os'))"):
            with self.assertRaises(SrunError):
                parse_response(text)

    def test_logout_sends_only_session_identity_fields(self):
        self.session.get.return_value = response({"res": "ok"})
        client = SrunClient(self.profile, "test-account", "synthetic-password", session=self.session)
        client.ip = "192.0.2.1"
        client.logout()
        params = self.session.get.call_args.kwargs["params"]
        self.assertEqual(set(params), {"callback", "action", "username", "ip", "ac_id"})
        self.assertNotIn("synthetic-password", str(params))

    def test_explicit_failure_cannot_be_overridden_by_a_secondary_ok_field(self):
        self.session.get.side_effect = [response({"challenge": "token"}), response({"res": "fail", "error": "ok"})]
        client = SrunClient(self.profile, "test-account", "synthetic-password", session=self.session)
        with patch("campus_connect.client.local_ip", return_value="192.0.2.1"), self.assertRaises(SrunError):
            client.login()


class ConnectivityAndMonitorTests(unittest.TestCase):
    def test_captive_portal_content_and_redirects_are_not_counted_as_online(self):
        profile = CampusProfile()
        session = Mock()
        for status, text, expected in ((200, "<html>sign in</html>", False), (302, "Microsoft Connect Test", False), (200, "Microsoft Connect Test\n", True)):
            session.get.return_value = SimpleNamespace(status_code=status, text=text, content=text.encode())
            self.assertEqual(check_connectivity(profile, session), expected)
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])

    def test_http_204_probe_requires_empty_response(self):
        profile = CampusProfile(probe_status=204, probe_text="")
        session = Mock()
        session.get.return_value = SimpleNamespace(status_code=204, text="", content=b"")
        self.assertTrue(check_connectivity(profile, session))
        session.get.return_value.content = b"unexpected"
        self.assertFalse(check_connectivity(profile, session))

    def test_auto_login_waits_for_two_failures_and_stops_interruptibly(self):
        settings = Settings(username="test-account", password="synthetic-password")
        stop, emit, client = Mock(), Mock(), Mock()
        stop.is_set.return_value = False
        stop.wait.side_effect = [False, False, True]
        with patch("campus_connect.monitor.check_connectivity", side_effect=[False, False, True]), patch("campus_connect.monitor.SrunClient", return_value=client):
            run_monitor(settings, stop, emit)
        client.login.assert_called_once()
        client.close.assert_called_once()
        self.assertEqual(emit.call_args.args[0], "stopped")

    def test_missing_credentials_never_trigger_authentication(self):
        stop, emit = Mock(), Mock()
        stop.is_set.return_value = False
        stop.wait.side_effect = [False, True]
        with patch("campus_connect.monitor.check_connectivity", return_value=False), patch("campus_connect.monitor.SrunClient") as client:
            run_monitor(Settings(), stop, emit)
        client.assert_not_called()

    def test_translations_preserve_fields_and_do_not_reformat_values(self):
        import string
        formatter = string.Formatter()
        for english, chinese in ZH.items():
            fields = lambda text: sorted(field for _, field, _, _ in formatter.parse(text) if field is not None)
            self.assertEqual(fields(english), fields(chinese))
        self.assertEqual(Translator("zh-CN")("Status"), "状态")
        self.assertEqual(Translator("en")("Status"), "Status")


if __name__ == "__main__":
    unittest.main()
