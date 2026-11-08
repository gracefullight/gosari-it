"""개인 작업 라우트 — 수첩·지역·나눔. prepare는 무변경, commit은 승인 결합 필수."""

from datetime import date, datetime
from typing import Any, Literal

from litestar import Controller, Request, get, post
from litestar.response import Response
from pydantic import BaseModel

from gosari.api.deps import check_origin, current_session
from gosari.config import get_settings
from gosari.domain.errors import GosariError
from gosari.personal import (
    ActionResult,
    NotebookEntry,
    Preview,
    PrivateRegion,
    ShareDraft,
    notebook,
    regions,
    share,
)
from gosari.personal.approval import commit


class PreviewResponse(BaseModel):
    """미리보기 응답 — canonical_payload(개인 원문)는 노출하지 않는다."""

    preview_id: str
    action: str
    target_id: str
    target_revision: int
    schema_version: str
    display_payload: dict[str, Any]
    preview_hash: str
    expires_at: datetime
    action_status: Literal["preview"] = "preview"


class SharePreviewResponse(PreviewResponse):
    """나눔 미리보기 응답 — 로컬 표시용 display 추가."""

    display: dict[str, Any]


class NotebookListResponse(BaseModel):
    entries: list[NotebookEntry]


class NotebookRecallResponse(BaseModel):
    entries: list[NotebookEntry]
    count: int
    notice: str


class RegionListResponse(BaseModel):
    regions: list[PrivateRegion]


class ShareDraftListResponse(BaseModel):
    drafts: list[ShareDraft]


class ShareFileResult(ActionResult):
    """공유 파일 커밋 결과 — 승인된 미리보기 내용 그대로의 파일 1개를 응답에 담는다."""

    filename: str | None = None
    content: str | None = None
    media_type: str = "text/plain; charset=utf-8"


def _preview_response(preview: Preview) -> PreviewResponse:
    return PreviewResponse(
        preview_id=preview.preview_id,
        action=preview.action,
        target_id=preview.target_id,
        target_revision=preview.expected_revision,
        schema_version=preview.schema_version,
        display_payload=preview.display_payload,
        preview_hash=preview.preview_hash,
        expires_at=preview.expires_at,
    )


def _commit_body(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "consent_id",
        "preview_id",
        "action",
        "target_id",
        "target_revision",
        "preview_hash",
    }
    unknown = set(data) - allowed
    if unknown:
        raise GosariError("UNKNOWN_FIELD", {"fields": sorted(unknown)})
    missing = allowed - set(data)
    if missing:
        raise GosariError("INVALID_INPUT", {"fields": sorted(missing)})
    return data


