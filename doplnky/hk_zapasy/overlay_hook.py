"""Zápasy FC Hradec Králové (doplněk): z assets/doplnky/hk_zapasy.json předá prohlížeči polohu a rozměry arény, zdroje dat a zkratky klubů."""
from __future__ import annotations

import json
from typing import Any

KLICE = ('arena', 'zdroje', 'odkaz', 'zkratky')


def build_overlay(ctx: dict[str, Any]) -> dict[str, Any] | bool:
    f = ctx['data_file']
    if not f.is_file():
        return False
    raw = json.loads(f.read_text(encoding='utf-8'))
    ar = raw.get('arena') or {}
    if raw.get('enabled', True) is False or not isinstance(ar.get('lat'), (int, float)) or not isinstance(ar.get('lon'), (int, float)):
        return False
    return {k: raw[k] for k in KLICE if k in raw}
