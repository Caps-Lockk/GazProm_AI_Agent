"""Загрузка настроек и карточек продуктов."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_settings(path: str | Path | None = None) -> dict[str, Any]:
    path = Path(path or ROOT / "config" / "settings.yaml")
    settings = yaml.safe_load(path.read_text(encoding="utf-8"))
    # Переопределения из окружения: SIGNAL_LLM_BASE_URL, SIGNAL_LLM_MODEL, SIGNAL_DB_PATH …
    env_map = {
        "SIGNAL_LLM_BASE_URL": ("llm", "base_url"),
        "SIGNAL_LLM_MODEL": ("llm", "model"),
        "SIGNAL_ASR_BASE_URL": ("asr", "base_url"),
        "SIGNAL_VL_BASE_URL": ("vl", "base_url"),
    }
    for env, (section, key) in env_map.items():
        if os.getenv(env):
            settings[section][key] = os.environ[env]
    if os.getenv("SIGNAL_DB_PATH"):
        settings["db_path"] = os.environ["SIGNAL_DB_PATH"]
    return settings


def load_product(product_id: str, products_dir: str | Path | None = None) -> dict[str, Any]:
    products_dir = Path(products_dir or ROOT / "config" / "products")
    return yaml.safe_load((products_dir / f"{product_id}.yaml").read_text(encoding="utf-8"))


def load_prompt(name: str) -> str:
    """Читает промпт и выбрасывает HTML-комментарии — они для людей, не для модели."""
    import re
    text = (ROOT / "prompts" / name).read_text(encoding="utf-8")
    return re.sub(r"<!--.*?-->\s*", "", text, flags=re.S).strip()
