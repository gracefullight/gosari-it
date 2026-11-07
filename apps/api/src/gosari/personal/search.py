"""세션 내 개인 자료 검색. 로컬 모델만 사용하며 공개 캐시·LLM과 분리한다."""

import math
import os
import re
import threading
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from gosari.config import get_settings
from gosari.sessions import Session


class PersonalSearchItem(BaseModel):
    kind: Literal["notebook", "region", "contact", "share"]
    id: str
    title: str
    snippet: str
    date: str | None = None


class PersonalSearchResponse(BaseModel):
    query: str
    mode: Literal["hybrid", "keyword"]
    items: list[PersonalSearchItem]
    answer: str


def is_personal_search(text: str) -> bool:
    compact = text.replace(" ", "")
    private = any(
        word in compact
        for word in (
            "나의",
            "우리",
            "지인",
            "수첩",
            "스팟",
            "나눔이력",
            "관심지역",
            "방문지역",
        )
    ) or bool(
        re.search(r"(?:^|\s)(?:내|내가)(?:\s|등록|관심|수첩|나눔|기록|지인|스팟|방문|명당)", text)
    )
    read = any(
        word in compact
        for word in (
            "찾",
            "알려",
            "보여",
            "조회",
            "검색",
            "회고",
            "이력",
            "목록",
            "어디",
            "언제",
            "누구",
        )
    )
    write = any(
        word in compact.replace("등록한", "").replace("등록된", "").replace("등록스팟", "스팟")
        for word in ("등록", "저장", "작성", "추가", "수정", "삭제", "기록해", "적어")
    )
    return private and read and not write


def _tokens(text: str) -> list[str]:
    stop = {
        "내",
        "나의",
        "우리",
        "좀",
        "찾아",
        "알려줘",
        "보여줘",
        "해줘",
        "검색",
        "조회",
        "목록",
        "이력",
        "찾아줘",
        "어디",
        "언제",
        "누구",
        "관심지역",
        "방문지역",
        "스팟",
        "지역",
        "지인",
        "나눔",
        "수첩",
        "기록",
        "등록한",
        "등록된",
        "등록스팟",
    }
    result = []
    for token in re.findall(r"[가-힣a-z0-9]+", text.casefold()):
        if token in stop:
            continue
        for suffix in (
            "에서는",
            "했던",
            "에게",
            "에서",
            "으로",
            "이랑",
            "께",
            "를",
            "을",
            "의",
            "은",
            "는",
            "에",
        ):
            if token.endswith(suffix) and len(token) > len(suffix) + 1:
                token = token[: -len(suffix)]
                break
        result.append(token)
    return result


def _documents(session: Session) -> list[tuple[PersonalSearchItem, str]]:
    docs: list[tuple[PersonalSearchItem, str]] = []
    with session.lock:
        for entry in session.notebook.values():
            day = entry.experience_date.isoformat()
            text = " ".join(
                (
                    "수첩 채취 기록",
                    day,
                    entry.activity_text,
                    " ".join(entry.companion_aliases),
                    entry.location_address or "",
                    str(entry.amount_value or ""),
                    entry.amount_unit or "",
                )
            )
            docs.append(
                (
                    PersonalSearchItem(
                        kind="notebook",
                        id=entry.record_id,
                        title=f"{day} · {entry.activity_text[:40]}",
                        snippet=text.removeprefix("수첩 채취 기록 ")[:240],
                        date=day,
                    ),
                    text,
                )
            )
        for region in session.regions.values():
            day = region.visited_on.isoformat() if region.visited_on else None
            label = "방문 지역" if region.kind == "existing" else "관심 지역"
            text = " ".join(
                ("스팟 지역", label, region.local_alias, region.public_area_code or "", day or "")
            )
            docs.append(
                (
                    PersonalSearchItem(
                        kind="region",
                        id=region.region_id,
                        title=region.local_alias,
                        snippet=" · ".join(v for v in (label, region.public_area_code, day) if v),
                        date=day,
                    ),
                    text,
                )
            )
        for contact in session.contacts.values():
            text = " ".join(("지인 연락처", contact.name, contact.relationship, contact.notes))
            docs.append(
                (
                    PersonalSearchItem(
                        kind="contact",
                        id=contact.contact_id,
                        title=contact.name,
                        snippet=f"{contact.relationship} · {contact.notes}".rstrip(" ·")[:240],
                    ),
                    text,
                )
            )
        for draft in session.share_drafts.values():
            lines = []
            dates = []
            for item in draft.items:
                day = item.occurred_on.isoformat() if item.occurred_on else ""
                if day:
                    dates.append(day)
                state = "전달 완료 나눠준 나눔" if item.status == "delivered" else "나눔 예정 계획"
                contact = session.contacts.get(item.contact_id or "")
                lines.append(
                    " ".join(
                        v
                        for v in (
                            item.recipient_alias,
                            contact.relationship if contact else "",
                            f"{item.amount_value}{item.amount_unit}",
                            state,
                            day,
                            item.planned_delivery or "",
                            item.optional_role_note or "",
                        )
                        if v
                    )
                )
            text = " · ".join(lines)
            docs.append(
                (
                    PersonalSearchItem(
                        kind="share",
                        id=draft.share_draft_id,
                        title="나눔 · " + ", ".join(item.recipient_alias for item in draft.items),
                        snippet=text[:240],
                        date=max(dates) if dates else draft.prepared_at.date().isoformat(),
                    ),
                    text,
                )
            )
    return docs


