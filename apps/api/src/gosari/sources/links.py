"""조사가·상품 표시가 — 공식 원문 링크 우선 (SRS §7.4, 기술설계 §8).

자동 취득·재배포 권리가 확인되지 않았으므로 링크 카드만 제공한다.
링크만 제공한 카드는 source_mode=link, link_status=link_ready,
data_status=unavailable(LINK_ONLY)로 반환한다.
"""

from decimal import Decimal
from typing import Any

from gosari.quality.calculation import price_per_kg

SURVEY_LINKS = [
    {
        "channel": "survey",
        "source_id": "forestinfo",
        "source_url": "https://www.forestinfo.or.kr/",
        "title": "산림조합중앙회 임산물가격정보 지역 조사가",
        "rights_status": "link_only",
    }
]

SURVEY_SAMPLES = [
    {
        "channel": "survey",
        "source_id": "forestinfo",
        "source_url": "https://www.forestinfo.or.kr/",
        "title": "제주 생고사리 (상) 생산지 조사가",
        "survey_region": "제주",
        "form": "생고사리",
        "survey_grade": "상",
        "survey_stage": "생산지",
        "net_weight_value": 1000,
        "net_weight_unit": "g",
        "price_value": 11500,
        "price_per_kg_value": 11500,
        "currency": "KRW",
        "price_basis": "산림조합 지역 조사가 (생산지)",
        "price_as_of": "2026-11-04",
        "rights_status": "link_only",
    },
    {
        "channel": "survey",
        "source_id": "forestinfo",
        "source_url": "https://www.forestinfo.or.kr/",
        "title": "제주 생고사리 (상) 도매지 조사가",
        "survey_region": "제주",
        "form": "생고사리",
        "survey_grade": "상",
        "survey_stage": "도매지",
        "net_weight_value": 1000,
        "net_weight_unit": "g",
        "price_value": 15000,
        "price_per_kg_value": 15000,
        "currency": "KRW",
        "price_basis": "산림조합 지역 조사가 (도매지)",
        "price_as_of": "2026-11-04",
        "rights_status": "link_only",
    },
    {
        "channel": "survey",
        "source_id": "forestinfo",
        "source_url": "https://www.forestinfo.or.kr/",
        "title": "제주 생고사리 (상) — 소비지 조사가",
        "survey_region": "제주",
        "form": "생고사리",
        "survey_grade": "상",
        "survey_stage": "소비지",
        "net_weight_value": 1000,
        "net_weight_unit": "g",
        "price_value": 18500,
        "price_per_kg_value": 18500,
        "currency": "KRW",
        "price_basis": "산림조합 지역 조사가 (소비지)",
        "price_as_of": "2026-11-04",
        "rights_status": "link_only",
    },
]

RETAIL_LINKS = [
    {
        "channel": "retail",
        "source_id": "tamnao",
        "source_url": "https://www.tamnao.com/web/sv/detailPrdt.do?prdtNum=SV00004060",
        "title": "탐나오 — 서귀포산림조합 제주 한라산 건고사리",
        "rights_status": "link_only",
    },
    {
        "channel": "retail",
        "source_id": "oasis",
        "source_url": "https://m.oasis.co.kr/product/detail/20342",
        "title": "오아시스마켓 — 제주 건고사리 80g",
        "rights_status": "link_only",
    },
]


def survey_link_cards() -> list[dict[str, Any]]:
    return [{**link, "checked_at": None, "link_status": "link_ready"} for link in SURVEY_LINKS]


def survey_sample_cards() -> list[dict[str, Any]]:
    return [
        {**card, "checked_at": None, "source_mode": "replay", "link_status": "link_ready"}
        for card in SURVEY_SAMPLES
    ]


def retail_link_cards() -> list[dict[str, Any]]:
    return [{**link, "checked_at": None, "link_status": "link_ready"} for link in RETAIL_LINKS]


def retail_sample_cards(products: list[dict[str, Any]], verified_on: str) -> list[dict[str, Any]]:
    """검증된 표본 수치 — 표본의 범위·시점을 별도로 밝힌다. 최신 가격이 아니다."""
    cards = []
    for p in products:
        weight_g = p.get("weight_g")
        price_won = p.get("displayPriceWon")
        per_kg = None
        if weight_g is not None and price_won is not None:
            converted = price_per_kg(Decimal(str(price_won)), Decimal(str(weight_g)))
            if converted is not None:
                per_kg = (
                    int(converted)
                    if converted == converted.to_integral_value()
                    else float(converted)
                )
        cards.append(
            {
                "channel": "retail",
                "source_id": p.get("source"),
                "source_url": p.get("url"),
                "product": p.get("product"),
                "origin_label_raw": p.get("originLabel"),
                "form": p.get("form"),
                "product_option": p.get("optionLabel"),
                "net_weight_value": weight_g,
                "net_weight_unit": "g",
                "price_value": price_won,
                "price_per_kg_value": per_kg,
                "conversion_formula": (
                    f"{price_won:,}원 ÷ ({weight_g}g / 1,000g) = {per_kg:,}원/kg "
                    f"(내용물 기준, 배송비·쿠폰 별도)"
                    if per_kg is not None and price_won is not None and weight_g is not None
                    else None
                ),
                "currency": "KRW",
                "price_basis": "상품 표시 판매가",
                "shipping_value": p.get("shippingWon"),
                "shipping_condition": "표본 확인 당시",
                "coupon_price": p.get("couponPriceWon"),
                "coupon_condition": "조건부" if p.get("couponConditional") else None,
                "price_as_of": p.get("observationDate"),
                "checked_at": None,
                "verified_on": verified_on,
                "transaction_verified": p.get("transactionVerified", False),
                "source_mode": "replay",
                "link_status": "link_ready",
            }
        )
    return cards
