import json
from typing import Any

import httpx
import respx

from app.summarize import SYSTEM_PROMPT, FactIn, ground

CHAT = r".*/api/chat$"

FACTS: list[dict[str, Any]] = [
    {"section": "complaint", "key": "site", "value": {"value": "knee"}, "text_en": "Pain in the Knee"},
    {"section": "complaint", "key": "side", "value": {"value": "right"}, "text_en": "Right side"},
    {"section": "hpi", "key": "duration_days", "value": {"value": 90}, "text_en": "Duration: 90 days"},
    {"section": "hpi", "key": "swelling", "value": {"value": True}, "text_en": "Joint is swollen"},
    {"section": "hpi", "key": "worse_with", "value": {"value": ["stairs"]}, "text_en": "Worse with: climbing stairs"},
    {"section": "hpi", "key": "severity", "value": {"value": 7}, "text_en": "Severity 7/10"},
    {"section": "hpi", "key": "fever", "value": {"value": False}, "text_en": "No fever"},
]
FALLBACK = "Pain in the Knee; Right side; Duration: 90 days; Joint is swollen; Worse with: climbing stairs; " \
    "Severity 7/10; No fever"  # fmt: skip


def reply(narrative: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"content": json.dumps({"narrative": narrative})}})


def post(client, narrative: str, facts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    with respx.mock() as mock:
        mock.post(url__regex=CHAT).mock(return_value=reply(narrative))
        r = client.post("/summarize", json={"language": "en", "facts": FACTS if facts is None else facts})
    assert r.status_code == 200, r.text
    return r.json()


def test_faithful_narrative_kept(client) -> None:
    text = (
        "The patient reports pain in the right knee for 90 days, and the joint is swollen. "
        "Pain is worse when climbing stairs and rated 7 out of 10. There is no fever."
    )
    assert post(client, text) == {"narrative": text, "unsupported_terms": [], "fallback_used": False}


def test_request_payload(client) -> None:
    with respx.mock() as mock:
        route = mock.post(url__regex=CHAT).mock(return_value=reply("The patient reports pain in the knee."))
        client.post("/summarize", json={"language": "en", "facts": FACTS})
    sent = json.loads(route.calls[0].request.content)
    assert sent["options"] == {"temperature": 0} and sent["stream"] is False
    assert sent["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert "Do not add facts, diagnoses or advice" in SYSTEM_PROMPT and "at most 3" in SYSTEM_PROMPT
    assert "- Duration: 90 days" in sent["messages"][1]["content"]


def test_hallucinated_sentence_removed(client) -> None:
    text = (
        "The patient reports right knee pain for 90 days. "
        "This is likely osteoarthritis and the patient should take rest. "
        "Pain is worse with stairs."
    )
    body = post(client, text)
    assert body["narrative"] == "The patient reports right knee pain for 90 days. Pain is worse with stairs."
    assert body["unsupported_terms"] == ["likely", "osteoarthritis", "should", "rest"]
    assert body["fallback_used"] is False


def test_invented_number_removed(client) -> None:
    body = post(client, "Knee pain for 3 months. Severity is 7 out of 10.")
    assert body["narrative"] == "Severity is 7 out of 10." and body["unsupported_terms"] == ["3"]


def test_number_word_checked(client) -> None:
    body = post(client, "Knee pain for ninety days. Pain for two weeks.")
    assert body["narrative"] == "Knee pain for ninety days." and body["unsupported_terms"] == ["two"]


def test_denied_symptom_asserted_is_removed(client) -> None:
    body = post(client, "The knee is swollen. The patient has fever.")
    assert body["narrative"] == "The knee is swollen." and body["unsupported_terms"] == ["fever"]


def test_unmentioned_symptom_removed(client) -> None:
    body = post(client, "Right knee pain with morning stiffness. The joint is swollen.")
    assert body["narrative"] == "The joint is swollen."
    assert body["unsupported_terms"] == ["morning", "stiffness"]


def test_lexicon_concept_is_a_clinical_word(client) -> None:
    body = post(client, "The knee is swollen. The patient also has constipation.")
    assert body["narrative"] == "The knee is swollen." and body["unsupported_terms"] == ["constipation"]


def test_max_three_sentences(client) -> None:
    text = "Knee pain. The joint is swollen. Worse with stairs. Severity 7 out of 10. No fever."
    assert post(client, text)["narrative"] == "Knee pain. The joint is swollen. Worse with stairs."


def test_everything_removed_falls_back(client) -> None:
    body = post(client, "The patient has gout and should see a specialist.")
    assert body == {"narrative": FALLBACK, "unsupported_terms": ["gout", "should"], "fallback_used": True}


def test_ollama_down_falls_back(client) -> None:
    with respx.mock() as mock:
        mock.post(url__regex=CHAT).mock(side_effect=httpx.ConnectError("down"))
        body = client.post("/summarize", json={"language": "en", "facts": FACTS}).json()
    assert body == {"narrative": FALLBACK, "unsupported_terms": [], "fallback_used": True}


def test_bad_model_json_falls_back(client) -> None:
    with respx.mock() as mock:
        mock.post(url__regex=CHAT).mock(return_value=httpx.Response(200, json={"message": {"content": "oops"}}))
        body = client.post("/summarize", json={"language": "en", "facts": FACTS}).json()
    assert body["fallback_used"] is True and body["narrative"] == FALLBACK


def test_no_facts(client) -> None:
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(url__regex=CHAT).mock(return_value=reply("x"))
        body = client.post("/summarize", json={"language": "en", "facts": []}).json()
    assert not route.called and body == {"narrative": "", "unsupported_terms": [], "fallback_used": True}


def test_ground_synonyms_and_plurals() -> None:
    facts = [FactIn(section="hpi", key="injury", value={"value": True}, text_en="Had a fall last month")]
    kept, bad = ground("The patient was injured in a fall.", facts)
    assert kept == ["The patient was injured in a fall."] and bad == []


def test_language_must_be_en(client) -> None:
    r = client.post("/summarize", json={"language": "hi", "facts": FACTS})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
