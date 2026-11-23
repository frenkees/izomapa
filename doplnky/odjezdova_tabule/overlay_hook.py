"""Odjezdová tabule (doplněk): z assets/doplnky/odjezdova_tabule.json předá prohlížeči polohu nádraží, regulární výrazy názvu budovy a zastávek a rozložení tabule."""
from __future__ import annotations

import json
from typing import Any

KLICE = ('stanice', 'titulek', 'radku', 'sirky', 'zkratky', 'horizont_h')


def build_overlay(ctx: dict[str, Any]) -> dict[str, Any] | bool:
    f = ctx['data_file']
    if not f.is_file():
        return False
    raw = json.loads(f.read_text(encoding='utf-8'))
    st = raw.get('stanice') or {}
    if raw.get('enabled', True) is False or not isinstance(st.get('lat'), (int, float)) or not isinstance(st.get('lon'), (int, float)) or not st.get('zastavka_re'):
        return False
    return {k: raw[k] for k in KLICE if k in raw}
