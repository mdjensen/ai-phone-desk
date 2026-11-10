"""Configuration: environment variables, with an optional .env file underneath.

Precedence: a real environment variable wins over the same key in the .env file.
The .env file is read from PHONE_DESK_ENV_FILE, else ./.env. Nothing here is
required except OWNER_NAME and OWNER_TZ; the Vapi and LoopMessage keys are only
read when a dial or a message actually needs them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigError(RuntimeError):
    pass


def read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        text = path.read_text()
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, sep, v = line.removeprefix("export ").partition("=")
        if sep:
            out[k.strip()] = _value(v)
    return out


def _value(raw: str) -> str:
    """KEY="quoted # not a comment"  or  KEY=bare value   # a comment"""
    v = raw.strip()
    if v[:1] in ("'", '"'):
        end = v.find(v[0], 1)
        return v[1:end] if end != -1 else v[1:]
    if v.startswith("#"):
        return ""
    return v.split(" #", 1)[0].split("\t#", 1)[0].strip()


def _hour(raw: str, name: str) -> int:
    """'9', '09' or '09:00' -> 9. Whole hours only."""
    h, _, m = raw.partition(":")
    try:
        if m and int(m) != 0:
            raise ValueError
        return int(h)
    except ValueError:
        raise ConfigError(f"{name} must be a whole hour like 9 or 09:00, not {raw!r}") from None


@dataclass
class Config:
    owner_name: str
    owner_tz: str
    state_dir: Path
    window_start: int = 8                 # local hours a business may be dialed: [start, end)
    window_end: int = 20
    weekdays_only: bool = False           # also refuse Saturdays and Sundays
    daily_cap: int = 10                   # dials per local day, all origins together
    external_daily_cap: int = 3           # CALL REQUESTs accepted per external agent per day
    approval_ttl_s: int = 16 * 3600       # a 👍 is for today's call, not one days later
    bubble_max_age_s: int = 24 * 3600     # a bubble older than this cannot be approved
    approver: str = "terminal"            # terminal | loopmessage
    vapi_api_key: str = ""
    vapi_phone_number_id: str = ""
    vapi_model_provider: str = "openai"
    vapi_model: str = "gpt-4.1"
    vapi_voice_provider: str = "vapi"
    vapi_voice_id: str = "Elliot"
    vapi_voice_server_url: str = ""       # VAPI_VOICE_PROVIDER=custom-voice: your TTS endpoint
    vapi_voice_secret: str = ""           # sent by Vapi as the X-VAPI-SECRET header
    opener: str = ""                      # optional first line; must still say AI + recorded
    max_facts: int = 12                   # facts per brief (PHONE_DESK_MAX_FACTS)
    max_persona: int = 2000               # persona characters per brief (PHONE_DESK_MAX_PERSONA)
    idle_checkin: float = 6.0             # seconds of silence before the agent checks in; 0 = never
    loopmessage_api_key: str = ""
    loopmessage_sender: str = ""          # your LoopMessage sender name
    loopmessage_owner_contact: str = ""   # the owner's phone (or iMessage email) that approves
    loopmessage_webhook_secret: str = ""  # the Authorization value you set in the dashboard
    external_agent_name: str = "Instinct"
    external_agent_contact: str = ""      # the external agent's phone/handle, for inbound routing
    extra: dict = field(default_factory=dict)

    @property
    def tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.owner_tz)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ConfigError(f"OWNER_TZ {self.owner_tz!r} is not a valid IANA zone") from exc

    @property
    def voice(self) -> dict:
        """The Vapi ``voice`` block: a stock voice, or your own TTS server."""
        if self.vapi_voice_provider == "custom-voice":
            server = {"url": self.vapi_voice_server_url, "timeoutSeconds": 20}
            if self.vapi_voice_secret:
                server["secret"] = self.vapi_voice_secret
            return {"provider": "custom-voice", "server": server}
        return {"provider": self.vapi_voice_provider, "voiceId": self.vapi_voice_id}

    @property
    def kill_file(self) -> Path:
        return self.state_dir / "phone-desk.OFF"

    def killed(self) -> bool:
        return self.kill_file.exists()


