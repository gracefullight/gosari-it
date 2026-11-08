import copy
import json
import unicodedata
from datetime import UTC, datetime

import pytest

from gosari.cache.dialogue_guards import context_hash, guard_fingerprint, normalize_text

NOW = datetime(2026, 11, 8, 3, tzinfo=UTC)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("제주 고사리 100g 판매가 알려줘", "제주도 고사리 100그램 소매가 보여줘"),
        ("내일 오전 9시 성산 날씨 비교해줘", "2026-11-09 09:00 성산 기상 비교해주세요"),
        ("탐나오 건고사리 1kg 판매가", "탐나오 건고사리 1000g 소매가"),
        ("내일 오전9시 애월날씨알려줘", "내일 오전9시 애월날씨알려주세요"),
        ("내일 오전9시 애월날씨알려줘", "내일 오전9시 애월날씨어때"),
    ],
)
def test_equivalent_public_operands(left, right):
    assert guard_fingerprint(left, now=NOW) is not None
    assert guard_fingerprint(left, now=NOW) == guard_fingerprint(right, now=NOW)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("내일 성산 날씨", "모레 성산 날씨"),
        ("내일 오전 9시 성산 날씨", "내일 오후 9시 성산 날씨"),
        ("내일 성산 날씨", "내일 서귀포 날씨"),
        ("제주 고사리 판매가", "제주시 고사리 판매가"),
        ("한라산남벽 날씨", "한라산북벽 날씨"),
        ("고사리 100g 판매가", "고사리 200g 판매가"),
        ("생고사리 판매가", "건고사리 판매가"),
        ("100g 말고 200g 판매가", "200g 말고 100g 판매가"),
        ("서귀포 말고 애월 날씨", "애월 말고 서귀포 날씨"),
        ("비 오는 곳", "비 안 오는 곳"),
        ("기온 20도 이하", "기온 20도 이상"),
        ("강수확률 최저", "풍속 최저"),
        ("성산 사유지", "성산 국유지"),
        ("서울가락 도매가", "부산엄궁 도매가"),
    ],
)
def test_changed_conditions_never_share_a_semantic_guard(left, right):
    left_key = guard_fingerprint(left, now=NOW)
    right_key = guard_fingerprint(right, now=NOW)
    assert left_key is None or right_key is None or left_key != right_key


def test_anduk_is_a_public_place_not_a_negative_prefix():
    assert guard_fingerprint("안덕 날씨", now=NOW)
    assert guard_fingerprint("안덕 날씨", now=NOW) != guard_fingerprint("안 날씨", now=NOW)


def test_month_day_without_year_is_distinct_from_either_explicit_year():
    late_december = datetime(2026, 12, 30, 3, tzinfo=UTC)
    unspecified = guard_fingerprint("1월 1일 애월 날씨", now=late_december)
    assert unspecified is not None
    for year in (2026, 2027):
        assert unspecified != guard_fingerprint(f"{year}-01-01 애월 날씨", now=late_december)


@pytest.mark.parametrize(
    "question",
    [
        "내 수첩 가격",
        "엄마 밭 날씨",
        "010-1234-5678 가격",
        "a@example.com 날씨",
        "독특한 미확인 조건으로 가격",
    ],
)
def test_private_or_unrecognized_conditions_disable_semantic_only(question):
    assert guard_fingerprint(question, now=NOW) is None


def public_history(call_id="call-a", request_id="request-a", quantity=100):
    return [
        {"role": "user", "content": "탐나오 건고사리 판매가 알려줘"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": "retail_lookup",
                        "arguments": json.dumps({"product_option": f"{quantity}g"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(
                {
                    "request_id": request_id,
                    "conditions": {"product_option": f"{quantity}g"},
                    "facts": [{"id": "price_1", "value": 17000, "unit": "원"}],
                }
            ),
        },
        {"role": "assistant", "content": "탐나오 상품 가격을 확인했어요."},
    ]


def test_context_preserves_facts_conditions_and_turns_but_discards_transport_ids():
    original = public_history()
    assert context_hash(original) == context_hash(public_history("another-call", "another-request"))
    assert context_hash(original) != context_hash(public_history(quantity=1000))
    changed = copy.deepcopy(original)
    parsed = json.loads(changed[2]["content"])
    parsed["facts"][0]["value"] = 18000
    changed[2]["content"] = json.dumps(parsed)
    assert context_hash(original) != context_hash(changed)
    assert context_hash(original) != context_hash([])


@pytest.mark.parametrize(
    "tool", ["search_personal_records", "open_personal_form", "open_street_view"]
)
def test_private_or_link_tool_history_is_not_shared(tool):
    history = public_history()
    history[1]["tool_calls"][0]["function"]["name"] = tool
    assert context_hash(history) is None


def test_private_content_and_incomplete_pairs_bypass():
    assert context_hash([{"role": "user", "content": "내 관심지역은 어디야"}]) is None
    assert context_hash(public_history()[:2]) is None
    assert context_hash(public_history()[2:]) is None
    assert context_hash([{"role": "system", "content": "private"}]) is None


def test_normalization_is_nfc_and_whitespace_only():
    text = "제주 고사리"
    assert normalize_text(unicodedata.normalize("NFD", text) + "\n ") == text
    assert context_hash([]) == context_hash([])


def test_actual_dialogue_normalization_keeps_public_followups_cacheable():
    from gosari.agent.dialogue import normalize_dialogue_history

    original = public_history()
    text = original[-1]["content"]
    protocol = [
        *original[:-1],
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "respond-1",
                    "type": "function",
                    "function": {
                        "name": "respond",
                        "arguments": json.dumps({"text": text, "claims": []}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "respond-1",
            "content": json.dumps({"status": "responded", "accepted_text": text}),
        },
        original[-1],
    ]
    assert context_hash(normalize_dialogue_history(protocol)) == context_hash(original)
