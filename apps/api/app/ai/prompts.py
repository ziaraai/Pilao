"""Versioned prompts stored as Markdown files in /prompts.

Format: a front matter (``id``, ``version``, ...) then ``# Système`` and ``# Utilisateur``
sections. Variables are ``{{name}}``; a missing variable is an error, never an empty string.
The version is recorded with every AI result (docs/08-pipeline-ia.md).
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

_VAR = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class PromptError(Exception):
    pass


@dataclass(frozen=True)
class Prompt:
    id: str
    version: str
    system: str
    user: str

    def render(self, **variables: str) -> tuple[str, str]:
        """Return (system, user) with variables substituted."""

        def sub(text: str) -> str:
            def repl(m: re.Match[str]) -> str:
                name = m.group(1)
                if name not in variables:
                    raise PromptError(f"prompt {self.id}: missing variable {name!r}")
                return str(variables[name])

            return _VAR.sub(repl, text)

        return sub(self.system), sub(self.user)


@lru_cache
def load_prompt(name: str) -> Prompt:
    path = Path(get_settings().prompts_dir) / f"{name}.md"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptError(f"prompt file not found: {path}") from exc
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
    if not match:
        raise PromptError(f"{name}: missing front matter")
    meta = dict(line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    body = match.group(2)
    sys_match = re.search(r"^# Système\s*\n(.*?)(?=^# Utilisateur)", body, re.DOTALL | re.MULTILINE)
    usr_match = re.search(r"^# Utilisateur\s*\n(.*)$", body, re.DOTALL | re.MULTILINE)
    if not sys_match or not usr_match or "version" not in meta or "id" not in meta:
        raise PromptError(f"{name}: expected id, version, '# Système' and '# Utilisateur'")
    return Prompt(
        meta["id"], meta["version"], sys_match.group(1).strip(), usr_match.group(1).strip()
    )
