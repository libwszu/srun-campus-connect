"""Validated, credential-free campus profiles and local-only account settings."""

from dataclasses import asdict, dataclass, field, fields
import ipaddress
import json
from pathlib import Path
from urllib.parse import urlsplit


SRUN_ALPHABET = "LVoJPiCN2R8G90yg+hmFHuacZ1OWMnrsSTXkYpUq/3dlbfKwv6xztjI7DeBE45QA"


class ProfileError(ValueError):
    pass


def validate_url(value, *, portal=False):
    if any(ord(c) < 33 for c in value.strip()):
        raise ProfileError("Enter an HTTP or HTTPS URL without embedded credentials.")
    parsed = urlsplit(value.strip())
    try:
        parsed.port
    except ValueError:
        raise ProfileError("The server port is invalid.") from None
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ProfileError("Enter an HTTP or HTTPS URL without embedded credentials.")
    if parsed.fragment or (portal and parsed.query):
        raise ProfileError("Use the server base URL without a query or fragment.")
    return value.strip().rstrip("/")


@dataclass(frozen=True)
class CampusProfile:
    name: str = "My campus"
    base_url: str = ""
    ac_id: str = "1"
    username_suffix: str = ""
    challenge_path: str = "/cgi-bin/get_challenge"
    portal_path: str = "/cgi-bin/srun_portal"
    n: str = "200"
    type: str = "1"
    enc_ver: str = "srun_bx1"
    base64_alphabet: str = SRUN_ALPHABET
    client_ip: str = ""
    probe_url: str = "http://www.msftconnecttest.com/connecttest.txt"
    probe_status: int = 200
    probe_text: str = "Microsoft Connect Test"

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) - {item.name for item in fields(cls)}:
            raise ProfileError("This is not a supported campus profile.")
        data = dict(value)
        for key in ("ac_id", "n", "type"):
            if key in data:
                data[key] = str(data[key])
        if "probe_status" in data:
            try:
                data["probe_status"] = int(data["probe_status"])
            except (TypeError, ValueError):
                raise ProfileError("The probe status must be an HTTP status number.") from None
        if any(not isinstance(v, str) for k, v in data.items() if k != "probe_status"):
            raise ProfileError("Profile text fields must contain text.")
        return cls(**data)

    def validate(self):
        validate_url(self.base_url, portal=True)
        validate_url(self.probe_url)
        for path in (self.challenge_path, self.portal_path):
            parsed = urlsplit(path)
            if not path.startswith("/") or path.startswith("//") or parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
                raise ProfileError("API paths must start with / and stay on the configured server.")
        if not self.ac_id.isdigit() or not self.n.isdigit() or not self.type.isdigit():
            raise ProfileError("ac_id, n and type must be numeric.")
        if self.enc_ver != "srun_bx1":
            raise ProfileError("This version supports the SRUN BX1 protocol only.")
        if len(self.base64_alphabet) != 64 or len(set(self.base64_alphabet)) != 64 or any(not 33 <= ord(c) <= 126 for c in self.base64_alphabet) or "=" in self.base64_alphabet:
            raise ProfileError("The Base64 alphabet must contain 64 distinct ASCII characters without =.")
        if self.username_suffix and (not self.username_suffix.startswith("@") or any(c.isspace() for c in self.username_suffix)):
            raise ProfileError("The account suffix must be empty or start with @.")
        if self.client_ip:
            try:
                ipaddress.IPv4Address(self.client_ip)
            except ipaddress.AddressValueError:
                raise ProfileError("The optional client IP must be an IPv4 address.") from None
        if not isinstance(self.probe_status, int) or not 100 <= self.probe_status <= 599 or self.probe_status in (301, 302, 303, 307, 308):
            raise ProfileError("Use a non-redirect HTTP status for connectivity checks.")
        if self.probe_status != 204 and not self.probe_text.strip():
            raise ProfileError("Provide expected probe text, or use HTTP 204.")
        return self

    def to_dict(self):
        return asdict(self)

    def account(self, username):
        username = username.strip()
        return username + self.username_suffix if username and "@" not in username else username


@dataclass
class Settings:
    profile: CampusProfile = field(default_factory=CampusProfile)
    username: str = ""
    password: str = ""
    language: str = "en"
    check_interval: int = 60
    reconnect_retries: int = 3
    retry_delay: int = 10
    auto_login: bool = True

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ProfileError("The settings file is not a JSON object.")
        if any(not isinstance(value.get(key, ""), str) for key in ("username", "password")):
            raise ProfileError("Account and password must be text.")
        options = {}
        for key, default, minimum, maximum in (("check_interval", 60, 10, 86400), ("reconnect_retries", 3, 1, 10), ("retry_delay", 10, 1, 300)):
            try:
                options[key] = max(minimum, min(maximum, int(value.get(key, default))))
            except (ValueError, TypeError):
                options[key] = default
        return cls(
            profile=CampusProfile.from_dict(value.get("profile", {})),
            username=str(value.get("username", "")), password=str(value.get("password", "")),
            language=value.get("language") if value.get("language") in ("en", "zh-CN") else "en",
            auto_login=value.get("auto_login", True) is True, **options,
        )

    def to_dict(self):
        return {**asdict(self), "profile": self.profile.to_dict()}


class ConfigStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / "settings.json"

    def load(self):
        if not self.path.exists():
            return Settings()
        try:
            return Settings.from_dict(json.loads(self.path.read_text(encoding="utf-8-sig")))
        except (OSError, ValueError, TypeError) as error:
            raise ProfileError("Could not read settings. Back up and check settings.json.") from error

    def save(self, settings):
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(settings.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


def load_profile(path):
    try:
        return CampusProfile.from_dict(json.loads(Path(path).read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, TypeError) as error:
        raise ProfileError("Could not read the campus profile.") from error


def export_profile(path, profile):
    profile.validate()
    Path(path).write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
