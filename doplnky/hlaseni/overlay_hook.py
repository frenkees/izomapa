"""Hlášení (doplněk): jen zapíná doplněk podle assets/doplnky/hlaseni.json; adresa API jde do klienta přes konfiguraci."""
from __future__ import annotations

import json
from typing import Any


def build_overlay(ctx: dict[str, Any]) -> dict[str, Any] | bool:
    f = ctx['data_file']
    if not f.is_file():
        return False
    raw = json.loads(f.read_text(encoding='utf-8'))
    if raw.get('enabled', True) is False:
        return False
    return {}
