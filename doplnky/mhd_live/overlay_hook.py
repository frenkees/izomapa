"""MHD živě (doplněk): z assets/doplnky/mhd_live.json předá prohlížeči adresu API a interval dotazů.
Zapíná se souborem assets/doplnky/mhd_live.json (`enabled: false` doplněk vypne). Vyžaduje MHD v mesto.json (jízdní řády GTFS)
a serverovou funkci skripty/vercel_api/mhd_live.js (nasazuje ji pripravit_vercel.mjs jako api/mhd_live.js)."""
from __future__ import annotations

import json
from typing import Any

DEFAULTS: dict[str, Any] = {'api': 'api/mhd_live', 'poll_s': 30}


def build_overlay(ctx: dict[str, Any]) -> dict[str, Any] | bool:
    f = ctx['data_file']
    if not f.is_file():
        return False
    raw = json.loads(f.read_text(encoding='utf-8'))
    if raw.get('enabled', True) is False:
        return False
    return {**DEFAULTS, **{k: v for k, v in raw.items() if k in DEFAULTS}}
