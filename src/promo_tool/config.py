from __future__ import annotations
import os
import re
from pathlib import Path
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def load_settings(path: str | Path | None = None) -> dict:
    p = Path(path) if path else ROOT / "config" / "settings.yaml"
    with open(p, encoding="utf-8") as f:
        settings = yaml.safe_load(f)
    settings["model"] = os.getenv("PROMO_MODEL", settings["model"])
    return settings


def load_characters(path: str | Path | None = None) -> list[dict]:
    p = Path(path) if path else ROOT / "config" / "characters.yaml"
    with open(p, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("characters", [])


def load_prompt(name: str) -> str:
    return (ROOT / "prompts" / name).read_text(encoding="utf-8")


def render(template: str, **values: object) -> str:
    out = template
    for k, v in values.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


def cast_patterns(characters: list[dict]) -> list[re.Pattern]:
    names: list[str] = []
    for c in characters:
        names.append(c.get("name", ""))
        names.extend(c.get("aliases", []) or [])
    return [re.compile(r"\b" + re.escape(n) + r"\b", re.I) for n in names if n]
