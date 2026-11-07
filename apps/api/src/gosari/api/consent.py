"""승인 발급·실행 결과 조회. 사용자 UI 경로만 승인 가능 (SRS §12.1)."""

from typing import Any

from litestar import Controller, Request, get, post
from litestar.response import Response

from gosari.api.deps import check_origin, current_session
from gosari.domain.errors import GosariError
from gosari.personal import ActionResult, Consent
from gosari.personal.approval import issue_consent


class ConsentsController(Controller):
    path = "/consents"

    @post("/", sync_to_thread=True)
    def create(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> Response[Consent]:
        check_origin(request)
        session = current_session(request)
        allowed = {"preview_id", "preview_hash", "decision"}
        if set(data) - allowed:
            raise GosariError("UNKNOWN_FIELD", {"fields": sorted(set(data) - allowed)})
        consent = issue_consent(
            session,
            str(data.get("preview_id", "")),
            str(data.get("preview_hash", "")),
            str(data.get("decision", "")),
        )
        return Response(
            consent,
            status_code=201,
            headers={"Cache-Control": "no-store"},
        )


class ActionsController(Controller):
    path = "/actions"

    @get("/{action_id:str}", sync_to_thread=True)
    def get_action(
        self, request: Request[Any, Any, Any], action_id: str
    ) -> Response[ActionResult]:
        session = current_session(request)
        result = session.actions.get(action_id)
        if result is None:
            raise GosariError("RESOURCE_NOT_FOUND")
        return Response(result, headers={"Cache-Control": "no-store"})
