"""Zimní údržba silnic KHK (doplněk): z assets/doplnky/udrzba_khk.json předá prohlížeči adresu API a interval dotazů.
Zapíná se souborem assets/doplnky/udrzba_khk.json (`enabled: false` doplněk vypne). Vyžaduje serverovou funkci
skripty/vercel_api/udrzba_khk.js (nasazuje ji pripravit_vercel.mjs jako api/udrzba_khk.js); bez ní (404) se prohlížeč přestane ptát."""
from __future__ import annotations

import json
from typing import Any

DEFAULTS: dict[str, Any] = {'api': 'api/udrzba_khk', 'poll_s': 300}


def build_overlay(ctx: dict[str, Any]) -> dict[str, Any] | bool:
    f = ctx['data_file']
    if not f.is_file():
        return False
    raw = json.loads(f.read_text(encoding='utf-8'))
    if raw.get('enabled', True) is False:
        return False
    return {**DEFAULTS, **{k: v for k, v in raw.items() if k in DEFAULTS}}
