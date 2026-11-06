"""Generate OpenAPI schema from the gosari Litestar application."""

import json
from pathlib import Path

from gosari.app import create_app


def generate_openapi() -> None:
    app = create_app()
    openapi_schema = app.openapi_schema.to_schema()
    output_path = Path(__file__).parent.parent / "openapi.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
    print(f"OpenAPI schema generated: {output_path}")


if __name__ == "__main__":
    generate_openapi()
