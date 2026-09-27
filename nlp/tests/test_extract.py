import json
from typing import Any

import httpx
import pytest
import respx

from app.extract import SYSTEM_PROMPT, InvalidOutput, SlotSpec, build_schema, coerce

CHAT = r".*/api/chat$"

JOINT_SLOTS = [
    {"name": "site", "type": "enum", "enum": ["knee", "back", "hip"]},
    {"name": "duration_days", "type": "duration_days"},
    {"name": "fever", "type": "bool"},
]


def req(text: str, slots: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "question_id": "jp_site",
        "language": "hi",
        "text": text,
        "question_text_en": "Which joint hurts the most?",
        "slots": slots if slots is not None else JOINT_SLOTS,
    }


def reply(content: dict[str, Any] | str) -> httpx.Response:
    body = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return httpx.Response(200, json={"message": {"role": "assistant", "content": body}, "done": True})


def test_schema_types() -> None:
    slots = [
        SlotSpec(name="s", type="string"),
        SlotSpec(name="e", type="enum", enum=["a", "b"]),
        SlotSpec(name="b", type="bool"),
        SlotSpec(name="n", type="number"),
        SlotSpec(name="d", type="duration_days"),
        SlotSpec(name="sc", type="scale_0_10"),
        SlotSpec(name="le", type="list_enum", enum=["x", "y"]),
        SlotSpec(name="ls", type="list_string"),
    ]
    schema = build_schema(slots)
    p = schema["properties"]
    assert schema["required"] == ["s", "e", "b", "n", "d", "sc", "le", "ls"]
    assert schema["additionalProperties"] is False
    assert p["s"] == {"type": ["string", "null"]}
    assert p["e"] == {"type": ["string", "null"], "enum": ["a", "b", None]}
    assert p["b"] == {"type": ["boolean", "null"]}
    assert p["n"] == {"type": ["number", "null"]}
    assert p["d"] == {"type": ["integer", "null"]}
    assert p["sc"] == {"type": ["integer", "null"], "minimum": 0, "maximum": 10}
    assert p["le"] == {"type": ["array", "null"], "items": {"type": "string", "enum": ["x", "y"]}}
    assert p["ls"] == {"type": ["array", "null"], "items": {"type": "string"}}


@pytest.mark.parametrize(
    ("slot", "value", "expected"),
    [
        (SlotSpec(name="d", type="duration_days"), 45.5, 46),
        (SlotSpec(name="sc", type="scale_0_10"), 7.0, 7),
        (SlotSpec(name="s", type="string"), "  ", None),
        (SlotSpec(name="le", type="list_enum", enum=["x", "y"]), ["x", "x", "y"], ["x", "y"]),
        (SlotSpec(name="ls", type="list_string"), [" dolo ", ""], ["dolo"]),
        (SlotSpec(name="b", type="bool"), None, None),
    ],
)
def test_coerce_ok(slot: SlotSpec, value: Any, expected: Any) -> None:
    assert coerce(slot, value) == expected


@pytest.mark.parametrize(
    ("slot", "value"),
    [
        (SlotSpec(name="e", type="enum", enum=["a"]), "z"),
        (SlotSpec(name="sc", type="scale_0_10"), 11),
        (SlotSpec(name="b", type="bool"), "yes"),
        (SlotSpec(name="n", type="number"), True),
        (SlotSpec(name="d", type="duration_days"), -3),
        (SlotSpec(name="le", type="list_enum", enum=["x"]), ["q"]),
    ],
)
def test_coerce_invalid(slot: SlotSpec, value: Any) -> None:
    with pytest.raises(InvalidOutput):
        coerce(slot, value)


