"""MHD podle jízdních řádů (GTFS, adresa v mesto.json mhd.gtfs) -> site/mhd.json

python mhd.py [--stahnout]   stáhne build/gtfs.zip (při --stahnout nebo když je starší než den) a převede ho:
  routes   [číslo linky, typ (0 tramvaj, 2 vlak, 3 autobus, 11 trolejbus)]
  shapes   trasy ve světových souřadnicích mapy [[x, y], ...] (zjednodušené na 1 m)
  services kalendář {id: [po..ne (7× 0/1), od, do, [přidané dny], [zrušené dny]]}
  trips    [linka, trasa, služba, začátek (s od půlnoci), [Δt, vzdálenost po trase (m)] × zastávky, cíl, [zastávka, Δt příjezdu] × zastávky]
  heads, stops  názvy cílů a zastávek (indexy v trips)
Krajské GTFS (např. IDS JMK) se ořízne: jen autobusy a tramvaje, jejichž trasa vede územím mapy.
Prohlížeč z toho podle skutečného času dopočítá, kde je každé vozidlo. Bez mhd.gtfs skript nic neudělá.
"""
import csv, io, json, math, os, subprocess, sys, time, zipfile
import shapely
from nastroje.gtfs_casy import cekani_na_konecne, dopln_mezicasy
from geo import CHUNKS, HALF, MESTO, chunk_center, to_local

URL = (MESTO.get('mhd') or {}).get('gtfs')
if not URL: sys.exit('mesto.json nemá mhd.gtfs – MHD se vynechá')
Z = 'build/gtfs.zip'
if '--stahnout' in sys.argv or not os.path.exists(Z) or time.time() - os.path.getmtime(Z) > 86400:
    subprocess.run(['curl', '-sL', '-m', '120', '-o', Z + '.tmp', URL], check=True)
    zipfile.ZipFile(Z + '.tmp').testzip(); os.replace(Z + '.tmp', Z)
zf = zipfile.ZipFile(Z)
def T(n):                                                    # soubor z GTFS + doplněk build/gtfs_extra/<n>.txt (nastroje/vyluka_nad.py: náhradní doprava za výluku)
    yield from csv.DictReader(io.TextIOWrapper(zf.open(n + '.txt'), encoding='utf-8-sig'))
    if os.path.exists(f'build/gtfs_extra/{n}.txt'): yield from csv.DictReader(open(f'build/gtfs_extra/{n}.txt', encoding='utf-8-sig', newline=''))
sec = lambda t: (lambda h, m, s: h * 3600 + m * 60 + s)(*map(int, t.split(':')))

AREA = shapely.union_all([shapely.box(x - HALF, y - HALF, x + HALF, y + HALF) for x, y in map(chunk_center, CHUNKS)])
# tramvaj 0 / 900–906, autobus 3 / 700–716, trolejbus 11 / 800 (druh 11, autobus se sběrači); vlak 2, jen s volbou "vlak" a s tvary tras (po silnicích jezdit nemůže); lanovky prohlížeč nekreslí
# trolejbus má vlastní druh 11 (prohlížeč ho kreslí jako autobus se sběrači)
KIND = lambda t: 0 if t == 0 or 900 <= t <= 906 else 11 if t in (11, 800) else 3 if t == 3 or 700 <= t <= 716 else 2 if t == 2 and MESTO.get('vlak') and 'shapes.txt' in zf.namelist() else None
# celostátní GTFS (CIS JŘ) má všechny dopravce: "dopravce" v mesto.json vybere jen některé (agency_id nebo část názvu)
DOPR = (MESTO.get('mhd') or {}).get('dopravce')
if DOPR:
    _ag = {a['agency_id'] for a in T('agency') if any(d == a['agency_id'] or d.lower() in a['agency_name'].lower() for d in DOPR)}
    print('dopravci', sorted(_ag))