class LocalPersonalRanker:
    def __init__(self) -> None:
        self._model: Any = None
        self._failed = False
        self._lock = threading.Lock()

    def _cached_path(self) -> Path | None:
        configured = Path(get_settings().embedding_model_path).expanduser()
        if configured.is_dir():
            return configured
        hub = Path(
            os.environ.get(
                "HF_HUB_CACHE",
                str(
                    Path(os.environ.get("HF_HOME", str(Path.home() / ".cache/huggingface"))) / "hub"
                ),
            )
        )
        snapshots = hub / "models--intfloat--multilingual-e5-small" / "snapshots"
        if not snapshots.is_dir():
            return None
        return next(
            (
                p
                for p in sorted(snapshots.iterdir(), reverse=True)
                if (p / "config.json").is_file()
                and any((p / f).is_file() for f in ("model.safetensors", "pytorch_model.bin"))
            ),
            None,
        )

    def similarities(self, query: str, docs: list[str]) -> list[float] | None:
        if self._failed:
            return None
        with self._lock:
            try:
                if self._model is None:
                    path = self._cached_path()
                    if path is None:
                        self._failed = True
                        return None
                    import torch
                    from sentence_transformers import SentenceTransformer

                    torch.set_num_threads(2)
                    self._model = SentenceTransformer(
                        str(path), device="cpu", local_files_only=True
                    )
                # Personal texts and vectors stay request-local, without a shared index.
                vectors = self._model.encode(
                    ["query: " + query, *("passage: " + text for text in docs)],
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    batch_size=16,
                )
                scores = [
                    float(sum(float(a) * float(b) for a, b in zip(vectors[0], v, strict=True)))
                    for v in vectors[1:]
                ]
                return scores if all(math.isfinite(score) for score in scores) else None
            except Exception:
                self._failed = True
                return None


local_ranker = LocalPersonalRanker()


PersonalSearchKind = Literal["notebook", "region", "contact", "share", "all"]


def search_personal(
    session: Session, query: str, limit: int = 20, kind: PersonalSearchKind | None = None
) -> PersonalSearchResponse:
    docs = _documents(session)
    terms = _tokens(query)
    categories = [kind] if kind and kind != "all" else []
    for category, aliases in (
        ("notebook", ("수첩", "채취기록")),
        ("region", ("지역", "스팟", "명당")),
        ("contact", ("지인", "연락처")),
        ("share", ("나눔", "나눠", "나눈", "드린")),
    ):
        if kind is None and any(alias in query.replace(" ", "") for alias in aliases):
            categories.append(category)
    if categories:
        docs = [(item, text) for item, text in docs if item.kind in categories]
    if not docs:
        return PersonalSearchResponse(
            query=query, mode="keyword", items=[], answer="조건에 맞는 기록이 없습니다."
        )
    lexical = [
        sum(
            2 if token in item.title.casefold() else 1 if token in text.casefold() else 0
            for token in terms
        )
        for item, text in docs
    ]
    semantic = local_ranker.similarities(query, [text for _, text in docs]) if terms else None
    candidates = [
        i
        for i in range(len(docs))
        if lexical[i] > 0 or not terms or (semantic is not None and semantic[i] >= 0.80)
    ]
    keyword_order = sorted(candidates, key=lambda i: lexical[i], reverse=True)
    scores = {i: 1 / (60 + rank) for rank, i in enumerate(keyword_order, 1)}
    if semantic is not None:
        for rank, i in enumerate(sorted(candidates, key=lambda i: semantic[i], reverse=True), 1):
            scores[i] += 1 / (60 + rank)
    ordered = sorted(candidates, key=lambda i: (scores[i], docs[i][0].date or ""), reverse=True)
    items = [docs[i][0] for i in ordered[:limit]]
    return PersonalSearchResponse(
        query=query,
        mode="hybrid" if semantic is not None else "keyword",
        items=items,
        answer=f"관련 기록 {len(items)}건을 찾았습니다."
        if items
        else "조건에 맞는 기록이 없습니다.",
    )