def load(env_file: Optional[Path] = None, environ: Optional[dict] = None) -> Config:
    environ = dict(os.environ if environ is None else environ)
    path = env_file or Path(environ.get("PHONE_DESK_ENV_FILE") or ".env")
    values = {**read_env_file(path), **{k: v for k, v in environ.items() if v != ""}}

    def get(key: str, default: str = "") -> str:
        return str(values.get(key, default)).strip()

    owner = get("OWNER_NAME")
    tz = get("OWNER_TZ")
    if not owner:
        raise ConfigError("set OWNER_NAME (the name the voice agent says it is calling for)")
    if not tz:
        raise ConfigError("set OWNER_TZ (an IANA zone like America/Chicago); the calling window uses it")
    cfg = Config(
        owner_name=owner,
        owner_tz=tz,
        state_dir=Path(get("PHONE_DESK_STATE_DIR") or Path.home() / ".phone-desk").expanduser(),
        window_start=_hour(get("PHONE_DESK_WINDOW_START", "8"), "PHONE_DESK_WINDOW_START"),
        window_end=_hour(get("PHONE_DESK_WINDOW_END", "20"), "PHONE_DESK_WINDOW_END"),
        weekdays_only=get("PHONE_DESK_WEEKDAYS_ONLY").lower() in ("1", "true", "yes", "on"),
        daily_cap=int(get("PHONE_DESK_DAILY_CAP", "10")),
        external_daily_cap=int(get("PHONE_DESK_EXTERNAL_DAILY_CAP", "3")),
        approver=get("PHONE_DESK_APPROVER", "terminal").lower(),
        vapi_api_key=get("VAPI_API_KEY"),
        vapi_phone_number_id=get("VAPI_PHONE_NUMBER_ID"),
        vapi_model_provider=get("VAPI_MODEL_PROVIDER", "openai"),
        vapi_model=get("VAPI_MODEL", "gpt-4.1"),
        vapi_voice_provider=get("VAPI_VOICE_PROVIDER", "vapi"),
        vapi_voice_id=get("VAPI_VOICE_ID", "Elliot"),
        vapi_voice_server_url=get("VAPI_VOICE_SERVER_URL"),
        vapi_voice_secret=get("VAPI_VOICE_SECRET"),
        opener=get("OPENER"),
        max_facts=int(get("PHONE_DESK_MAX_FACTS", "12")),
        max_persona=int(get("PHONE_DESK_MAX_PERSONA", "2000")),
        idle_checkin=float(get("PHONE_DESK_IDLE_CHECKIN", "6")),
        loopmessage_api_key=get("LOOPMESSAGE_API_KEY"),
        loopmessage_sender=get("LOOPMESSAGE_SENDER_NAME"),
        loopmessage_owner_contact=get("LOOPMESSAGE_OWNER_CONTACT"),
        loopmessage_webhook_secret=get("LOOPMESSAGE_WEBHOOK_SECRET"),
        external_agent_name=get("EXTERNAL_AGENT_NAME", "Instinct"),
        external_agent_contact=get("EXTERNAL_AGENT_CONTACT"),
    )
    cfg.tz  # validate early
    if not (0 <= cfg.window_start < cfg.window_end <= 24):
        raise ConfigError("PHONE_DESK_WINDOW_START/END must satisfy 0 <= start < end <= 24")
    if cfg.vapi_voice_provider == "custom-voice" and not cfg.vapi_voice_server_url.startswith("https://"):
        raise ConfigError("VAPI_VOICE_PROVIDER=custom-voice needs VAPI_VOICE_SERVER_URL (an https:// URL)")
    if cfg.opener:
        from .brief import BriefError, check_opener
        try:
            check_opener(cfg.opener)
        except BriefError as exc:
            raise ConfigError(f"OPENER: {exc}") from None
    from . import brief
    brief.MAX_FACTS, brief.MAX_PERSONA = cfg.max_facts, cfg.max_persona   # briefs read these when validated
    if cfg.idle_checkin and not 2 <= cfg.idle_checkin <= 60:
        raise ConfigError("PHONE_DESK_IDLE_CHECKIN must be 0 (off) or 2 to 60 seconds")
    if cfg.approver not in ("terminal", "loopmessage"):
        raise ConfigError("PHONE_DESK_APPROVER must be 'terminal' or 'loopmessage'")
    return cfg
