"""Config: .env parsing and required settings."""
from pathlib import Path

import pytest

from phone_desk.config import ConfigError, load

ROOT = Path(__file__).resolve().parent.parent


def test_the_shipped_env_example_parses_to_clean_values(tmp_path):
    cfg = load(env_file=ROOT / ".env.example", environ={"PHONE_DESK_STATE_DIR": str(tmp_path)})
    assert cfg.owner_name == "Alex Rivera" and cfg.owner_tz == "America/Chicago"
    assert cfg.vapi_phone_number_id == "" and cfg.loopmessage_owner_contact == ""
    assert cfg.approver == "terminal" and cfg.external_agent_name == "Instinct"


def test_environment_variables_override_the_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text('OWNER_NAME="Alex Rivera"\nOWNER_TZ=America/Chicago\nPHONE_DESK_DAILY_CAP=10 # cap\n')
    cfg = load(env_file=env, environ={"PHONE_DESK_DAILY_CAP": "4", "PHONE_DESK_STATE_DIR": str(tmp_path)})
    assert cfg.daily_cap == 4


@pytest.mark.parametrize("missing", ["OWNER_NAME", "OWNER_TZ"])
def test_owner_name_and_timezone_are_required(tmp_path, missing):
    environ = {"OWNER_NAME": "Alex Rivera", "OWNER_TZ": "America/Chicago", "PHONE_DESK_STATE_DIR": str(tmp_path)}
    environ.pop(missing)
    with pytest.raises(ConfigError, match=missing):
        load(env_file=tmp_path / "none", environ=environ)


def test_a_bad_timezone_or_approver_is_refused(tmp_path):
    base = {"OWNER_NAME": "Alex Rivera", "PHONE_DESK_STATE_DIR": str(tmp_path)}
    with pytest.raises(ConfigError):
        load(env_file=tmp_path / "none", environ={**base, "OWNER_TZ": "Mars/Olympus"})
    with pytest.raises(ConfigError):
        load(env_file=tmp_path / "none", environ={**base, "OWNER_TZ": "UTC", "PHONE_DESK_APPROVER": "email"})


def _load(tmp_path, **env):
    base = {"OWNER_NAME": "Alex Rivera", "OWNER_TZ": "America/Denver", "PHONE_DESK_STATE_DIR": str(tmp_path)}
    return load(env_file=tmp_path / "none", environ={**base, **env})


def test_a_custom_voice_server_becomes_the_vapi_voice_block(tmp_path):
    cfg = _load(tmp_path, VAPI_VOICE_PROVIDER="custom-voice", VAPI_VOICE_SERVER_URL="https://tts.example.com/v",
                VAPI_VOICE_SECRET="shh")
    assert cfg.voice == {"provider": "custom-voice",
                         "server": {"url": "https://tts.example.com/v", "secret": "shh", "timeoutSeconds": 20}}
    assert _load(tmp_path).voice == {"provider": "vapi", "voiceId": "Elliot"}
    with pytest.raises(ConfigError, match="VAPI_VOICE_SERVER_URL"):
        _load(tmp_path, VAPI_VOICE_PROVIDER="custom-voice")


def test_an_opener_must_keep_the_ai_and_recording_disclosures(tmp_path):
    ok = "Hi, I'm Dynamo, an AI robot calling for {owner}. This call is recorded."
    assert _load(tmp_path, OPENER=ok).opener == ok
    with pytest.raises(ConfigError, match="OPENER"):
        _load(tmp_path, OPENER="Hi, I'm Dynamo calling for {owner}. This call is recorded.")
    with pytest.raises(ConfigError, match="OPENER"):
        _load(tmp_path, OPENER="Hi, I'm Dynamo, an AI robot calling for {owner}.")


@pytest.mark.parametrize("start,end", [("9", "17"), ("09", "17"), ("09:00", "17:00")])
def test_the_window_takes_hours_or_hh_00(tmp_path, start, end):
    cfg = _load(tmp_path, PHONE_DESK_WINDOW_START=start, PHONE_DESK_WINDOW_END=end, PHONE_DESK_WEEKDAYS_ONLY="1")
    assert (cfg.window_start, cfg.window_end, cfg.weekdays_only) == (9, 17, True)
    with pytest.raises(ConfigError):
        _load(tmp_path, PHONE_DESK_WINDOW_START="09:30")
    assert _load(tmp_path).weekdays_only is False
