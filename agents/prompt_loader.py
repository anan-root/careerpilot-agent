"""Prompt loading helpers for versioned Markdown prompts."""

from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt file from the repository prompt directory."""
    path = PROMPT_DIR / name
    if path.suffix != ".md":
        path = path.with_suffix(".md")
    return path.read_text(encoding="utf-8")


def render_prompt(name: str, **values: object) -> str:
    """Render {{placeholders}} in a prompt without fighting JSON braces."""
    prompt = load_prompt(name)
    for key, value in values.items():
        prompt = prompt.replace("{{" + key + "}}", str(value))
        prompt = prompt.replace("{{" + key.upper() + "}}", str(value))
    return prompt
