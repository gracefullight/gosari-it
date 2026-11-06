"""개인 작업 라우트 — 수첩·지역·나눔. prepare는 무변경, commit은 승인 결합 필수."""

from datetime import date
from typing import Any

from litestar import Controller, Request, get, post
from litestar.response import Response

from gosari.api.deps import check_origin, current_session
from gosari.config import get_settings
from gosari.domain.errors import GosariError
from gosari.personal import notebook, regions, share
from gosari.personal.approval import commit


def _preview_response(preview: Any) -> dict[str, Any]:
    return {
        "preview_id": preview.preview_id,
        "action": preview.action,
        "target_id": preview.target_id,
        "target_revision": preview.expected_revision,
        "schema_version": preview.schema_version,
        "display_payload": preview.display_payload,
        "preview_hash": preview.preview_hash,
        "expires_at": preview.expires_at.isoformat(),
        "action_status": "preview",
    }


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

    @post("/prepare")
    async def prepare(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> dict[str, Any]:
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

    @post("/commit", status_code=200)
    async def commit(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> Response[dict[str, Any]]:
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
        return Response(result.model_dump(mode="json"), headers={"Cache-Control": "no-store"})

    @get("/")
    async def list_entries(
        self,
        request: Request[Any, Any, Any],
        start: str | None = None,
        end: str | None = None,
        alias: str | None = None,
    ) -> Response[dict[str, Any]]:
        session = current_session(request)
        entries = notebook.search(
            session,
            start=date.fromisoformat(start) if start else None,
            end=date.fromisoformat(end) if end else None,
            alias=alias,
        )
        return Response(
            {"entries": [e.model_dump(mode="json") for e in entries]},
            headers={"Cache-Control": "no-store"},
        )

    @get("/{record_id:str}")
    async def get_entry(
        self, request: Request[Any, Any, Any], record_id: str
    ) -> Response[dict[str, Any]]:
        session = current_session(request)
        entry = session.notebook.get(record_id)
        if entry is None:
            raise GosariError("RESOURCE_NOT_FOUND")
        return Response(entry.model_dump(mode="json"), headers={"Cache-Control": "no-store"})

    @post("/recall")
    async def recall(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> Response[dict[str, Any]]:
        check_origin(request)
        session = current_session(request)
        entries = notebook.search(
            session,
            start=date.fromisoformat(data["start"]) if data.get("start") else None,
            end=date.fromisoformat(data["end"]) if data.get("end") else None,
            alias=data.get("alias"),
        )
        return Response(
            {
                "entries": [e.model_dump(mode="json") for e in entries],
                "count": len(entries),
                "notice": "현재 세션의 로컬 회고입니다. 외부 원문 전송 없음.",
            },
            headers={"Cache-Control": "no-store"},
        )

    @post("/export/prepare")
    async def export_prepare(self, request: Request[Any, Any, Any]) -> dict[str, Any]:
        check_origin(request)
        current_session(request)
        raise GosariError("CAPABILITY_DISABLED", {"reason": "NOTEBOOK_EXPORT_POLICY_UNCONFIRMED"})

    @post("/import/prepare")
    async def import_prepare(self, request: Request[Any, Any, Any]) -> dict[str, Any]:
        check_origin(request)
        current_session(request)
        raise GosariError("CAPABILITY_DISABLED", {"reason": "NOTEBOOK_IMPORT_POLICY_UNCONFIRMED"})


class RegionsController(Controller):
    path = "/regions"

    @post("/prepare")
    async def prepare(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> dict[str, Any]:
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

    @post("/commit", status_code=200)
    async def commit(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> Response[dict[str, Any]]:
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
        return Response(result.model_dump(mode="json"), headers={"Cache-Control": "no-store"})

    @get("/")
    async def list_regions(self, request: Request[Any, Any, Any]) -> Response[dict[str, Any]]:
        session = current_session(request)
        return Response(
            {"regions": [r.model_dump(mode="json") for r in session.regions.values()]},
            headers={"Cache-Control": "no-store"},
        )


class ShareController(Controller):
    path = "/share"

    @post("/prepare", status_code=200)
    async def prepare(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> Response[dict[str, Any]]:
        check_origin(request)
        session = current_session(request)
        preview, display = share.prepare(session, data)
        return Response(
            {**_preview_response(preview), "display": display},
            headers={"Cache-Control": "no-store"},
        )

    @post("/commit", status_code=200)
    async def commit(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> Response[dict[str, Any]]:
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
        return Response(result.model_dump(mode="json"), headers={"Cache-Control": "no-store"})

    @get("/")
    async def list_drafts(self, request: Request[Any, Any, Any]) -> Response[dict[str, Any]]:
        session = current_session(request)
        return Response(
            {"drafts": [d.model_dump(mode="json") for d in session.share_drafts.values()]},
            headers={"Cache-Control": "no-store"},
        )

    @post("/file/commit")
    async def file_commit(self, request: Request[Any, Any, Any]) -> dict[str, Any]:
        check_origin(request)
        current_session(request)
        raise GosariError("CAPABILITY_DISABLED", {"reason": "SHARE_FILE_POLICY_UNCONFIRMED"})
