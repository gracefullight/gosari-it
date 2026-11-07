"""지인 목록. 변경은 기존 미리보기·승인 절차를 따른다."""

from typing import Any

from litestar import Controller, Request, get, post
from litestar.response import Response
from pydantic import BaseModel

from gosari.api.deps import check_origin, current_session
from gosari.api.personal import PreviewResponse, _commit_body, _preview_response
from gosari.domain.errors import GosariError
from gosari.personal import ActionResult, PersonalContact, contacts
from gosari.personal.approval import commit


class ContactListResponse(BaseModel):
    contacts: list[PersonalContact]


class ContactsController(Controller):
    path = "/contacts"

    @get("/", sync_to_thread=True)
    def list_contacts(self, request: Request[Any, Any, Any]) -> Response[ContactListResponse]:
        session = current_session(request)
        return Response(
            ContactListResponse(
                contacts=sorted(session.contacts.values(), key=lambda contact: contact.name)
            ),
            headers={"Cache-Control": "no-store"},
        )

    @post("/prepare", sync_to_thread=True)
    def prepare(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> PreviewResponse:
        check_origin(request)
        session = current_session(request)
        action = data.get("action", "create")
        payload = data.get("payload", {})
        if not isinstance(payload, dict):
            raise GosariError("INVALID_INPUT")
        if action == "create":
            preview = contacts.prepare_create(session, payload)
        elif action == "update":
            preview = contacts.prepare_update(session, data.get("contact_id", ""), payload)
        elif action == "delete":
            preview = contacts.prepare_delete(session, data.get("contact_id", ""))
        else:
            raise GosariError("INVALID_INPUT", {"fields": ["action"]})
        return _preview_response(preview)

    @post("/commit", sync_to_thread=True, status_code=200)
    def commit(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> Response[ActionResult]:
        check_origin(request)
        session = current_session(request)
        body = _commit_body(data)
        if body["action"] not in {"contact.create", "contact.update", "contact.delete"}:
            raise GosariError("ACTION_NOT_ALLOWED")
        result = commit(
            session,
            body["consent_id"],
            body["preview_id"],
            body["action"],
            body["target_id"],
            int(body["target_revision"]),
            body["preview_hash"],
            contacts.execute,
        )
        return Response(result, headers={"Cache-Control": "no-store"})
