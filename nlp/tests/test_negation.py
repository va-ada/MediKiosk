import json

import httpx
import pytest
import respx

from app.negation import check


@pytest.mark.parametrize(
    ("text", "slots"),
    [
        ("bukhar nahi hai", {"fever": True}),  # romanised
        ("बुखार नहीं है", {"fever": True}),  # Hindi
        ("no fever", {"fever": True}),  # English, cue before keyword
        ("I do not have any fever", {"fever": True}),  # cue 3 tokens before
        ("सूजन तो नहीं है", {"swelling": True}),
        ("koi chot nahi lagi", {"injury": True}),
        ("मैं गिरा नहीं", {"injury": True}),
        ("seene mein dard nahi", {"chest_pain": True}),
        ("saans ki dikkat nahi hai", {"breathless": True}),
        ("never fainted", {"fainted": True}),
        ("behosh nhi hua", {"fainted": True}),  # "nhi" spelling
    ],
)
def test_negated_true_is_dropped(text: str, slots: dict) -> None:
    out, notes, uncertain = check(text, slots)
    name = next(iter(slots))
    assert out[name] is None and uncertain is True
    assert len(notes) == 1 and notes[0].startswith(f"{name}=true dropped")


@pytest.mark.parametrize(
    ("text", "slots"),
    [
        ("haan bukhar hai", {"fever": True}),  # affirmed
        ("बुखार है", {"fever": True}),
        ("I have a high fever since yesterday", {"fever": True}),
        ("bukhar nahi hai", {"fever": False}),  # false is already right
        ("bukhar nahi hai", {"fever": None}),  # nothing to check
        ("nahi nahi, ghutne mein bahut sujan hai aur dard bhi", {"swelling": True}),  # cue too far away (5 tokens)
        ("koi nahi, dard hai", {"site": True}),  # slot without keywords is left alone
    ],
)
def test_left_alone(text: str, slots: dict) -> None:
    assert check(text, slots) == (slots, [], False)


def test_only_the_negated_slot_is_dropped() -> None:
    out, notes, uncertain = check("sujan hai lekin bahut dino se, bukhar nahi", {"swelling": True, "fever": True})
    assert out == {"swelling": True, "fever": None} and uncertain
    assert notes == ["fever=true dropped: negation 'nahi' near 'bukhar'"]


def test_input_not_mutated() -> None:
    slots = {"fever": True}
    check("bukhar nahi", slots)
    assert slots == {"fever": True}


def test_custom_keyword_map() -> None:
    out, _, uncertain = check("khansi nahi hai", {"cough": True}, {"cough": ["khansi"]})
    assert out == {"cough": None} and uncertain
    assert check("bukhar nahi hai", {"fever": True}, {"cough": ["khansi"]})[2] is False  # map replaces defaults


def test_multiword_keyword() -> None:
    out, notes, _ = check("I have not passed out", {"fainted": True})
    assert out["fainted"] is None and "'passed out'" in notes[0]


def test_extract_wires_negation(client) -> None:
    """Acceptance: 'bukhar nahi hai' with model output fever=true → uncertain."""
    body = {
        "question_id": "jp_fever",
        "language": "hi",
        "text": "bukhar nahi hai",
        "question_text_en": "Do you have fever?",
        "slots": [{"name": "fever", "type": "bool"}],
    }
    with respx.mock() as mock:
        mock.post(url__regex=r".*/api/chat$").mock(
            return_value=httpx.Response(200, json={"message": {"content": json.dumps({"fever": True})}})
        )
        out = client.post("/extract", json=body).json()
    assert out["status"] == "uncertain" and out["slots"] == {"fever": None}
    assert out["notes"] == ["fever=true dropped: negation 'nahi hai' near 'bukhar'"]
