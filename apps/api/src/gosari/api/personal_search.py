"""로그인 세션 내부 개인 자료 검색. 공개 분석과 외부 모델을 호출하지 않는다."""

from typing import Any

from litestar import Controller, Request, post
from litestar.response import Response
from pydantic import BaseModel, Field

from gosari.api.deps import check_origin, current_session
from gosari.domain.errors import GosariError
from gosari.personal.search import PersonalSearchResponse, search_personal


class PersonalSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=20, ge=1, le=100)


class PersonalSearchController(Controller):
    path = "/personal"

    @post("/search", sync_to_thread=True, status_code=200)
    def search(
        self, request: Request[Any, Any, Any], data: PersonalSearchRequest
    ) -> Response[PersonalSearchResponse]:
        check_origin(request)
        session = current_session(request)
        if not data.query.strip():
            raise GosariError("INVALID_INPUT", {"fields": ["query"]})
        return Response(
            search_personal(session, data.query, data.limit), headers={"Cache-Control": "no-store"}
        )
