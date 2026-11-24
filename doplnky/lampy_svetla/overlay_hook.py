"""Světlo pouličních lamp (doplněk): z build/**/info_src.json (`lamps`, `roads`) vyrobí site/doplnky/lampy_svetla/lampy.json,
{ "l": [[x, y, z, typ], …] } ve společných souřadnicích mapy. Typ: 0 = sodíková (vedlejší ulice), 1 = LED (hlavní tahy: třída
nejbližší silnice v `hlavni`, výchozí motorway až tertiary). Lampy z okrajového pásu sousedního čtverce se berou jen jednou.
Zapíná se souborem assets/doplnky/lampy_svetla.json (`enabled: false` doplněk vypne; `hlavni` = seznam tříd silnic s LED)."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import shapely
from shapely.geometry import LineString, Point

import geo

HLAVNI = ['motorway', 'trunk', 'primary', 'secondary', 'tertiary']


def build_overlay(ctx: dict[str, Any]) -> dict[str, Any] | bool:
    f = ctx['data_file']
    if not f.is_file():
        return False
    raw = json.loads(f.read_text(encoding='utf-8'))
    if raw.get('enabled', True) is False:
        return False
    hlavni = set(raw.get('hlavni') or HLAVNI)
    half = geo.HALF
    out, n = [], [0, 0]
    for ci in range(-6, 7):
        for cj in range(-6, 7):
            src = Path(ctx['build_dir']).parent / geo.chunk_dir((ci, cj)) / 'info_src.json'
            if not src.is_file():
                continue
            d = json.loads(src.read_text(encoding='utf-8'))
            lines = [(LineString([(p[0], p[1]) for p in r['p']]), r['c']) for r in d.get('roads', []) if len(r.get('p', [])) > 1]
            tree = shapely.STRtree([l for l, _ in lines]) if lines else None
            ox, oy = geo.chunk_center((ci, cj))
            for x, y, z, *_ in d.get('lamps', []):
                if abs(x) >= half or abs(y) >= half:      # okrajový pás patří sousednímu čtverci
                    continue
                typ = 0
                if tree is not None:
                    i = tree.nearest(Point(x, y))
                    if i is not None and lines[i][0].distance(Point(x, y)) < 25 and lines[i][1] in hlavni:
                        typ = 1
                out.append([round(x + ox, 1), round(y + oy, 1), round(z, 1), typ]); n[typ] += 1
    dest = Path(ctx['site_dir']) / 'doplnky' / 'lampy_svetla'
    dest.mkdir(parents=True, exist_ok=True)
    (dest / 'lampy.json').write_text(json.dumps({'l': out}, separators=(',', ':')), encoding='utf-8')
    print(f'lampy_svetla: {len(out)} lamp (sodík {n[0]}, LED {n[1]})')
    return {'data': 'doplnky/lampy_svetla/lampy.json'}
