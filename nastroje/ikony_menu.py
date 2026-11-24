"""Pixelové ikonky přepínačů ve Vrstvách (menu): z textových mřížek 9×9 vyrobí web/css/44-menu-ikony.css.

python nastroje/ikony_menu.py      (výsledek je v gitu; spouští se jen po úpravě mřížek níže)
Každá ikonka je CSS maska (currentColor), takže se barví podle stavu přepínače. Přepínač dostane ikonku podle id vstupu
(`.layers label:has(#l-xxx)`); ostatní (např. z doplňků) dostanou výchozí kosočtverec. Nové ikonky: přidat mřížku a id do IKONY.
"""
import os, re

IKONY = {
    'l-labels': ['#########', '#.......#', '#.#####.#', '#.......#', '#.#####.#', '#.......#', '#########', '...#.....', '..#......'],
    'l-traffic': ['.........', '..#####..', '.#######.', '#.##.##.#', '#########', '#########', '##.###.##', '.........', '.........'],
    'l-people': ['...###...', '...###...', '....#....', '.#######.', '#.#####.#', '#.#####.#', '..##.##..', '..##.##..', '.###.###.'],
    'l-pluhy': ['.........', '.#####...', '.#####.##', '.#####.##', '#########', '#########', '.##...##.', '.........', '.........'],
    'l-smoke': ['..#......', '.#.#.....', '..#..#...', '......#..', '...####..', '...####..', '...####..', '..######.', '..######.'],
    'l-xmas': ['....#....', '...###...', '..#####..', '...###...', '..#####..', '.#######.', '#########', '....#....', '....#....'],
    'l-hover': ['.#######.', '.#.#.#.#.', '.#######.', '.#.#.#.#.', '.#######.', '.#.#.#.#.', '.#######.', '.###.###.', '.###.###.'],
    'l-stops': ['.#######.', '.#.....#.', '.#.###.#.', '.#.###.#.', '.#.....#.', '.#######.', '....#....', '....#....', '....#....'],
    'l-jam': ['....#....', '...###...', '...#.#...', '..#.#.#..', '..#.#.#..', '.#.....#.', '.###.###.', '#########', '.........'],
    'l-mhdpins': ['..#####..', '.#######.', '##.###.##', '##.###.##', '.#######.', '..#####..', '...###...', '....#....', '.........'],
    'l-planes': ['....#....', '....#....', '...###...', '#########', '#########', '...###...', '....#....', '...###...', '.........'],
    '_default': ['....#....', '...###...', '..#####..', '...###...', '....#....', '.........', '.........', '.........', '.........'],
}


def svg(mrizka):
    assert len(mrizka) == 9 and all(len(r) == 9 for r in mrizka), mrizka
    d = ''
    for y, r in enumerate(mrizka):
        for m in re.finditer(r'#+', r):
            d += f'M{m.start()} {y}h{m.end() - m.start()}v1h-{m.end() - m.start()}z'
    return f"url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 9 9' shape-rendering='crispEdges'%3E%3Cpath d='{d}'/%3E%3C/svg%3E\")"


out = ['/* Generováno: nastroje/ikony_menu.py (neupravovat ručně). Pixelové ikonky přepínačů ve Vrstvách jako CSS masky. */',
       f".layers label {{ --i: {svg(IKONY['_default'])}; }}"]
for k, v in IKONY.items():
    if k != '_default':
        out.append(f".layers label:has(#{k}) {{ --i: {svg(v)}; }}")
open(os.path.join(os.path.dirname(__file__), '..', 'web', 'css', '44-menu-ikony.css'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print('ikonek', len(IKONY) - 1)
