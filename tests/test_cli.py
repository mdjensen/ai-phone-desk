"""The CLI surface other programs shell out to."""
import json

from phone_desk import cli


def _env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for k, v in {"OWNER_NAME": "Alex Rivera", "OWNER_TZ": "America/Denver",
                 "PHONE_DESK_STATE_DIR": str(tmp_path / "state"), "PHONE_DESK_ENV_FILE": str(tmp_path / "none")}.items():
        monkeypatch.setenv(k, v)


def test_propose_with_a_persona_file_then_status_json(monkeypatch, tmp_path, capsys):
    _env(monkeypatch, tmp_path)
    (tmp_path / "persona.txt").write_text("You are Dynamo, a humanoid robot.\n\nYou book event appearances.\n")
    assert cli.main(["propose", "--who", "Expo Hall", "--to", "(801) 555-0123", "--goal", "Book a demo slot.",
                     "--persona-file", str(tmp_path / "persona.txt"), "--fact", "Dynamo is 1.3 m tall"]) == 0
    out = capsys.readouterr().out
    assert "Persona: You are Dynamo, a humanoid robot." in out
    iid = json.loads(out.strip().splitlines()[-1])["id"]
    assert cli.main(["status", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows == [{**rows[0], "id": iid, "status": "surfaced", "who": "Expo Hall", "to": "+18015550123"}]
    assert cli.main(["status", iid]) == 0
    assert json.loads(capsys.readouterr().out)["brief"]["persona"].endswith("You book event appearances.")


def test_approve_batch_refuses_without_a_terminal(monkeypatch, tmp_path, capsys):
    _env(monkeypatch, tmp_path)
    cli.main(["propose", "--who", "Expo Hall", "--to", "(801) 555-0123", "--goal", "Book a demo slot."])
    iid = json.loads(capsys.readouterr().out.strip().splitlines()[-1])["id"]
    assert cli.main(["approve-batch", iid]) == 0
    assert "not a TTY" in capsys.readouterr().out