RT = {r['route_id']: r for r in T('routes') if KIND(int(r['route_type'] or 3)) is not None and (not DOPR or r.get('agency_id') in _ag)}
# CIS JŘ má v route_short_name licenční číslo linky (615011), skutečné číslo je v dlouhém názvu („linka: 11“)
import re as _re
for _r in RT.values():
    _m = _re.search(r'linka\s*:\s*([0-9]+[A-ZŠ]?)', _r.get('route_long_name') or '')
    if _m and len(_r['route_short_name']) > 4: _r['route_short_name'] = _m.group(1)
trips = [t for t in T('trips') if t['route_id'] in RT]
SN, SXY = {}, {}
for r in T('stops'):
    SN[r['stop_id']] = r['stop_name']
    if r.get('stop_lat'): SXY[r['stop_id']] = tuple(float(v) for v in to_local(float(r['stop_lon']), float(r['stop_lat'])))
shapes, SI, SLEN = [], {}, {}
if 'shapes.txt' in zf.namelist():
    used = {t['shape_id'] for t in trips}
    pts = {}
    for r in T('shapes'):
        if r['shape_id'] in used: pts.setdefault(r['shape_id'], []).append((int(r['shape_pt_sequence']), float(r['shape_pt_lon']), float(r['shape_pt_lat']), float(r['shape_dist_traveled'] or 0)))
    # autobusové trasy na silnici (nastroje/trasy_na_silnici.py): tvary dopravce vedou k zastávkám na chodník a kousek vedle osy
    BUS = {t['shape_id'] for t in trips if KIND(int(RT[t['route_id']]['route_type'] or 3)) == 3}
    SIL = None
    if BUS and os.path.exists('data_all/segment.parquet'):
        from nastroje.trasy_na_silnici import ze_segmentu
        SIL = ze_segmentu('data_all/segment.parquet')
    for k, v in pts.items():
        if len(v) < 2: continue
        v.sort(); x, y = to_local([p[1] for p in v], [p[2] for p in v])
        l = shapely.LineString(list(zip(x, y)))
        if not l.intersects(AREA): continue                      # trasa mimo mapu
        if SIL and k in BUS: l = shapely.LineString(SIL.uprav(list(l.coords)))
        SI[k] = len(shapes); SLEN[k] = (l.length, v[-1][3] or 1.0)
        shapes.append([[round(a, 1), round(b, 1)] for a, b in shapely.simplify(l, 1.0).coords])
    trips = [t for t in trips if t['shape_id'] in SI]
TI = {t['trip_id'] for t in trips}
st = {}
PRUJEZD = set()                                           # (trip_id, stop_sequence) bez zastavení (pickup i drop_off = 1): vlak jen projíždí
for r in T('stop_times'):
    if r['trip_id'] not in TI: continue
    if r.get('pickup_type') == '1' and r.get('drop_off_type') == '1': PRUJEZD.add((r['trip_id'], int(r['stop_sequence'])))
    ta = r.get('arrival_time') or r.get('departure_time')
    td = r.get('departure_time') or ta
    st.setdefault(r['trip_id'], []).append((int(r['stop_sequence']), sec(ta) if ta else None, sec(td) if td else None, float(r.get('shape_dist_traveled') or 0), r['stop_id']))
