"""Packaged prompt resources and runtime wiring, without provider calls."""

import tomllib
from datetime import UTC, datetime
from importlib import import_module
from importlib.resources import files
from pathlib import Path

import pytest

from gosari.agent.llm import runtime_system_prompt
from gosari.agent.prompts import load_prompt


@pytest.mark.parametrize(
    ("module", "constant", "resource"),
    [
        ("dialogue", "SYSTEM", "dialogue-system.md"),
        ("runtime", "SYSTEM", "public-runtime-system.md"),
        ("llm", "STRUCTURE_SYSTEM_PROMPT", "structure-system.md"),
        ("llm", "EXPLAIN_SYSTEM_PROMPT", "explain-system.md"),
    ],
)
def test_runtime_constants_use_utf8_markdown_resources(
    module: str, constant: str, resource: str
) -> None:
    document = files("gosari.agent").joinpath("prompts", resource)
    text = document.read_bytes().decode("utf-8")
    assert text.endswith("\n")
    assert load_prompt(resource) == text.rstrip()
    assert getattr(import_module(f"gosari.agent.{module}"), constant) == text.rstrip()
    assert "고사리잇" in text
    assert "고사리잇과 관련된 질문만 도와드릴 수 있어요." in text


def test_clock_template_preserves_korean_date_rollover_and_original_spacing() -> None:
    now = datetime(2026, 11, 6, 16, 5, 4, tzinfo=UTC)
    assert runtime_system_prompt("원래 지시", now=now) == (
        "원래 지시\n\n"
        "현재 기준 날짜: 2026-11-07 (토요일)\n"
        "현재 기준 시각: 01:05:04 (Asia/Seoul, UTC+09:00)\n"
        "오늘·내일·모레는 이 한국 시간 기준으로 해석하세요. "
        "입력에 명시된 날짜와 자료의 관측·발표·조사 시점은 그대로 유지하세요.\n\n"
    )


def test_structure_tool_call_uses_its_markdown_resource() -> None:
    module = import_module("gosari.agent.llm")
    prompt = module.STRUCTURE_TOOL_SYSTEM_PROMPT
    assert prompt == load_prompt("structure-tool-system.md")


def test_required_prompt_files_belong_to_the_configured_wheel_package() -> None:
    api = Path(__file__).resolve().parents[1]
    config = tomllib.loads((api / "pyproject.toml").read_text(encoding="utf-8"))
    packages = config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    agent = api / "src" / "gosari" / "agent"
    assert any(agent.is_relative_to(api / package) for package in packages)
    for name in (
        "dialogue-system.md",
        "public-runtime-system.md",
        "structure-system.md",
        "structure-tool-system.md",
        "explain-system.md",
        "runtime-clock.md",
    ):
        assert files("gosari.agent").joinpath("prompts", name).is_file()