def test_extract_request_and_answer(client) -> None:
    with respx.mock() as mock:
        route = mock.post(url__regex=CHAT).mock(
            return_value=reply({"site": "knee", "duration_days": 90, "fever": False})
        )
        r = client.post("/extract", json=req("teen mahine se ghutne mein dard hai, bukhar nahi hai"))
    assert r.status_code == 200, r.text
    assert r.json() == {
        "slots": {"site": "knee", "duration_days": 90, "fever": False},
        "status": "confident",
        "notes": [],
    }
    sent = json.loads(route.calls[0].request.content)
    assert sent["stream"] is False and sent["options"] == {"temperature": 0}
    assert sent["format"] == build_schema([SlotSpec(**s) for s in JOINT_SLOTS])
    msgs = sent["messages"]
    assert msgs[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert [m["role"] for m in msgs[1:]] == ["user", "assistant"] * 3 + ["user"]  # 3 few-shot turns
    assert "teen mahine se ghutne" in msgs[-1]["content"] and "knee (Knee, घुटना)" in msgs[-1]["content"]


def test_system_prompt_exact() -> None:
    assert SYSTEM_PROMPT == (
        "You extract facts from a patient's answer to one clinical question. Return only JSON that matches the "
        "schema. Use null for anything the patient did not say. If the patient denies something (for example "
        "'nahi', 'नहीं', 'no'), set it to false. Never guess, never diagnose, never add fields."
    )


def test_null_duration_filled_from_normalize(client) -> None:
    with respx.mock() as mock:
        mock.post(url__regex=CHAT).mock(return_value=reply({"site": "knee", "duration_days": None, "fever": None}))
        body = client.post("/extract", json=req("dedh mahine se ghutne mein dard")).json()
    assert body["slots"]["duration_days"] == 45 and body["status"] == "confident"
    assert body["notes"] == ["duration_days filled from 'dedh mahine se'"]


def test_model_duration_replaced_by_rule(client) -> None:
    with respx.mock() as mock:
        mock.post(url__regex=CHAT).mock(return_value=reply({"site": None, "duration_days": 3, "fever": None}))
        body = client.post("/extract", json=req("teen mahine se")).json()
    assert body["slots"]["duration_days"] == 90
    assert body["notes"] == ["duration_days 3 replaced by 90 from 'teen mahine se'"]


def test_invalid_then_valid_retries_once(client) -> None:
    with respx.mock() as mock:
        route = mock.post(url__regex=CHAT).mock(
            side_effect=[reply("{not json"), reply({"site": "hip", "duration_days": None, "fever": None})]
        )
        body = client.post("/extract", json=req("kulhe mein dard")).json()
    assert route.call_count == 2
    assert body == {"slots": {"site": "hip", "duration_days": None, "fever": None}, "status": "confident", "notes": []}


def test_invalid_twice_is_uncertain(client) -> None:
    with respx.mock() as mock:
        route = mock.post(url__regex=CHAT).mock(return_value=reply({"site": "elbow", "duration_days": 1}))
        body = client.post("/extract", json=req("kohni mein dard")).json()
    assert route.call_count == 2
    assert body["status"] == "uncertain" and body["slots"] == {"site": None, "duration_days": None, "fever": None}
    assert body["notes"][0].startswith("model output invalid after retry")


def test_empty_text_skips_model(client) -> None:
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(url__regex=CHAT).mock(return_value=reply({}))
        body = client.post("/extract", json=req("   ")).json()
    assert not route.called
    assert body == {"slots": {"site": None, "duration_days": None, "fever": None}, "status": "uncertain",
                    "notes": ["empty text"]}  # fmt: skip


def test_ollama_down_is_uncertain_but_keeps_rule_duration(client) -> None:
    with respx.mock() as mock:
        mock.post(url__regex=CHAT).mock(side_effect=httpx.ConnectError("down"))
        body = client.post("/extract", json=req("do hafte se")).json()
    assert body["status"] == "uncertain"
    assert body["slots"]["duration_days"] == 14
    assert "language model unavailable" in body["notes"]


def test_ollama_http_500_is_uncertain(client) -> None:
    with respx.mock() as mock:
        mock.post(url__regex=CHAT).mock(return_value=httpx.Response(500, json={"error": "boom"}))
        body = client.post("/extract", json=req("ghutne mein dard")).json()
    assert body["status"] == "uncertain" and body["notes"] == ["language model unavailable"]


def test_nothing_extracted_is_uncertain(client) -> None:
    with respx.mock() as mock:
        mock.post(url__regex=CHAT).mock(return_value=reply({"site": None, "duration_days": None, "fever": None}))
        body = client.post("/extract", json=req("pata nahi")).json()
    assert body["status"] == "uncertain" and body["notes"] == ["nothing extracted"]


def test_list_slots(client) -> None:
    slots = [{"name": "current_medicines", "type": "list_string"}]
    with respx.mock() as mock:
        mock.post(url__regex=CHAT).mock(return_value=reply({"current_medicines": ["Dolo 650", "metformin"]}))
        body = client.post("/extract", json=req("dolo aur metformin", slots)).json()
    assert body == {"slots": {"current_medicines": ["Dolo 650", "metformin"]}, "status": "confident", "notes": []}


def test_bad_slot_type_is_422(client) -> None:
    r = client.post("/extract", json=req("x", [{"name": "a", "type": "colour"}]))
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


# ---- grounding (added after the live voice test: misheard "दोनों तरफ़" came back as a confident "right") ----
from app.extract import SlotSpec, ungrounded


@pytest.mark.parametrize(
    ("slot", "enum", "value", "text", "ok"),
    [
        ("site", ["knee", "back", "hip", "shoulder", "hands", "ankle", "neck"], "knee", "मेरे घुटने में दर्द है", True),
        ("site", ["knee", "back", "hip", "shoulder", "hands", "ankle", "neck"], "back", "कमर में दर्द", True),
        ("side", ["left", "right", "both"], "right", "जूनों तरफ", False),  # the real misheard case
        ("side", ["left", "right", "both"], "both", "दोनों तरफ़", True),
        ("onset", ["sudden", "gradual"], "gradual", "धीरे धीरे शुरू हुआ", True),
        ("morning_stiffness", ["none", "under_30", "over_30"], "under_30", "आधा घंटा से ज्यादा", False),
        ("character", ["aching", "sharp", "burning", "throbbing"], "aching", "हम", False),
    ],
)
def test_enum_grounding(slot, enum, value, text, ok) -> None:
    assert (ungrounded(SlotSpec(name=slot, type="enum", enum=enum), value, text) is None) is ok


def test_list_grounding_and_non_enum_skipped() -> None:
    spec = SlotSpec(name="worse_with", type="list_enum", enum=["stairs", "walking", "cold", "rest", "morning"])
    assert ungrounded(spec, ["stairs", "cold"], "सीढ़ी चढ़ने में और ठंड में") is None
    assert ungrounded(spec, ["stairs", "morning"], "सीढ़ी चढ़ने में") is not None
    assert ungrounded(SlotSpec(name="duration_days", type="duration_days"), 90, "तीन महीने से") is None
    assert ungrounded(SlotSpec(name="unknown_slot", type="enum", enum=["a"]), "a", "xyz") is None  # no labels known


def test_romanised_hindi_is_not_grounding_checked() -> None:
    spec = SlotSpec(name="site", type="enum", enum=["knee", "back", "hip", "shoulder", "hands", "ankle", "neck"])
    assert ungrounded(spec, "knee", "ghutne mein dard", "hi") is None  # typed romanised: no labels in that script
    assert ungrounded(spec, "knee", "my knee hurts", "en") is None
    assert ungrounded(spec, "back", "my knee hurts", "en") is not None
