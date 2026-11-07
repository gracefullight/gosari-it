"""로컬 임베딩 — intfloat/multilingual-e5-small, 384차원, query: 접두사 (SRS §11.5).

모델/토크나이저를 쓸 수 없으면 길이 검증이 불가능하므로 캐시 전체를 우회한다.
유료 임베딩 API는 호출하지 않는다.
"""

import threading
from typing import Any

from gosari.config import get_settings
from gosari.logging import get_logger

logger = get_logger(__name__)

QUERY_PREFIX = "query: "
MAX_TOKENS = 512
DIMENSIONS = 384


class EmbeddingEngine:
    def __init__(self) -> None:
        self._model: Any = None
        self._tokenizer: Any = None
        self._lock = threading.Lock()
        self._failed = False
        self.revision = get_settings().embedding_revision

    def _load(self) -> bool:
        if self._model is not None:
            return True
        if self._failed:
            return False
        with self._lock:
            if self._model is not None:
                return True
            if self._failed:
                return False
            try:
                import torch
                from sentence_transformers import SentenceTransformer
                from transformers import AutoTokenizer

                torch.set_num_threads(2)
                settings = get_settings()
                self._model = SentenceTransformer(
                    settings.embedding_model_path,
                    revision=settings.embedding_revision,
                    device="cpu",
                    local_files_only=True,
                )
                self._tokenizer = AutoTokenizer.from_pretrained(
                    settings.embedding_model_path,
                    revision=settings.embedding_revision,
                    local_files_only=True,
                )
                dim_fn = getattr(self._model, "get_embedding_dimension", None)
                dim = dim_fn() if dim_fn else self._model.get_sentence_embedding_dimension()
                if dim != DIMENSIONS:
                    logger.warning("embedding dimension mismatch", dim=dim)
                    self._failed = True
                    return False
                return True
            except Exception as exc:
                logger.warning("embedding model unavailable", error_type=type(exc).__name__)
                self._failed = True
                return False

    def available(self) -> bool:
        return self._load()

    def token_count(self, text: str) -> int | None:
        """query: 접두사·특수 토큰 포함 길이. 미확인이면 None → 우회."""
        if not self._load():
            return None
        try:
            encoded = self._tokenizer(QUERY_PREFIX + text, add_special_tokens=True)
            return len(encoded["input_ids"])
        except Exception:
            return None

    def embed(self, text: str) -> list[float] | None:
        if not self._load():
            return None
        try:
            vector = self._model.encode(
                [QUERY_PREFIX + text],
                normalize_embeddings=True,
                show_progress_bar=False,
            )[0]
            values = [float(v) for v in vector]
            if len(values) != DIMENSIONS or any(v != v for v in values):
                return None
            if all(v == 0.0 for v in values):
                return None
            return values
        except Exception:
            return None


_engine: EmbeddingEngine | None = None


def get_engine() -> EmbeddingEngine:
    global _engine
    if _engine is None:
        _engine = EmbeddingEngine()
    return _engine
