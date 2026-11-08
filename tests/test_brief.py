"""The brief: what the owner sees is everything the voice agent knows."""
import pytest
from conftest import GYM, brief

from phone_desk import brief as B

OWNER = "Alex Rivera"


def test_numbers_are_normalized():
    assert B.normalize_us("(312) 555-0147") == GYM
    assert B.normalize_us("1-312-555-0147") == GYM
    assert B.normalize_us("+1 312.555.0147") == GYM


@pytest.mark.parametrize("bad", ["911", "411", "1-900-555-0100", "976-555-0100", "+44 20 7946 0958",
                                 "312-555-014", "(011) 555-0147", "(312) 011-0147", "(312) 911-0147"])
def test_invalid_premium_and_service_numbers_are_refused(bad):
    with pytest.raises(B.BriefError):
        B.normalize_us(bad)


@pytest.mark.parametrize("bad", ["876-555-0100", "809-555-0100", "1-473-555-0100", "242-555-0100", "284-555-0100"])
def test_caribbean_numbers_in_the_plus_one_plan_are_refused(bad):
    with pytest.raises(B.BriefError, match="Caribbean"):
        B.normalize_us(bad)


def test_us_territories_are_not_caribbean_refusals():
    assert B.normalize_us("787-555-0100") == "+17875550100"     # Puerto Rico
    assert B.normalize_us("340-555-0100") == "+13405550100"     # USVI


@pytest.mark.parametrize("fact", ["Card: 4111 1111 1111 1111", "SSN 123-45-6789", "Password is hunter2",
                                  "Date of birth: Jan 2", "DOB 1990-01-02", "CVV 123", "PIN 4321",
                                  "Routing number 123456780", "Bank account at First Example Bank"])
def test_credential_card_bank_ssn_and_birthdate_facts_are_refused(fact):
    with pytest.raises(B.BriefError, match="never carries"):
        brief(facts=[fact])


def test_ordinary_account_facts_are_fine():
    b = brief(facts=["Member number: NAC-20417", "Phone on file: (312) 555-0199", "Email on file: alex@example.com"])
    assert len(b.facts) == 3


def test_the_bubble_and_the_agent_carry_the_same_facts_and_nothing_else():
    b = brief()
    text, prompt = B.render(b, "abcd1234", OWNER), B.system_prompt(b, OWNER)
    for f in b.facts + [b.goal, b.ask, b.fallback]:
        assert f in text and f in prompt
    assert B.opener(OWNER) in text and B.opener(OWNER) in prompt
    assert "abcd1234" in text and "abcd1234" not in prompt
    # the prompt's only text beyond the brief is the fixed hard rules
    rest = prompt
    for piece in b.facts + [b.goal, b.ask, b.fallback, b.who]:
        rest = rest.replace(piece, "")
    assert "555-0199" not in rest and "@" not in rest


def test_the_agent_says_it_is_an_ai_and_never_claims_to_be_the_owner():
    prompt = B.system_prompt(brief(), OWNER)
    assert "You are an AI assistant" in prompt and f"Never claim to be {OWNER}" in prompt
    for never in ("card number", "bank detail", "birth date", "password", "Social Security"):
        assert never in prompt
    assert "Never agree to pay anything" in prompt


def test_the_agent_hangs_up_on_voicemail_unless_a_message_was_approved():
    assert "without leaving a message" in B.system_prompt(brief(), OWNER)
    b = brief(voicemail="Please call Alex back about the membership.")
    assert b.voicemail in B.render(b, "x", OWNER) and b.voicemail in B.system_prompt(b, OWNER)


def test_call_screening_is_not_treated_as_voicemail():
    prompt = B.system_prompt(brief(), OWNER)
    assert "Call screening is NOT voicemail" in prompt and "Never hang up while told to hold" in prompt


def test_assistant_config_caps_duration_records_and_can_press_keys():
    a = B.assistant(brief(max_minutes=999), OWNER)
    assert a["maxDurationSeconds"] == B.MAX_MINUTES_CAP * 60
    assert a["artifactPlan"]["recordingEnabled"] and a["firstMessageMode"] == "assistant-waits-for-user"
    assert {"type": "endCall"} in a["model"]["tools"] and {"type": "dtmf"} in a["model"]["tools"]
    assert a["analysisPlan"]["structuredDataPlan"]["schema"] is B.OUTCOME_SCHEMA


