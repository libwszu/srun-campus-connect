"""Standard SRUN BX1 challenge/sign-in/sign-out transport."""

import ipaddress
import json
import socket
import time
from urllib.parse import urlsplit

import requests

from .crypto import hmac_md5, sha1_hash, trans_base64, xxtea_encrypt


class SrunError(RuntimeError):
    pass


def parse_response(text):
    text = text.strip()
    try:
        if not text.startswith("{"):
            text = text[text.index("(") + 1:text.rindex(")")]
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError
        return data
    except (ValueError, TypeError):
        raise SrunError("The server did not return a valid SRUN JSON response.") from None


def local_ip(profile):
    if profile.client_ip:
        return profile.client_ip
    parsed = urlsplit(profile.base_url.strip())
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.connect((parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)))
            return route.getsockname()[0]
    except OSError:
        return "0.0.0.0"


class SrunClient:
    def __init__(self, profile, username, password, session=None):
        self.profile = profile.validate()
        self.username = profile.account(username)
        self.password = password
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.ip = None
        self.token = None

    def close(self):
        self.session.close()

    def _get(self, path, params):
        try:
            response = self.session.get(self.profile.base_url.strip().rstrip("/") + path, params=params, timeout=(5, 12), allow_redirects=False)
            if response.status_code != 200:
                raise SrunError("The SRUN endpoint did not return HTTP 200. Check the server and API paths.")
            return parse_response(response.text)
        except requests.RequestException:
            raise SrunError("Could not reach the authentication server. Check the URL, network and VPN routing.") from None

    def challenge(self):
        if not self.username or not self.password:
            raise SrunError("Enter your campus account and password first.")
        self.ip = local_ip(self.profile)
        data = self._get(self.profile.challenge_path, {"callback": "srunCallback", "username": self.username, "ip": self.ip, "_": str(int(time.time() * 1000))})
        challenge = data.get("challenge")
        if not isinstance(challenge, str) or not challenge:
            raise SrunError("The server did not provide an authentication challenge. Check the campus profile.")
        self.token = challenge
        reported = data.get("client_ip") or data.get("online_ip")
        if reported:
            try:
                self.ip = str(ipaddress.IPv4Address(reported))
            except ipaddress.AddressValueError:
                pass
        return data

    def build_login_params(self):
        if not self.token or self.ip is None:
            raise SrunError("An authentication challenge is required.")
        profile, token, username = self.profile, self.token, self.username
        digest = hmac_md5(self.password, token)
        payload = json.dumps({"username": username, "password": self.password, "ip": self.ip, "acid": profile.ac_id, "enc_ver": profile.enc_ver}, separators=(",", ":"))
        info = "{SRBX1}" + trans_base64(xxtea_encrypt(payload, token), profile.base64_alphabet)
        checksum = sha1_hash(token + username + token + digest + token + profile.ac_id + token + self.ip + token + profile.n + token + profile.type + token + info)
        return {
            "callback": "srunCallback", "action": "login", "username": username, "password": "{MD5}" + digest,
            "os": "Windows", "name": "Windows", "nas_ip": "", "double_stack": 0, "chksum": checksum, "info": info,
            "ac_id": profile.ac_id, "ip": self.ip, "n": profile.n, "type": profile.type,
            "captchaVal": "", "_": str(int(time.time() * 1000)),
        }

    def login(self):
        self.challenge()
        data = self._get(self.profile.portal_path, self.build_login_params())
        if data.get("res") != "ok" and not ("res" not in data and data.get("error") == "ok"):
            raise SrunError("Sign-in was rejected by the server. Check your account, ac_id and protocol settings.")
        return data

    def logout(self):
        if not self.username:
            raise SrunError("Enter your campus account and password first.")
        self.ip = self.ip or local_ip(self.profile)
        data = self._get(self.profile.portal_path, {"callback": "srunCallback", "action": "logout", "username": self.username, "ip": self.ip, "ac_id": self.profile.ac_id})
        if data.get("res") != "ok" and not ("res" not in data and data.get("error") == "ok"):
            raise SrunError("Sign-out was rejected or there is no active session.")
        return data


def check_connectivity(profile, session=None):
    owned = session is None
    session = session or requests.Session()
    session.trust_env = False
    try:
        response = session.get(profile.probe_url, timeout=(3, 5), allow_redirects=False)
        return response.status_code == profile.probe_status and (not response.content if profile.probe_status == 204 else response.text.strip() == profile.probe_text.strip())
    except requests.RequestException:
        return False
    finally:
        if owned:
            session.close()
