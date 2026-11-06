"""컨테이너 건강 검사 — 로컬 DB/스키마만 확인. 유료·원천 호출 금지."""

import httpx


def main() -> int:
    try:
        response = httpx.get("http://127.0.0.1:8765/api/v1/health/ready", timeout=3.0)
        if response.status_code != 200:
            return 1
        data = response.json()
        return 0 if data.get("status") in ("ready", "limited") else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