def test_an_external_request_is_marked_in_the_bubble_and_must_name_its_agent():
    b = brief(origin="external", requested_by="Instinct")
    assert "(Instinct asked for this)" in B.render(b, "x", OWNER)
    with pytest.raises(B.BriefError):
        brief(origin="external")


def test_too_many_facts_and_overlong_fields_are_refused():
    with pytest.raises(B.BriefError):
        brief(facts=[f"fact {i}" for i in range(B.MAX_FACTS + 1)])
    with pytest.raises(B.BriefError):
        brief(goal="x" * 401)


# ── opener, persona, custom voice, outcome fields ────────────────────────────
@pytest.mark.parametrize("bad", [
    "Hi, this is Dynamo calling for {owner}. This call is recorded.",          # no AI
    "Hi, this is an AI assistant calling for {owner}.",                        # no recording notice
    "Hi, this is Dynamo, a robot, said the chair. This call is recorded.",     # 'said' is not 'AI'
])
def test_an_opener_without_both_disclosures_is_refused(bad):
    with pytest.raises(B.BriefError):
        B.check_opener(bad)
    with pytest.raises(B.BriefError):
        B.render(brief(), "x", OWNER, custom_opener=bad)


def test_a_custom_opener_is_what_the_bubble_shows_and_the_agent_says():
    op = "Hi! I'm Dynamo, an AI robot calling for {owner}. This call is being recorded."
    b = brief()
    said = op.replace("{owner}", OWNER)
    assert said in B.render(b, "x", OWNER, custom_opener=op)
    prompt = B.assistant(b, OWNER, custom_opener=op)["model"]["messages"][0]["content"]
    assert f'Open with exactly: "{said}"' in prompt
    assert B.render(b, "x", OWNER) != B.render(b, "x", OWNER, custom_opener=op)   # so the hash binds it


def test_the_persona_is_in_the_bubble_and_the_prompt_and_the_hard_rules_still_win():
    b = brief(persona="You are Dynamo, a cheerful humanoid robot.\n\nYou book event appearances.")
    text, prompt = B.render(b, "x", OWNER), B.system_prompt(b, OWNER)
    assert "Dynamo, a cheerful humanoid robot" in text and "Dynamo, a cheerful humanoid robot" in prompt
    assert prompt.index("You book event appearances") < prompt.index("HARD RULES.")
    assert "HARD RULES below override this" in prompt


def test_a_persona_is_optional_and_bounded():
    assert "Persona:" not in B.render(brief(), "x", OWNER)
    with pytest.raises(B.BriefError):
        brief(persona="x" * (B.MAX_PERSONA + 1))
    with pytest.raises(B.BriefError):
        brief(persona="Card 4111 1111 1111 1111")


def test_a_custom_voice_block_replaces_the_stock_voice():
    v = {"provider": "custom-voice", "server": {"url": "https://tts.example.com/v", "secret": "s",
                                                "timeoutSeconds": 20}}
    assert B.assistant(brief(), OWNER, voice=v)["voice"] == v
    assert B.assistant(brief(), OWNER)["voice"] == {"provider": "vapi", "voiceId": "Elliot"}


def test_the_outcome_schema_keeps_the_old_fields_and_adds_the_booking_fields():
    props = B.OUTCOME_SCHEMA["properties"]
    for k in ("outcome", "what_they_did", "confirmation", "staff_name", "money", "next_step_for_owner",
              "follow_up_by", "interest", "contacts", "event_name", "event_dates", "venue", "attendance",
              "budget_range", "hold_requested_dates", "next_step", "follow_up_on", "best_time", "objections",
              "do_not_call"):
        assert k in props
    assert props["interest"]["enum"] == ["hot", "warm", "cold", "not_now", "no"]
    contact = props["contacts"]["items"]["properties"]
    assert contact["decision_maker"]["type"] == contact["sms_consent"]["type"] == "boolean"
    assert set(B.OUTCOME_SCHEMA["required"]) == {"outcome", "what_they_did", "next_step_for_owner"}
