"""SRS §16.2 설정 계약. 비밀은 *_FILE 우선, 값은 로그/응답에 노출하지 않는다."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


def read_secret_file(path: str | None) -> str | None:
    """file-backed secret을 읽는다. 없거나 비면 None."""
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    value = p.read_text(encoding="utf-8").strip()
    return value or None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 실행
    app_host: str = "127.0.0.1"
    app_port: int = 8765
    app_profile: Literal["center", "replay", "integration_test", "public_scale_test"] = "center"

    # 세션 및 서버(PostgreSQL 18) 내 개인 기록 보관 기간 (기본 365일 — 재방문 시에도 확인 가능)
    session_idle_ttl: int = 31536000
    session_absolute_ttl: int = 31536000

    # 동의 (제안 기본치)
    preview_ttl: int = 600
    consent_ttl: int = 600

    # DB
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "gosari_public"
    db_user: str = "gosari_app"
    db_password: str | None = None
    db_password_file: str | None = None
    db_admin_password_file: str | None = None
    db_pool_min: int = 1
    db_pool_max: int = 8
    db_thread_limit: int = 8

    # 모델
    llm_model: Literal["gpt-6-luna"] = "gpt-6-luna"
    openai_api_key: str | None = None
    openai_api_key_file: str | None = None
    model_concurrency: int = 2

    # 외부 요청 — 안전 기본 false. 서버측 전송 게이트가 이 값을 검사한다.
    external_requests_enabled: bool = False

    # 작업 한도 (SRS 기본 제안)
    max_plan_steps: int = 8
    max_retries: int = 3
    job_deadline: int = 120
    analysis_concurrency: int = 4
    analysis_queue_limit: int = 8
    job_retention_limit: int = 1000

    # 원천 키
    jeju_project_key: str | None = None
    kma_service_key: str | None = None
    kma_hub_key: str | None = None
    at_service_key: str | None = None

    # 캐시
    response_cache_enabled: bool = True
    embedding_model_path: str = "intfloat/multilingual-e5-small"
    embedding_revision: str = "main"

    # 캐시 도메인 — 검증된 문턱값·TTL만 허용. 미설정 시 semantic 조회 우회.
    domain_threshold_config: str | None = "0.90"
    freshness_policy_config: str | None = None

    # 지도
    tile_provider_config: str | None = None
    geocoder_config: str | None = None

    # 파일 — 기본 비활성
    allow_notebook_import: bool = False
    allow_notebook_export: bool = False
    allow_share_file: bool = False

    # 예산
    source_daily_budget: int = 2000
    model_job_token_budget: int = 16000
    spend_warning: int = 0

    # 로그
    safe_log_retention: int = 7
    safe_log_max_size: int = 10

    # 입력 한도 (TBD-06 제안 기본치)
    max_text_length: int = 2000
    max_page_size: int = 100

    # 재생 픽스처 경로 (컨테이너에서는 /app/fixtures로 주입)
    fixtures_dir: str = ""

    @property
    def resolved_db_password(self) -> str | None:
        return read_secret_file(self.db_password_file) or self.db_password

    @property
    def resolved_openai_api_key(self) -> str | None:
        return read_secret_file(self.openai_api_key_file) or self.openai_api_key

    @property
    def db_dsn(self) -> str:
        """비밀 포함 DSN — 로그에 남기지 않는다."""
        password = self.resolved_db_password or ""
        return (
            f"host={self.db_host} port={self.db_port} dbname={self.db_name} "
            f"user={self.db_user} password={password}"
        )

    @property
    def resolved_fixtures_dir(self) -> Path:
        if self.fixtures_dir:
            return Path(self.fixtures_dir)
        return Path(__file__).resolve().parents[4] / "fixtures"


@lru_cache
def get_settings() -> Settings:
    return Settings()