st = {trip_id: dopln_mezicasy(rows) for trip_id, rows in st.items()}
if 'shapes.txt' not in zf.namelist():                      # GTFS bez tvarů tras (např. IDS JMK): trasa mezi zastávkami po silnicích z mapy
    import road_route
    near = AREA.buffer(300)
    trips = [t for t in trips if any(near.contains(shapely.Point(SXY[z[4]])) for z in st.get(t['trip_id'], []) if z[4] in SXY)]
    R = road_route.Graph('data_all/segment.parquet')
    # referenční trasy linek (assets/mhd_trasy_ref.json: relace z OSM, mapa linek dopravce/města; assets/mhd_trasy_rucne.json:
    # ruční průjezdní čáry): trasa vede přednostně po nich, ne nejkratší cestou; kvalita úseků mezi zastávkami jde do mhd.json
    REF = json.load(open('assets/mhd_trasy_ref.json', encoding='utf-8')) if os.path.exists('assets/mhd_trasy_ref.json') else {}
    RUC = json.load(open('assets/mhd_trasy_rucne.json', encoding='utf-8')) if os.path.exists('assets/mhd_trasy_rucne.json') else []
    _ll = lambda q: [tuple(float(v) for v in to_local(b, a)) for a, b in q]
    _base = lambda n: (_re.match(r'\d+', n) or [n])[0]
    _cor = {}

    def koridory(ln):
        if ln not in _cor:
            o = [_ll(w) for r in REF.get('osm', []) if r['ref'] in (ln, _base(ln)) for w in r['ways']]
            m = [_ll(w) for k, ws in REF.get('mesto', {}).items() if k in (ln, _base(ln)) for w in ws]
            u = [_ll(q['pres']) for q in RUC if q.get('linka') in (ln, _base(ln))]
            _cor[ln] = {'u': R.koridor(u, 15.0), 'o': R.koridor(o, 16.0), 'm': R.koridor(m, 35.0), 'ma_m': bool(m), 'ma_o': bool(o),
                        'og': shapely.union_all([shapely.LineString(q) for q in u + o if len(q) > 1]) if u or o else None,
                        'mg': shapely.union_all([shapely.LineString(q) for q in m if len(q) > 1]) if m else None}
        return _cor[ln]
    # polohy zastávek z OSM podle názvu (jízdní řád má jednu souřadnici na název; stejnojmenné zastávky bývají v několika ulicích)
    _oz = {}
    for _n, _la, _lo in REF.get('zastavky', []): _oz.setdefault(_n, []).append(tuple(float(v) for v in to_local(_lo, _la)))
    _mesto0 = MESTO.get('nazev', '') + ', '

    def _smer_pasu(q, smer):
        """největší shoda (cos) směru spoje s hranami vycházejícími z nejbližšího uzlu grafu; na jednosměrném pásu opačného směru vychází záporně"""
        d = np.hypot(R.arr[:, 0] - q[0], R.arr[:, 1] - q[1]); u = int(d.argmin())
        if d[u] > 25: return 1.0                              # daleko od silnice: nerozhoduje
        n = math.hypot(*smer); best = -1.0
        for v, _w in R.adj[u]:
            e = (R.xy[v][0] - R.xy[u][0], R.xy[v][1] - R.xy[u][1]); le = math.hypot(*e)
            if le > 0.5: best = max(best, (e[0] * smer[0] + e[1] * smer[1]) / (le * n))
        return best

    def poloha(z, c, smer=None):
        p = SXY[z]; n = SN.get(z, '')
        n = n[len(_mesto0):] if n.startswith(_mesto0) else n
        alts = [q for q in _oz.get(n, []) + _oz.get(n.split(', ')[-1], []) if math.dist(q, p) < 500]
        for g, lim in ((c['og'], 30.0), (c['mg'], 45.0)):
            if g is None or not alts: continue
            ds = [(g.distance(shapely.Point(q)), q) for q in alts]
            d, q = min(ds)
            if d <= lim and g.distance(shapely.Point(p)) > d:
                if smer is not None:                      # protější zastávky rozdělené silnice (oba pásy jsou v koridoru): ta na pásu, kde se smí jet ve směru spoje,
                    bl = [qq for dd, qq in ds if dd <= lim and math.dist(qq, q) < 200]   # jinak trasa zajede na pás opačného směru a vrací se (otočka u zastávky)
                    if len(bl) > 1:
                        ok = [qq for qq in bl if _smer_pasu(qq, smer) > 0.3]
                        if ok: q = min(ok, key=lambda a: math.dist(a, q))
                return q
        return p

    SMER_ON = os.environ.get('IZO_STOP_SMER', '1') != '0'      # 0 = bez výběru zastávky podle směru jízdy (porovnání se starým chováním)

    def smery(zs):                                        # směr jízdy u každé zastávky spoje: z předchozí do následující (podle souřadnic jízdního řádu)
        if not SMER_ON: return [None] * len(zs)
        out = []
        for i, z in enumerate(zs):
            a = SXY[zs[i - 1]] if i else SXY[z]; b = SXY[zs[i + 1]] if i + 1 < len(zs) else SXY[z]
            d = (b[0] - a[0], b[1] - a[1]); out.append(d if math.hypot(*d) > 20 and 0 < i < len(zs) - 1 else None)   # konečné: směr nejistý (otáčení, smyčky)
        return out

    def kvalita(c, legs, pts):
        """kód úseku: j jistý (OSM i město, nebo ručně), o jen OSM, m jen město, r rozpor OSM × město, n nejistý, x mimo mapu"""
        out = []
        for i, seq in enumerate(legs):
            if not (AREA.contains(shapely.Point(pts[i])) and AREA.contains(shapely.Point(pts[i + 1]))): out.append('x'); continue
            if not seq or len(seq) < 2: out.append('n'); continue
            L = lo = lm = lu = 0.0
            for a, b in zip(seq, seq[1:]):
                d = float(np.hypot(*np.subtract(R.xy[a], R.xy[b]))); L += d
                if a in c['o'] and b in c['o']: lo += d
                if a in c['m'] and b in c['m']: lm += d
                if a in c['u'] and b in c['u']: lu += d
            if L < 120 or lu >= 0.8 * L: out.append('j'); continue
            fo, fm = lo / L, lm / L
            if fo >= 0.8 and (fm >= 0.6 or not c['ma_m']): out.append('j')
            elif fo >= 0.8:                                   # rozpor jen když městská čára vede poblíž jinudy (ne když tu chybí)
                mid = shapely.Point(R.xy[seq[len(seq) // 2]])
                out.append('r' if fm < 0.2 and c['mg'] is not None and c['mg'].distance(mid) < 250 else 'o')
            elif fm >= 0.8: out.append('m')
            else: out.append('n')
        return out
    import numpy as np
    syn, KVAL = {}, {}
    for t in trips:
        s = [z for z in st[t['trip_id']] if z[4] in SXY]
        ln = RT[t['route_id']]['route_short_name']
        key = (ln, tuple(z[4] for z in s))
        if key not in syn:
            c = koridory(ln); pts_ = [poloha(z, c, sm) for z, sm in zip(key[1], smery(key[1]))]
            line, dists = R.path(pts_, cor=[(c['u'], 0.1), (c['o'], 0.3), (c['m'], 0.65)], exact=[tuple(q) != tuple(SXY[z]) for q, z in zip(pts_, key[1])], smer=smery(key[1]))
            KVAL[len(shapes)] = (kvalita(c, R.legs, pts_), dists)
            syn[key] = (f'syn{len(shapes)}', dists)
            SI[syn[key][0]] = len(shapes); SLEN[syn[key][0]] = (dists[-1] or 1.0, dists[-1] or 1.0)
            shapes.append([[round(a, 1), round(b, 1)] for a, b in shapely.simplify(shapely.LineString(line), 1.0).coords])
        t['shape_id'], dists = syn[key]
        st[t['trip_id']] = [(q, a_, d_, dist, z) for (q, a_, d_, _, z), dist in zip(s, dists)]
    print('trasy dopočítané po silnicích:', len(shapes), 'úseků bez silnice:', R.fails, 'úseků jen bez ohledu na jednosměrky:', R.undirected, 'kruhových objezdů:', R.n_rings)
TI = {t['trip_id'] for t in trips}; SV = {t['service_id'] for t in trips}
# nejisté úseky tvarů pro prohlížeč: {tvar: [[od m, do m, kód], …]} (jen úseky, které nejsou 'j')
kval = {}
for _sh, (_k, _d) in (KVAL.items() if 'KVAL' in globals() else []):
    _r = [[round(_d[i]), round(_d[i + 1]), c] for i, c in enumerate(_k) if c not in 'jx' and i + 1 < len(_d)]
    if _r: kval[str(_sh)] = _r
if 'KVAL' in globals():
    from collections import Counter as _C
    print('kvalita úseků tras:', dict(_C(c for _k, _d in KVAL.values() for c in _k)))
st = {k: [(q, a_, d_, dist, SN.get(z, '') if (k, q) not in PRUJEZD else None) for q, a_, d_, dist, z in v] for k, v in st.items() if k in TI}
routes, RI = [], {}
for rid in dict.fromkeys(t['route_id'] for t in trips):
    RI[rid] = len(routes); routes.append([RT[rid]['route_short_name'], KIND(int(RT[rid]['route_type'] or 3))])
services = {}
for c in T('calendar'):
    if c['service_id'] not in SV: continue
    services[c['service_id']] = [[int(c[d]) for d in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')],
                                 int(c['start_date']), int(c['end_date']), [], []]
for c in T('calendar_dates'):
    if c['service_id'] not in SV: continue
    s = services.setdefault(c['service_id'], [[0] * 7, 0, 0, [], []])
    s[3 if c['exception_type'] == '1' else 4].append(int(c['date']))
names, NI = [], {}
def nid(n):
    if n not in NI: NI[n] = len(names); names.append(n)
    return NI[n]
out = []
_vcek = {}
# vlaky z celostátního jízdního řádu (nastroje/vlaky_vyber.py a nastroje/vlaky.py), hodí se, když GTFS vlaky nemá; druh vozidla určuje volba "vlak"
if MESTO.get('vlak') and os.path.exists('build/vlaky/vlaky_mhd.json'):
    _v = json.load(open('build/vlaky/vlaky_mhd.json', encoding='utf-8'))
    _r, _s = len(routes), len(shapes)
    routes += _v['routes']; shapes += _v['shapes']; services.update(_v['services'])
    for t in _v['trips']:
        z_ = t[6]
        if len(t) > 7 and t[7]: _vcek[len(out)] = t[7]                       # vlak, který v mapě začíná, stojí před odjezdem
        out.append([t[0] + _r, t[1] + _s, t[2], t[3], t[4], nid(t[5]), [q for i in range(0, len(z_), 2) for q in (nid(z_[i]), z_[i + 1])]])
    print('vlaků z celostátního jízdního řádu', len(_v['trips']))
for t in trips:
    if routes[RI[t['route_id']]][1] != 2 and len(routes[RI[t['route_id']]][0]) > 4: continue   # poptávková doprava apod. bez pravidelné trasy; vlaky mají dlouhá čísla
    s = st.get(t['trip_id'], [])
    if len(s) < 2 or t['shape_id'] not in SI: continue
    L, gl = SLEN[t['shape_id']]; k = L / gl                     # vzdálenost z jízdního řádu -> délka trasy v mapě
    t0 = s[0][1]; seq = []; zs = []
    for j, (_, a, d, dist, nm) in enumerate(s):
        if nm is None:                                       # průjezd (rychlík zastávkou nestaví): jen časový bod polohy
            seq += [a - t0, round(dist * k)]; continue
        if 0 < j < len(s) - 1 and d == a:                    # jízdní řád je po minutách: v zastávce stát ~20 s kolem času odjezdu
            gap = min(a - s[j - 1][2], s[j + 1][1] - d)
            w = min(10, gap // 4)
            a, d = a - w, d + w
        seq += [a - t0, round(dist * k)]
        if d > a: seq += [d - t0, round(dist * k)]              # pobyt v zastávce
        zs += [nid(nm), a - t0]
    T_, D_ = seq[0::2], seq[1::2]; k_ = 1                          # zastávky ve stejné minutě mají stejný čas a různou vzdálenost (skok o stovky metrů za 0 s): čas rozložit podle vzdálenosti
    while k_ < len(T_):
        if T_[k_] == T_[k_ - 1] and D_[k_] > D_[k_ - 1]:
            a_ = k_ - 1
            while a_ > 0 and T_[a_ - 1] == T_[k_]: a_ -= 1
            b_ = k_
            while b_ + 1 < len(T_) and T_[b_ + 1] == T_[k_]: b_ += 1
            lo_, hi_ = max(a_ - 1, 0), min(b_ + 1, len(T_) - 1)
            if D_[hi_] > D_[lo_] and T_[hi_] > T_[lo_]:
                for m_ in range(lo_ + 1, hi_): T_[m_] = round(T_[lo_] + (T_[hi_] - T_[lo_]) * (D_[m_] - D_[lo_]) / (D_[hi_] - D_[lo_]), 1)
            k_ = hi_
        k_ += 1
    seq = [v_ for p_ in zip(T_, D_) for v_ in p_]
    out.append([RI[t['route_id']], SI[t['shape_id']], t['service_id'], t0, seq, nid(t['trip_headsign'] or s[-1][4] or ''), zs])
# terminál (assets/terminal_hd.json): odjezdová nástupiště jsou pod střechou, tvar spoje ale začíná u výstupní zastávky; vůz začíná na nástupišti (vzdálenost 0 -> místo v pruhu)
TERM = json.load(open('assets/terminal_hd.json', encoding='utf-8')) if os.path.exists('assets/terminal_hd.json') else None
if TERM:
    _bx0, _bx1, _by0, _by1 = TERM['box']; _dbay, _n = {}, 0
    for q in out:
        if routes[q[0]][1] == 2 or names[q[6][0]] != TERM['name'] or len(q[4]) < 4: continue
        if q[1] not in _dbay:
            _w = shapes[q[1]]; _d = None; _c = 0.0
            for (_ax, _ay), (_bx, _by) in zip(_w, _w[1:]):
                _l = math.dist((_ax, _ay), (_bx, _by))
                for _k in range(int(_l) + 1):
                    _u = _k / (_l or 1); _x, _y = _ax + (_bx - _ax) * _u, _ay + (_by - _ay) * _u
                    if _bx0 <= _x <= _bx1 and _by0 <= _y <= TERM['bay_y']: _d = _c + _k; break
                if _d is not None: break
                _c += _l
            _dbay[q[1]] = _d or 0
        if q[4][1] == 0 and _dbay[q[1]] > 0: q[4][1] = min(_dbay[q[1]], q[4][3]); _n += 1
    print('spojů začínajících na nástupišti terminálu', _n)
# čekání na konečné (q[7] = s do odjezdu, kdy vůz už stojí na první zastávce): GTFS čekání nezná, spoj začíná až odjezdem
print('spojů s čekáním na konečné', cekani_na_konecne(out, lambda q: routes[q[0]][1]))
for _i, _w in _vcek.items(): out[_i][7] = _w                      # čekání vlaků (cekani_na_konecne vlaky přeskakuje)
out.sort(key=lambda q: q[3])
# zastávky na mapě (prohlížeč z nich po kliknutí ukáže odjezdy, hledání je najde): [jméno, x, y, druh 0 tramvaj / 3 autobus]
_obsl = {}
for q in out:
    if routes[q[0]][1] == 2: continue
    for i in range(0, len(q[6]), 2): _obsl.setdefault(q[6][i], set()).add(routes[q[0]][1])
stops = []
for sid, (x, y) in SXY.items():
    n_ = NI.get(SN.get(sid))
    if n_ is None or n_ not in _obsl or not AREA.contains(shapely.Point(x, y)): continue
    if any(q[0] == n_ and abs(q[1] - x) < 6 and abs(q[2] - y) < 6 for q in stops): continue   # stejné místo vícekrát (nástupiště, stanice)
    stops.append([n_, round(x, 1), round(y, 1), 0 if 0 in _obsl[n_] else 3])   # trolejbus (11) má zastávku jako autobus
print('zastávek na mapě', len(stops))
# odstav na konečné: kolej za zastávkou končí slepě (do 160 m), tramvaj čeká vzadu na konci koleje, ne na nástupišti
# {tvar: [[[x, y], …] od zastávky po konec koleje, …]}, nejvýš dvě koleje, ať se vozy můžou vystřídat
import heapq as _hq, math as _m
_gk = lambda p: (round(p[0] / 2) * 2, round(p[1] / 2) * 2)
_g = {}
for _c in CHUNKS:
    _f = 'build/info_src.json' if tuple(_c) == (0, 0) else f'build/c{_c[0]}_{_c[1]}/info_src.json'
    if not os.path.exists(_f): continue
    _cx, _cy = chunk_center(_c)
    for _t in json.load(open(_f, encoding='utf-8')).get('trams') or []:
        _p = [(_q[0] + _cx, _q[1] + _cy) for _q in _t]
        for _a, _b in zip(_p, _p[1:]):
            _d = _m.dist(_a, _b)
            if _d: _g.setdefault(_gk(_a), {})[_gk(_b)] = _d; _g.setdefault(_gk(_b), {})[_gk(_a)] = _d
odstav = {}
for _sh in sorted({q[1] for q in out if routes[q[0]][1] == 0 and len(q) > 7 and q[7]}) if _g else []:
    _s0, _s1 = shapes[_sh][0], shapes[_sh][1]
    _st = min(_g, key=lambda k: (k[0] - _s0[0]) ** 2 + (k[1] - _s0[1]) ** 2)
    if _m.dist(_st, _s0) > 6: continue
    _dist, _prev, _h = {_st: 0.0}, {}, [(0.0, _st)]
    while _h:
        _d, _u = _hq.heappop(_h)
        if _d > _dist[_u] or _d > 160: continue
        for _v, _w in _g[_u].items():
            if _d + _w < _dist.get(_v, 1e18): _dist[_v] = _d + _w; _prev[_v] = _u; _hq.heappush(_h, (_d + _w, _v))
    _vyber = []
    for _e in sorted((k for k in _dist if len(_g[k]) == 1 and 20 <= _dist[k] <= 160), key=lambda k: -_dist[k]):
        if any(_m.dist(_e, _o[-1]) < 6 for _o in _vyber): continue
        _pts = [_e]
        while _pts[-1] != _st: _pts.append(_prev[_pts[-1]])
        _pts.reverse()
        _n = _pts[min(3, len(_pts) - 1)]
        if (_n[0] - _pts[0][0]) * (_s1[0] - _s0[0]) + (_n[1] - _pts[0][1]) * (_s1[1] - _s0[1]) < 0: _vyber.append(_pts)   # jen kolej za zastávkou, ne dopředu po trase
        if len(_vyber) == 2: break
    if _vyber: odstav[str(_sh)] = [[[round(float(_a), 1), round(float(_b), 1)] for _a, _b in _o] for _o in _vyber]
print('tvarů s odstavem na konečné', len(odstav))
json.dump({'routes': routes, 'shapes': shapes, 'services': services, 'trips': out, 'names': names, 'odstav': odstav, 'terminal': ({**TERM, 'name': NI.get(TERM['name'])} if TERM else None), 'stops': stops, 'kvalita': kval,
           'feed': next(iter(T('feed_info')), {}).get('feed_version', '') if 'feed_info.txt' in zf.namelist() else time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(Z)))}, open('site/mhd.json', 'w', encoding='utf-8'), separators=(',', ':'), ensure_ascii=False)
print('linek', len(routes), 'tras', len(shapes), 'spojů', len(out), 'kB', os.path.getsize('site/mhd.json') // 1000)
