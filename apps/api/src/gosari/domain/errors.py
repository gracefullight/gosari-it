"""SRS §8.7 HTTP·업무 오류 매핑. 내부 예외 메시지를 그대로 노출하지 않는다."""

from typing import Any

ERROR_HTTP_MAP: dict[str, int] = {
    "INVALID_INPUT": 400,
    "UNKNOWN_FIELD": 400,
    "SESSION_REQUIRED": 401,
    "LOGIN_FAILED": 401,
    "ORIGIN_DENIED": 403,
    "POLICY_BLOCKED": 403,
    "ACTION_NOT_ALLOWED": 403,
    "RESOURCE_NOT_FOUND": 404,
    "REVISION_CONFLICT": 409,
    "LOGIN_ID_TAKEN": 409,
    "PREVIEW_MISMATCH": 409,
    "CONSENT_REUSED_DIFFERENTLY": 409,
    "SESSION_EXPIRED": 410,
    "PREVIEW_EXPIRED": 410,
    "INPUT_TOO_LARGE": 413,
    "FILE_TOO_LARGE": 413,
    "UNIT_UNRESOLVED": 422,
    "STATION_AMBIGUOUS": 422,
    "QUALITY_CONFLICT": 422,
    "LOCAL_BUSY": 429,
    "SOURCE_RATE_LIMIT": 429,
    "BUDGET_EXCEEDED": 429,
    "UPSTREAM_SCHEMA_CHANGED": 502,
    "UPSTREAM_FAILED": 502,
    "MODEL_UNAVAILABLE": 503,
    "DATABASE_UNAVAILABLE": 503,
    "CAPABILITY_DISABLED": 503,
    "JOB_DEADLINE_EXCEEDED": 504,
}

SAFE_MESSAGES: dict[str, str] = {
    "INVALID_INPUT": "입력 형식을 확인해 주세요.",
    "UNKNOWN_FIELD": "허용되지 않는 필드가 있습니다.",
    "SESSION_REQUIRED": "현재 로컬 세션이 필요합니다.",
    "LOGIN_FAILED": "아이디 또는 비밀번호가 맞지 않습니다.",
    "ORIGIN_DENIED": "허용되지 않은 요청 출처입니다.",
    "POLICY_BLOCKED": "정책상 허용되지 않는 작업입니다.",
    "ACTION_NOT_ALLOWED": "수행할 수 없는 작업입니다.",
    "RESOURCE_NOT_FOUND": "대상을 찾을 수 없습니다.",
    "REVISION_CONFLICT": "다른 변경이 먼저 반영되었습니다. 새 미리보기가 필요합니다.",
    "LOGIN_ID_TAKEN": "이미 사용 중인 아이디입니다.",
    "PREVIEW_MISMATCH": "미리보기 내용이 일치하지 않습니다. 새 미리보기가 필요합니다.",
    "CONSENT_REUSED_DIFFERENTLY": "다른 명령에 승인을 재사용할 수 없습니다.",
    "SESSION_EXPIRED": "세션이 만료되었습니다. 이전 개인 기록은 복구되지 않습니다.",
    "PREVIEW_EXPIRED": "미리보기가 만료되었습니다. 다시 준비해 주세요.",
    "INPUT_TOO_LARGE": "입력이 허용 길이를 초과했습니다.",
    "FILE_TOO_LARGE": "파일이 허용 크기를 초과했습니다.",
    "UNIT_UNRESOLVED": "단위를 확정할 수 없습니다.",
    "STATION_AMBIGUOUS": "관측소 연결이 모호합니다. 확인이 필요합니다.",
    "QUALITY_CONFLICT": "자료 품질 충돌이 있습니다. 확인이 필요합니다.",
    "LOCAL_BUSY": "로컬 작업이 많아 잠시 후 다시 시도해 주세요.",
    "SOURCE_RATE_LIMIT": "원천 호출 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.",
    "BUDGET_EXCEEDED": "호출 예산을 초과했습니다.",
    "UPSTREAM_SCHEMA_CHANGED": "원천 응답 구조가 변경되었습니다.",
    "UPSTREAM_FAILED": "원천 조회에 실패했습니다.",
    "MODEL_UNAVAILABLE": "외부 모델을 사용할 수 없습니다. 검증된 표·근거만 제공합니다.",
    "DATABASE_UNAVAILABLE": (
        "지금은 자료를 불러오거나 저장할 수 없습니다. 잠시 후 다시 시도해 주세요."
    ),
    "CAPABILITY_DISABLED": "비활성화된 기능입니다.",
    "JOB_DEADLINE_EXCEEDED": "작업 제한 시간을 초과했습니다. 기존 변경 상태를 먼저 확인해 주세요.",
}


class GosariError(Exception):
    code: str
    extra: dict[str, Any]

    def __init__(self, code: str, extra: dict[str, Any] | None = None) -> None:
        self.code = code
        self.extra = extra or {}
        super().__init__(SAFE_MESSAGES.get(code, code))

    @property
    def http_status(self) -> int:
        return ERROR_HTTP_MAP.get(self.code, 500)

    @property
    def safe_message(self) -> str:
        return SAFE_MESSAGES.get(self.code, "요청을 처리할 수 없습니다.")

    def to_body(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.safe_message, **self.extra}
