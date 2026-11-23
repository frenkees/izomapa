"""Build-time hook doplňku doprava_here (běží jen v overlay.py).

1. Silnicím v site/overlay/<čtverec>.json přidá `h` = čísla úseků HERE / TomTom (nastroje/here_doprava.py `prirad`,
   registry assets/here_segmenty.json a assets/tomtom_segmenty.json). Dřív to dělal přímo overlay.py (`mesto.json` `doprava_here`).
2. Vyrobí site/doplnky/doprava_here/doprava_id.json (klíč úseku "lat,lon,délka" -> číslo), podle kterého klient páruje data z api/doprava.
3. Do overlay.json vrátí veřejnou konfiguraci klienta (adresy API, režimy zobrazení, parametry hustoty).
Zapíná se souborem assets/doplnky/doprava_here.json (volitelné klíče viz DEFAULTS, `enabled: false` doplněk vypne).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    'api': 'api/doprava',                    # živá data {t, s: {klíč: [jamFactor×10, rychlost %]}}
    'api_typicka': 'api/doprava_typicka',    # typický průběh {n, s: {klíč: [48 hodnot]}}
    'zive_s': 300,                           # jak často klient znovu stahuje živá data (s)
    'min_podil': 0.35,                       # podíl aut při jamFactoru 0 (volno); při j_plny a víc jedou všechna auta
    'j_plny': 6,
    'rezimy': [
        {'v': 'live', 't': 'živě'}, {'v': '7', 't': 'prac. den 7 h'}, {'v': '8', 't': 'prac. den 8 h'},
        {'v': '16', 't': 'prac. den 16 h'}, {'v': '17', 't': 'prac. den 17 h'}, {'v': '36', 't': 'víkend 12 h'},
    ],
}
ID_URL = 'doplnky/doprava_here/doprava_id.json'


def _nastroje(root: Path):
    """Importuje nastroje/here_doprava.py (a tomtom_doprava.py), pokud je dostupné."""
    d = str(root / 'nastroje')
    if d not in sys.path:
        sys.path.insert(0, d)
    import here_doprava
    try:
        import tomtom_doprava
    except ImportError:
        tomtom_doprava = None
    return here_doprava, tomtom_doprava


def vyrob_ids(here, tomtom) -> dict[str, int]:
    """klíč úseku -> číslo (HERE 0.., TomTom s posunem ID_POSUN), stejné jako `here_doprava.py ids` + `tomtom_doprava.py ids`"""
    ids = {s['k']: i for i, s in enumerate(here.registr()['seg'])}
    if tomtom is not None and Path(tomtom.REG).exists():
        for i, s in enumerate(tomtom.registr()['seg']):
            ids[s['k']] = tomtom.ID_POSUN + i
    return ids


def prirad_silnice(site_dir: Path, here) -> tuple[int, dict]:
    """projde site/overlay/*.json, doplní `h` a soubory přepíše; vrací počet silnic s úseky a statistiku směrů"""
    n, st = 0, {}
    for f in sorted((site_dir / 'overlay').glob('*.json')):
        d = json.loads(f.read_text(encoding='utf-8'))
        roads = d.get('roads')
        if not roads:
            continue
        for r in roads:
            r.pop('h', None)
        k = here.prirad(roads)
        for nm, (a, b) in getattr(here.prirad, 'stat', {}).items():
            s = st.setdefault(nm, [0, 0]); s[0] += a; s[1] += b
        if k:
            n += k
        f.write_text(json.dumps(d, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
    return n, st


def build_overlay(ctx: dict[str, Any]) -> dict[str, Any] | bool:
    data_file = ctx['data_file']
    if not data_file.is_file():
        return False
    raw = json.loads(data_file.read_text(encoding='utf-8'))
    if raw.get('enabled', True) is False:
        return False
    cfg = {**DEFAULTS, **{k: v for k, v in raw.items() if k in DEFAULTS}}

    root = Path(ctx['plugin_dir']).resolve().parents[1]
    here, tomtom = _nastroje(root)
    site = Path(ctx['site_dir'])
    n, st = prirad_silnice(site, here)
    ids = vyrob_ids(here, tomtom)
    if not ids:
        print('doprava_here: žádné registry úseků (assets/here_segmenty.json), doplněk se přeskočí')
        return False
    out = site / ID_URL
    out.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(ids, separators=(',', ':'))
    out.write_text(body, encoding='utf-8')
    print(f'doprava HERE + TomTom: silnic s úseky {n} | úseků v registrech {len(ids)} | směr na jednosměrkách (shoda, neshoda): {st}')
    return {**cfg, 'ids': ID_URL, 'ids_v': hashlib.md5(body.encode()).hexdigest()[:8]}
