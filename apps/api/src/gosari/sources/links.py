"""조사가·상품 표시가 — 공식 원문 링크 우선 (SRS §7.4, 기술설계 §8).

자동 취득·재배포 권리가 확인되지 않았으므로 링크 카드만 제공한다.
링크만 제공한 카드는 source_mode=link, link_status=link_ready,
data_status=unavailable(LINK_ONLY)로 반환한다.
"""

from typing import Any

SURVEY_LINKS = [
    {
        "channel": "survey",
        "source_id": "forestinfo",
        "source_url": "https://www.forestinfo.or.kr/",
        "title": "산림조합중앙회 임산물가격정보 — 지역 조사가",
        "description": "조사지역·등급·유통단계별 가격. "
        "생산지 가격은 출하기 입력값이 이후에도 표시될 수 있음.",
        "rights_status": "link_only",
    }
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


def retail_link_cards() -> list[dict[str, Any]]:
    return [{**link, "checked_at": None, "link_status": "link_ready"} for link in RETAIL_LINKS]


def retail_sample_cards(products: list[dict[str, Any]], verified_on: str) -> list[dict[str, Any]]:
    """검증된 표본 수치 — 표본의 범위·시점을 별도로 밝힌다. 최신 가격이 아니다."""
    cards = []
    for p in products:
        cards.append(
            {
                "channel": "retail",
                "source_id": p.get("source"),
                "source_url": p.get("url"),
                "product": p.get("product"),
                "origin_label_raw": p.get("originLabel"),
                "form": p.get("form"),
                "product_option": p.get("optionLabel"),
                "net_weight_value": p.get("weight_g"),
                "net_weight_unit": "g",
                "price_value": p.get("displayPriceWon"),
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