class NotebookController(Controller):
    path = "/notebook"

    @post("/prepare", sync_to_thread=True)
    def prepare(self, request: Request[Any, Any, Any], data: dict[str, Any]) -> PreviewResponse:
        check_origin(request)
        session = current_session(request)
        settings = get_settings()
        action = data.get("action", "create")
        payload = data.get("payload", {})
        if action == "create":
            preview = notebook.prepare_create(session, payload, settings.max_text_length)
        elif action == "update":
            preview = notebook.prepare_update(
                session, data.get("record_id", ""), payload, settings.max_text_length
            )
        elif action == "delete":
            preview = notebook.prepare_delete(session, data.get("record_id", ""))
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
        result = commit(
            session,
            body["consent_id"],
            body["preview_id"],
            body["action"],
            body["target_id"],
            int(body["target_revision"]),
            body["preview_hash"],
            notebook.execute,
        )
        return Response(result, headers={"Cache-Control": "no-store"})

    @get("/", sync_to_thread=True)
    def list_entries(
        self,
        request: Request[Any, Any, Any],
        start: str | None = None,
        end: str | None = None,
        alias: str | None = None,
    ) -> Response[NotebookListResponse]:
        session = current_session(request)
        entries = notebook.search(
            session,
            start=date.fromisoformat(start) if start else None,
            end=date.fromisoformat(end) if end else None,
            alias=alias,
        )
        return Response(
            NotebookListResponse(entries=entries),
            headers={"Cache-Control": "no-store"},
        )

    @get("/{record_id:str}", sync_to_thread=True)
    def get_entry(self, request: Request[Any, Any, Any], record_id: str) -> Response[NotebookEntry]:
        session = current_session(request)
        entry = session.notebook.get(record_id)
        if entry is None:
            raise GosariError("RESOURCE_NOT_FOUND")
        return Response(entry, headers={"Cache-Control": "no-store"})

    @post("/recall", sync_to_thread=True)
    def recall(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> Response[NotebookRecallResponse]:
        check_origin(request)
        session = current_session(request)
        entries = notebook.search(
            session,
            start=date.fromisoformat(data["start"]) if data.get("start") else None,
            end=date.fromisoformat(data["end"]) if data.get("end") else None,
            alias=data.get("alias"),
        )
        return Response(
            NotebookRecallResponse(
                entries=entries,
                count=len(entries),
                notice="",
            ),
            headers={"Cache-Control": "no-store"},
        )

    @post("/export/prepare", sync_to_thread=True)
    def export_prepare(self, request: Request[Any, Any, Any]) -> dict[str, Any]:
        check_origin(request)
        current_session(request)
        raise GosariError("CAPABILITY_DISABLED", {"reason": "NOTEBOOK_EXPORT_POLICY_UNCONFIRMED"})

    @post("/import/prepare", sync_to_thread=True)
    def import_prepare(self, request: Request[Any, Any, Any]) -> dict[str, Any]:
        check_origin(request)
        current_session(request)
        raise GosariError("CAPABILITY_DISABLED", {"reason": "NOTEBOOK_IMPORT_POLICY_UNCONFIRMED"})


class RegionsController(Controller):
    path = "/regions"

    @post("/prepare", sync_to_thread=True)
    def prepare(self, request: Request[Any, Any, Any], data: dict[str, Any]) -> PreviewResponse:
        check_origin(request)
        session = current_session(request)
        action = data.get("action", "create")
        payload = data.get("payload", {})
        if action == "create":
            preview = regions.prepare_create(session, payload)
        elif action == "update":
            preview = regions.prepare_update(session, data.get("region_id", ""), payload)
        elif action == "delete":
            preview = regions.prepare_delete(session, data.get("region_id", ""))
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
        result = commit(
            session,
            body["consent_id"],
            body["preview_id"],
            body["action"],
            body["target_id"],
            int(body["target_revision"]),
            body["preview_hash"],
            regions.execute,
        )
        return Response(result, headers={"Cache-Control": "no-store"})

    @get("/", sync_to_thread=True)
    def list_regions(self, request: Request[Any, Any, Any]) -> Response[RegionListResponse]:
        session = current_session(request)
        return Response(
            RegionListResponse(regions=list(session.regions.values())),
            headers={"Cache-Control": "no-store"},
        )


class ShareController(Controller):
    path = "/share"

    @post("/prepare", sync_to_thread=True, status_code=200)
    def prepare(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> Response[SharePreviewResponse]:
        check_origin(request)
        session = current_session(request)
        action = data.get("action", "save")
        if not isinstance(action, str):
            raise GosariError("INVALID_INPUT", {"fields": ["action"]})
        payload = data.get("payload", data)
        if not isinstance(payload, dict):
            raise GosariError("INVALID_INPUT", {"fields": ["payload"]})
        draft_id = data.get("share_draft_id")
        if draft_id is not None and not isinstance(draft_id, str):
            raise GosariError("INVALID_INPUT", {"fields": ["share_draft_id"]})
        preview, display = share.prepare(session, payload, action, draft_id)
        return Response(
            SharePreviewResponse(**_preview_response(preview).model_dump(), display=display),
            headers={"Cache-Control": "no-store"},
        )

    @post("/commit", sync_to_thread=True, status_code=200)
    def commit(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> Response[ActionResult]:
        check_origin(request)
        session = current_session(request)
        body = _commit_body(data)
        result = commit(
            session,
            body["consent_id"],
            body["preview_id"],
            body["action"],
            body["target_id"],
            int(body["target_revision"]),
            body["preview_hash"],
            share.execute,
        )
        return Response(result, headers={"Cache-Control": "no-store"})

    @get("/", sync_to_thread=True)
    def list_drafts(self, request: Request[Any, Any, Any]) -> Response[ShareDraftListResponse]:
        session = current_session(request)
        return Response(
            ShareDraftListResponse(drafts=list(session.share_drafts.values())),
            headers={"Cache-Control": "no-store"},
        )

    @post("/file/prepare", sync_to_thread=True, status_code=200)
    def file_prepare(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> Response[SharePreviewResponse]:
        check_origin(request)
        session = current_session(request)
        preview, display = share.prepare_file(session, data, get_settings())
        return Response(
            SharePreviewResponse(**_preview_response(preview).model_dump(), display=display),
            headers={"Cache-Control": "no-store"},
        )

    @post("/file/commit", sync_to_thread=True, status_code=200)
    def file_commit(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> Response[ShareFileResult]:
        check_origin(request)
        session = current_session(request)
        if not get_settings().allow_share_file:
            raise GosariError("CAPABILITY_DISABLED", {"reason": "SHARE_FILE_POLICY_UNCONFIRMED"})
        body = _commit_body(data)
        result = commit(
            session,
            body["consent_id"],
            body["preview_id"],
            body["action"],
            body["target_id"],
            int(body["target_revision"]),
            body["preview_hash"],
            share.execute_file,
        )
        payload = session.previews[body["preview_id"]].canonical_payload
        return Response(
            ShareFileResult(
                **result.model_dump(),
                filename=str(payload["filename"]),
                content=str(payload["content"]),
            ),
            headers={"Cache-Control": "no-store", "Content-Disposition": "inline"},
        )
