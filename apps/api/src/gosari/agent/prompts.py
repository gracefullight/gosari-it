"""Load the agent's UTF-8 Markdown prompt resources."""

from importlib.resources import files


def load_prompt(name: str) -> str:
    """Read a statically selected prompt without its file-ending whitespace."""
    return files("gosari.agent").joinpath("prompts", name).read_text(encoding="utf-8").rstrip()


DIALOGUE_SYSTEM_PROMPT = load_prompt("dialogue-system.md")
PUBLIC_RUNTIME_SYSTEM_PROMPT = load_prompt("public-runtime-system.md")
STRUCTURE_SYSTEM_PROMPT = load_prompt("structure-system.md")
STRUCTURE_TOOL_SYSTEM_PROMPT = load_prompt("structure-tool-system.md")
EXPLAIN_SYSTEM_PROMPT = load_prompt("explain-system.md")
RUNTIME_CLOCK_TEMPLATE = load_prompt("runtime-clock.md")
