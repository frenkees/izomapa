"""Předzpracování: Overture Maps + Terrarium DEM -> build/scene.json, build/ground_<sezóna>.png, build/lightmap.png, build/info_src.json

python prep.py [složka_s_daty]
"""
import hashlib, json, math, os, random, sys
import numpy as np, pandas as pd, shapely, pyarrow.parquet as pq
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import transform
from PIL import Image, ImageDraw, ImageFilter
import geo
from geo import HALF, HREF

DATA = sys.argv[1] if len(sys.argv) > 1 else 'data'
CHUNK = tuple(int(v) for v in sys.argv[2].split(',')) if len(sys.argv) > 2 else (0, 0)
OUT = geo.chunk_dir(CHUNK) + ('_plachta' if os.environ.get('IZO_PLACHTA') == '1' else '')   # IZO_PLACHTA=1: varianta scény se zástavbou podle studie (skripty/plachta.sh)
CX, CY = geo.chunk_center(CHUNK)          # všechno níže je v souřadnicích relativních ke středu čtverce


def to_local(lon, lat):
    x, y = geo.to_local(lon, lat); return x - CX, y - CY


def to_lonlat(x, y):
    return geo.to_lonlat(np.asarray(x) + CX, np.asarray(y) + CY)
os.makedirs(OUT, exist_ok=True)
TEX_RES = 2 * HALF / 8000   # m/px textury terénu (max. velikost textury v GPU je 8192 px)
AREA = box(-HALF, -HALF, HALF, HALF)
# Pás sousedů (MARGIN): budovy a stromy u švu se kreslí do obou čtverců stejně, aby přes šev pokračovaly i se stíny.
# Masky (kde nesmí stát strom) se proto kreslí na rozšířený výřez HE, textura terénu se pak ořízne na AREA.
NB = geo.neighbours(CHUNK)
HE = HALF + geo.MARGIN
MPX = round(geo.MARGIN / TEX_RES)           # šířka pásu v pixelech textury
S2 = 2 * HALF
NBOX = [box(di * S2 - HALF, dj * S2 - HALF, di * S2 + HALF, dj * S2 + HALF) for di, dj in NB]
CLIP = shapely.unary_union([AREA] + NBOX)   # mimo tohle už je okraj mapy
EXT = CLIP.intersection(box(-HE, -HE, HE, HE))
EXT_P = shapely.prepared.prep(EXT)


# upřesnění ze satelitních snímků (build/sat/, odvozené hodnoty): barva a typ střechy, povrch hřišť, obrysy snímků
SAT = json.load(open('assets/satelit.json')) if os.path.exists('assets/satelit.json') else {'b': {}, 'lu': {}, 'zones': []}
# ruční upřesnění podle satelitu a 3D fotek: výška/barvy budov (OSM je často nemá), přístřešky, plochy, autobusy
UP = json.load(open('assets/upresneni.json')) if os.path.exists('assets/upresneni.json') else {'b': {}, 'roofs': [], 'paved': [], 'buses': []}
# barvy střech z ortofota (nastroje/strechy.py); ruční úpravy v upresneni.json mají přednost
if os.path.exists('assets/strechy_orto.json'):
    for _k, _v in json.load(open('assets/strechy_orto.json')).items(): SAT['b'].setdefault(_k, {})['rc'] = _v
for _k, _v in UP['b'].items(): SAT['b'][_k] = {**SAT['b'].get(_k, {}), **_v}
# vlastní lokální úpravy konkrétního města (assets/custom_prep.py): oddělené hooky pro terén, hřbitov, doplňky
for _k, _v in UP.get('lu', {}).items(): SAT['lu'][_k] = _v
_CUSTOM_PREP = open('assets/custom_prep.py', encoding='utf-8').read() if os.path.exists('assets/custom_prep.py') else None
def _hook(phase):
    if _CUSTOM_PREP:
        globals()['HOOK'] = phase
        exec(_CUSTOM_PREP, globals())
# typy a podlaží z RÚIAN (nastroje/ruian.py): jen kde data typ nemají nebo je obecný
RUIAN = json.load(open('assets/ruian_budovy.json')) if os.path.exists('assets/ruian_budovy.json') else {}
# oblasti podle skutečnosti (tuning/oblast.py): stromy z ortofota a DMP, barvy střech, ruční úpravy budov
OBL = json.load(open('assets/oblasti.json')) if os.path.exists('assets/oblasti.json') else {}
# varianta „Plachta“ (IZO_PLACHTA=1, assets/plachta_studie.json z ../skripty/plachta_studie.py): hypotetická zástavba podle urbanistické studie.
# Budovy přes custom_bld, trávník a atletický ovál přes plochy, v zóně náhodné stromy pryč a místo nich uliční stromořadí (oblast).
if os.environ.get('IZO_PLACHTA') == '1' and os.path.exists('assets/plachta_studie.json'):
    _PS = json.load(open('assets/plachta_studie.json', encoding='utf-8'))
    UP['custom_bld'] = list(UP.get('custom_bld', [])) + [
        {'id': b['id'], 'poly': b['poly'], 'h': b['h'], 'cls': b['cls'], 'r': 'flat', 'wc': b['wc'], 'rc': b['rc']} for b in _PS['budovy']]
    UP['plochy'] = list(UP.get('plochy', [])) + _PS['plochy']
    UP['hriste'] = list(UP.get('hriste', [])) + _PS.get('hriste', [])
    OBL['plachta_studie'] = {'poly': _PS['zona'], 'trees': _PS['stromy'], 'b': {}, 'b_auto': {}}
for _o in OBL.values():
    for _k, _v in list(_o['b_auto'].items()) + list(_o['b'].items()): SAT['b'][_k] = {**SAT['b'].get(_k, {}), **_v}
HREBENY = json.load(open('assets/hrebeny.json')) if os.path.exists('assets/hrebeny.json') else {}   # nastroje/hrebeny.py
# změřené výšky z DMP 1G (ČÚZK, CC BY 4.0): id -> [medián, p90] nad terénem. Nerozhodují o typu ani tvaru střechy, jen o výšce
DMP = json.load(open('assets/dmp_vysky.json')) if os.path.exists('assets/dmp_vysky.json') else {}
if os.path.exists('assets/dmp_rucne.json'): DMP.update({k: v for k, v in json.load(open('assets/dmp_rucne.json')).items() if not k.startswith('_')})   # ověřená měření z kontrolního seznamu
DMP.update(UP.get('dmp', {}))                                 # ruční doplnění měření
# vlastní modely památek (pamatky/, kreslí je render.html): skutečný vršek modelu pro obrys při najetí myší
# (pamatky/pred_po.mjs zapíše pamatky/vrsky.json; oid v seznamu stačí začátkem). Do dlaždic jdou jen modely schválené
# v dashboardu (pamatky/schvalene.json), proto i vršky jen jejich.
PAM_SCHV = set(json.load(open('pamatky/schvalene.json', encoding='utf-8'))) if os.path.exists('pamatky/schvalene.json') else set()
PAM_VRSKY = [(o, v['vrsek']) for s_, v in (json.load(open('pamatky/vrsky.json', encoding='utf-8')).items() if os.path.exists('pamatky/vrsky.json') else [])
             if s_ in PAM_SCHV for o in v.get('oids', []) if o]
def pam_vrsek(key): return next((v for o, v in PAM_VRSKY if str(key).startswith(o)), None)


def h01(s):
    return int(hashlib.md5(str(s).encode()).hexdigest()[:8], 16) / 0xffffffff


def wkey(x, y):
    """klíč podle polohy ve světových souřadnicích (stejný ve všech čtvercích)"""
    return f'{round(x + CX, 1)},{round(y + CY, 1)}'


def wrng(x, y, salt=''):
    return random.Random(salt + wkey(x, y))


def ihash(*a):
    """deterministická náhoda 0..1 z celých čísel (numpy, vektorově)"""
    with np.errstate(over='ignore'):
        h = np.uint64(0x9E3779B97F4A7C15)
        for v in a:
            h = h ^ (np.asarray(v).astype(np.int64).astype(np.uint64) * np.uint64(0xBF58476D1CE4E5B9) + np.uint64(0x94D049BB133111EB) + (h << np.uint64(6)) + (h >> np.uint64(2)))
        h = (h ^ (h >> np.uint64(31))) * np.uint64(0xBF58476D1CE4E5B9)
        h = (h ^ (h >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        h = h ^ (h >> np.uint64(31))
    return (h >> np.uint64(11)).astype(np.float64) / float(2 ** 53)


def load(name):
    t = pq.read_table(f'{DATA}/{name}.parquet').to_pandas()
    t = t.sort_values('id', kind='stable').reset_index(drop=True)   # pořadí ze S3 není zaručené
    # souřadnice se převádí vektorově nad celým polem geometrií (dřív po jedné Python lambdou: ~10× pomalejší, výsledek stejný)
    t['geom'] = list(shapely.transform(shapely.from_wkb(np.asarray(t.geometry.values, dtype=object)), lambda c: np.column_stack(to_local(c[:, 0], c[:, 1]))))
    return t


def polys(g):
    if g.is_empty: return []
    if isinstance(g, Polygon): return [g]
    if hasattr(g, 'geoms'): return [p for q in g.geoms for p in polys(q)]
    return []


def lines(g):
    if g.is_empty: return []
    if isinstance(g, LineString): return [g]
    if hasattr(g, 'geoms'): return [p for q in g.geoms for p in lines(q)]
    return []


def sname(r):
    n = r.get('names')
    return n.get('primary') if isinstance(n, dict) else None


# ---------------- terén ----------------
def dem_sampler():
    import glob
    tiles = {}
    for f in glob.glob(f'{DATA}/dem/*.png') or glob.glob('data/dem/*.png'):
        _, x, y = os.path.basename(f)[:-4].split('_')
        a = np.asarray(Image.open(f).convert('RGB')).astype(np.float64)
        tiles[(int(x), int(y))] = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
    xs = sorted({k[0] for k in tiles}); ys = sorted({k[1] for k in tiles})
    big = np.zeros((len(ys) * 256, len(xs) * 256))
    for (x, y), a in tiles.items():
        big[(y - ys[0]) * 256:(y - ys[0] + 1) * 256, (x - xs[0]) * 256:(x - xs[0] + 1) * 256] = a
    # oprava zdrojových dat: Terrarium má na švech dlaždic SRTM (např. poledník 15° v. d.) úzké pruhy o desítky metrů níž
    # -> body výrazně pod mediánem okolí 7 × 7 se nahradí mediánem (skutečné rokle mají šířku víc pixelů a zůstanou)
    from numpy.lib.stride_tricks import sliding_window_view as _sw
    med = np.median(_sw(np.pad(big, 3, mode='edge'), (7, 7)), axis=(2, 3))
    pit = big < med - 12
    big = np.where(pit, med, big)
    if pit.any(): print('oprava terénu (pruhy ve zdrojových datech)', int(pit.sum()), 'bodů')
    n = 2 ** 14

    def sample(px, py):
        lon, lat = to_lonlat(px, py)
        gx = (lon + 180) / 360 * n * 256 - xs[0] * 256
        gy = (1 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2 * n * 256 - ys[0] * 256
        x0 = np.floor(gx - 0.5).astype(int); y0 = np.floor(gy - 0.5).astype(int)
        fx = gx - 0.5 - x0; fy = gy - 0.5 - y0
        x0 = np.clip(x0, 0, big.shape[1] - 2); y0 = np.clip(y0, 0, big.shape[0] - 2)
        return (big[y0, x0] * (1 - fx) * (1 - fy) + big[y0, x0 + 1] * fx * (1 - fy)
                + big[y0 + 1, x0] * (1 - fx) * fy + big[y0 + 1, x0 + 1] * fx * fy)
    # terén z laseru DMR 5G (nastroje/teren_dmr.py), kde je; mimo jeho rozsah Terrarium
    if os.path.exists('build/teren_dmr.npz'):
        _d = np.load('build/teren_dmr.npz'); _Z = _d['z'].astype(np.float64); _x0, _y1, _r = float(_d['x0']), float(_d['y1']), float(_d['res'])
        print('terén z DMR 5G (laser ČÚZK)')

        def sample_dmr(px, py):
            wx, wy = np.asarray(px) + CX, np.asarray(py) + CY          # světové souřadnice mapy
            fx = (wx - _x0) / _r - 0.5; fy = (_y1 - wy) / _r - 0.5
            x0 = np.floor(fx).astype(int); y0 = np.floor(fy).astype(int); ax = fx - x0; ay = fy - y0
            ok = (x0 >= 0) & (y0 >= 0) & (x0 < _Z.shape[1] - 1) & (y0 < _Z.shape[0] - 1)
            x0 = np.clip(x0, 0, _Z.shape[1] - 2); y0 = np.clip(y0, 0, _Z.shape[0] - 2)
            v = (_Z[y0, x0] * (1 - ax) * (1 - ay) + _Z[y0, x0 + 1] * ax * (1 - ay) + _Z[y0 + 1, x0] * (1 - ax) * ay + _Z[y0 + 1, x0 + 1] * ax * ay)
            return np.where(ok, v, sample(px, py))
        return sample_dmr
    return sample


dem = dem_sampler()
STEP = 5.0
N = int(2 * HALF / STEP) + 1
# mřížka výšek i s pásem sousedů (MS kroků); body leží na společné světové mřížce, takže se sousedé shodují
MS = int(math.ceil(geo.MARGIN / STEP)) + 2
NE = N + 2 * MS
RE = HALF + MS * STEP
gx, gy = np.meshgrid(np.linspace(-RE, RE, NE), np.linspace(RE, -RE, NE))
HX = dem(gx, gy)
from numpy.lib.stride_tricks import sliding_window_view
_TUN_CAR = {'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'residential', 'unclassified', 'living_street', 'service'}
def _tunnel_zones():
    """pásy nad dlouhými tunely silnic a cest (podjezd pod tratí, tunel pod kopcem): data magistrátu tam nesmí malovat vozovku ani chodník
    přes terén nad tunelem (kraje 3 m u portálů zůstanou). Pro hook assets/custom_prep.py; stejné prahy jako tunnel_parts (TUNNEL_MIN)."""
    out = []
    for _, r in load('segment').iterrows():
        if r.subtype != 'road': continue
        fl = r.road_flags; fl = list(fl) if isinstance(fl, (list, np.ndarray)) else []
        w = 7.0 if r['class'] in _TUN_CAR else 3.5
        for f in fl:
            if 'is_tunnel' not in list(f.get('values')): continue
            t = f.get('between'); t0, t1 = (0.0, 1.0) if t is None else (float(t[0]), float(t[1]))
            if (t1 - t0) * r.geom.length < 60.0: continue
            sub = shapely.ops.substring(r.geom, t0, t1, normalized=True)
            if sub.length > 8: out.append(shapely.ops.substring(sub, 3.0, sub.length - 3.0).buffer(w / 2, cap_style='flat'))
    return shapely.unary_union(out) if out else Polygon()
TUNNEL_ZONES = _tunnel_zones()


def _tunnel_passes():
    """podjezdy silnic pod tratí (kratší „tunel“, který se kreslí jako cesta): [(osa podjezdu, půlšířka)].
    Laser vidí nad podjezdem násyp tratě, takže se v terénu vyřízne zářez a trať se postaví jako most (syntetický is_bridge)."""
    t = load('segment')
    def _fl(r):
        v = r.rail_flags if r.subtype == 'rail' else r.road_flags
        return list(v) if isinstance(v, (list, np.ndarray)) else []
    rails = [r.geom for _, r in t.iterrows() if r.subtype == 'rail' and r['class'] == 'standard_gauge'
             and not any('is_tunnel' in list(f.get('values')) for f in _fl(r))]
    rt = shapely.STRtree(rails) if rails else None
    out = []
    for _, r in t.iterrows():
        if r.subtype != 'road' or r['class'] not in _TUN_CAR: continue
        for f in _fl(r):
            if 'is_tunnel' not in list(f.get('values')): continue
            b = f.get('between'); t0, t1 = (0.0, 1.0) if b is None else (float(b[0]), float(b[1]))
            L = (t1 - t0) * r.geom.length
            if not 12.0 <= L < 60.0 or rt is None: continue
            sub = shapely.ops.substring(r.geom, t0, t1, normalized=True)
            mid = shapely.ops.substring(sub, 3.0, sub.length - 3.0) if sub.length > 8 else sub
            if any(rails[k].intersects(mid) for k in rt.query(mid.buffer(1.0))): out.append((sub, 4.5 if r['class'] != 'service' else 3.5))
    return out
TUNNEL_PASSES = _tunnel_passes()
_hook('terrain')
HX = sliding_window_view(np.pad(HX, 1, mode='edge'), (3, 3)).mean(axis=(2, 3))
HMIN = HREF; HX = HX - HMIN              # společná výška pro všechny čtverce
HX = HX * float(geo.MESTO.get('teren_prevyseni', 1.0))   # volitelné převýšení reliéfu (stejné ve všech čtvercích), např. 1.5
H = HX[MS:MS + N, MS:MS + N]


def ground(x, y):
    fx = (np.asarray(x) + RE) / STEP; fy = (RE - np.asarray(y)) / STEP
    x0 = np.clip(np.floor(fx).astype(int), 0, NE - 2); y0 = np.clip(np.floor(fy).astype(int), 0, NE - 2)
    tx = np.clip(fx - x0, 0, 1); ty = np.clip(fy - y0, 0, 1)
    return (HX[y0, x0] * (1 - tx) * (1 - ty) + HX[y0, x0 + 1] * tx * (1 - ty)
            + HX[y0 + 1, x0] * (1 - tx) * ty + HX[y0 + 1, x0 + 1] * tx * ty)


# zářez pod tratí: laser nad podjezdem vidí násyp, silnice by se přes něj přehnula. Terén podél osy podjezdu klesne na přímku mezi výškami
# 10 m před začátkem a za koncem (jen dolů); do půlšířky plně, pak 5 m plynule do původního terénu.
_gpt = None
for _l, _hw in TUNNEL_PASSES:
    if _gpt is None: _gpt = shapely.points(gx.ravel(), gy.ravel()).reshape(gx.shape)
    _u0 = np.array(_l.coords[1]) - np.array(_l.coords[0]); _u0 /= (np.linalg.norm(_u0) or 1)
    _u1 = np.array(_l.coords[-1]) - np.array(_l.coords[-2]); _u1 /= (np.linalg.norm(_u1) or 1)
    _z0 = float(ground(_l.coords[0][0] - 10 * _u0[0], _l.coords[0][1] - 10 * _u0[1])); _z1 = float(ground(_l.coords[-1][0] + 10 * _u1[0], _l.coords[-1][1] + 10 * _u1[1]))
    _bb = _l.buffer(_hw + 5.0).bounds
    _m = (gx >= _bb[0]) & (gx <= _bb[2]) & (gy >= _bb[1]) & (gy <= _bb[3])
    if not _m.any(): continue
    _pp = _gpt[_m]
    _d = shapely.distance(_pp, _l); _t = np.clip(shapely.line_locate_point(_l, _pp) / _l.length, 0, 1)
    _zt = _z0 + (_z1 - _z0) * _t
    _w = np.clip((_hw + 5.0 - _d) / 5.0, 0, 1)
    _cur = HX[_m]
    HX[_m] = np.where(_cur > _zt + 0.5, _cur * (1 - _w) + _zt * _w, _cur)
    print('zářez podjezdu', round(_l.length), 'm, násyp max', round(float((_cur - _zt).max()), 1), 'm')


# ---------------- hradby a opěrné zdi jako svislé stěny (útesy ve stylu SimCity 2000) ----------------
# U zdi s výškovým rozdílem terénu se svah zalomí: body mřížky do 6 m od zdi dostanou výšku své strany (nahoře / dole),
# zeď se pak kreslí od paty po korunu (scene.lines.cliff). Hradby na rovině jsou samostatná zeď 3,5 m.
CLIFFS = []
_inf0 = load('infrastructure')
_ext = box(-RE, -RE, RE, RE)
_gpts = shapely.points(gx.ravel(), gy.ravel())
for _, r in _inf0.iterrows():
    if r['class'] not in ('city_wall', 'retaining_wall'): continue
    for l in lines(r.geom):
        if l.length < 15 or not l.intersects(_ext): continue          # úlomky hradeb v parku vynechat
        l = l.segmentize(2.0); P_ = np.array(l.coords)[:, :2]
        d_ = np.gradient(P_, axis=0); n_ = np.stack([-d_[:, 1], d_[:, 0]], 1); n_ /= np.linalg.norm(n_, axis=1, keepdims=True) + 1e-9
        zl = ground(*(P_ + n_ * 7).T); zr = ground(*(P_ - n_ * 7).T)
        diff = float(np.median(np.abs(zl - zr))); city = r['class'] == 'city_wall'
        if diff < 2.5: continue                                  # jen skutečné terénní stupně (hradba na rovině = běžná zeď)
        if True:                                         # zalomení terénu u zdi
            st = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(P_, axis=0).T))])
            hi, lo = np.maximum(zl, zr), np.minimum(zl, zr); left_hi = np.median(zl - zr) > 0
            near = np.where(shapely.dwithin(_gpts, l, 8.0))[0]
            if len(near):
                pp = shapely.get_coordinates(_gpts[near]); t_ = shapely.line_locate_point(l, _gpts[near])
                a_ = shapely.get_coordinates(shapely.line_interpolate_point(l, np.maximum(t_ - 0.5, 0)))
                b_ = shapely.get_coordinates(shapely.line_interpolate_point(l, np.minimum(t_ + 0.5, l.length)))
                cross = (b_[:, 0] - a_[:, 0]) * (pp[:, 1] - a_[:, 1]) - (b_[:, 1] - a_[:, 1]) * (pp[:, 0] - a_[:, 0])
                on_hi = (cross > 0) == left_hi
                val = np.where(on_hi, np.interp(t_, st, hi), np.interp(t_, st, lo))
                HX.flat[near] = val
        CLIFFS.append((l, city, diff))
_hook('cliffs')
if CLIFFS: print('hradeb a opěrných zdí', len(CLIFFS), 'z toho se zalomeným terénem', sum(1 for c in CLIFFS if c[2] >= 1.5))

print('terén', N, 'x', N, 'převýšení', round(float(H.max()), 1), 'm')

# ---------------- mapa povrchů (třídy) ----------------
# každá třída má barvu podle ročního období, viz SEASON_PAL níže
C = dict(grass=0, garden=1, park=2, meadow=3, forest=4, scrub=5, pitch=6, track=7, sand=8, paved=9,
         industrial=10, parking=11, road=12, marking=13, curb=14, dirt=15, water=16, pool=17, stream=18,
         rail=19, cemetery=20, wetland=21, rock=22, construction=23, footway=24, pool_edge=25, farmland=26,
         cobble=27, grave=28, manhole=29, court_blue=30, zone=31, zone2=32, piste=33, skijump=34,
         wheat=35, wheat2=36, rape=37, rape2=38, maize=39, maize2=40, soil=41, soil2=42,
         plaza=43, plaza2=44, deck=45, ballast=46)    # pole: plodina + řádky
TW = int(2 * HALF / TEX_RES)
TWE = TW + 2 * MPX                          # rastry včetně pásu sousedů
cls = Image.new('L', (TWE, TWE), C['grass'])
cd = ImageDraw.Draw(cls)
notree = Image.new('L', (TWE, TWE), 0)
nd = ImageDraw.Draw(notree)
DRAWBOX = box(-HE, -HE, HE, HE).buffer(50)


def P(coords):
    return [((x + HE) / TEX_RES, (HE - y) / TEX_RES) for x, y in coords]


def pix(x, y):
    return int((x + HE) / TEX_RES), int((HE - y) / TEX_RES)


def fill(g, c, outline=None, block=False):
    for p in polys(g.intersection(DRAWBOX)):
        cd.polygon(P(p.exterior.coords), fill=c, outline=outline)
        for h in p.interiors: cd.polygon(P(h.coords), fill=C['grass'])
        if block: nd.polygon(P(p.exterior.coords), fill=255)


def line(g, c, w, block=False):
    for l in lines(g.intersection(DRAWBOX)):
        pts = P(l.coords)
        cd.line(pts, fill=c, width=max(1, round(w / TEX_RES)), joint='curve')
        if block: nd.line(pts, fill=255, width=max(1, round((w + 2) / TEX_RES)), joint='curve')


LU = {'residential': 'garden', 'garden': 'garden', 'grass': 'park', 'park': 'park', 'village_green': 'park',
      'recreation_ground': 'park', 'meadow': 'meadow', 'farmland': 'farmland', 'allotments': 'garden',
      'cemetery': 'cemetery', 'pitch': 'pitch', 'track': 'track', 'playground': 'sand', 'stadium': 'pitch',
      'school': 'paved', 'kindergarten': 'garden', 'industrial': 'industrial', 'garages': 'industrial',
      'commercial': 'paved', 'retail': 'paved', 'pedestrian': 'cobble', 'plaza': 'cobble',
      'construction': 'construction', 'railway': 'ballast', 'barracks': 'industrial', 'downhill': 'piste', 'ski_jump': 'skijump'}
NOTREE_LU = {'pitch', 'track', 'playground', 'stadium', 'school', 'industrial', 'garages', 'commercial',
             'retail', 'pedestrian', 'plaza', 'construction', 'railway', 'downhill', 'ski_jump'}
lu = load('land_use')
lu['area'] = lu.geom.map(lambda g: g.area)
lu = lu.sort_values('area', ascending=False)
def _green_share(g):
    # podíl zeleně z ortofota (nastroje/povrchy.py) na mřížce po 5 m v ploše
    if not os.path.exists('build/zelen_maska.png'): return 0.0
    x0_, y0_, x1_, y1_ = g.bounds; xs_, ys_ = np.meshgrid(np.arange(x0_, x1_, 5.0), np.arange(y0_, y1_, 5.0))
    inside = shapely.contains_xy(g, xs_, ys_)
    if inside.sum() < 8: return 0.0
    z_, h_ = _GZ
    return float(z_[np.clip(((h_[1] - (ys_[inside] + CY)) / h_[2]).astype(int), 0, z_.shape[0] - 1), np.clip(((xs_[inside] + CX - h_[0]) / h_[2]).astype(int), 0, z_.shape[1] - 1)].mean())
_GZ = None
if os.path.exists('build/zelen_maska.png'):
    _gz = np.asarray(Image.open('build/zelen_maska.png')) > 0
    if os.path.exists('build/les_maska.png'):                   # koruny stromů jsou tmavé a maska zeleně je nepočítá
        _lz = np.asarray(Image.open('build/les_maska.png')) > 0
        if _lz.shape == _gz.shape: _gz = _gz | _lz
    _GZ = (_gz, json.load(open('build/zelen_maska.json'))['x0y1m'])
_PARK_Z = set()
for _, r in lu.iterrows():
    k = SAT['lu'].get(r.id) or LU.get(r['class'])
    block_ = r['class'] in NOTREE_LU
    if k == 'cobble' and _green_share(r.geom) > 0.5: k = 'park'; block_ = False; _PARK_Z.add(r.id)      # náměstí, které je ve skutečnosti park
    if k: fill(r.geom, C[k], block=block_)
# zpevněné plochy z dat, které jsou na ortofotu zelené, jsou tráva (nastroje/povrchy.py)
if os.path.exists('build/zelen_maska.png'):
    _zm = np.asarray(Image.open('build/zelen_maska.png')) > 0; _x0, _y1, _m = json.load(open('build/zelen_maska.json'))['x0y1m']
    _c = (np.arange(TWE) + 0.5) * TEX_RES - HE
    _mx = np.clip(((_c + CX - _x0) / _m).astype(int), 0, _zm.shape[1] - 1); _my = np.clip(((_y1 - (-_c + CY)) / _m).astype(int), 0, _zm.shape[0] - 1)
    _a = np.array(cls); _hit = _zm[np.ix_(_my, _mx)] & np.isin(_a, [C['paved'], C['industrial']])
    _a[_hit] = C['grass']; cls.paste(Image.fromarray(_a))
    _n = np.array(notree); _n[_hit] = 0; notree.paste(Image.fromarray(_n))
# pitch: bílé čáry hřiště. Překrývající se hřiště z dat se sloučí (jinak se čáry kříží); čáry jen u zhruba obdélníkových
pitch_polys = [p for _, r in lu.iterrows() if r['class'] == 'pitch' and SAT['lu'].get(r.id, 'pitch') in ('pitch', 'track', 'court_blue')
               for p in polys(r.geom.intersection(DRAWBOX)) if p.area > 30]
for p in polys(shapely.unary_union(pitch_polys)) if pitch_polys else []:
    o = p.minimum_rotated_rectangle
    if p.area / max(o.area, 1) < 0.86: continue                 # nepravidelný tvar: jen plocha bez čar
    q = o.buffer(-0.6, join_style=2)
    if q.is_empty: continue
    oc = [np.array(c) for c in list(q.exterior.coords)[:4]]
    e1, e2 = oc[1] - oc[0], oc[3] - oc[0]
    if np.linalg.norm(e1) < np.linalg.norm(e2): oc = [oc[0], oc[3], oc[2], oc[1]]; e1, e2 = e2, e1
    L, W = np.linalg.norm(e1), np.linalg.norm(e2); u, v = e1 / L, e2 / W
    if L < 12 or W < 6: continue
    pt = lambda s_, t_: tuple(oc[0] + u * s_ + v * t_)
    cd.polygon(P([pt(0, 0), pt(L, 0), pt(L, W), pt(0, W)]), outline=C['marking'])
    cd.line(P([pt(L / 2, 0), pt(L / 2, W)]), fill=C['marking'], width=1)        # středová čára napříč
    if L > 70 and W > 40:                                                       # fotbal: kruh a vápna
        r_ = 9.15; cx_, cy_ = pt(L / 2, W / 2)
        cd.line(P([(cx_ + r_ * math.cos(k / 24 * math.tau) * u[0] + r_ * math.sin(k / 24 * math.tau) * v[0],
                    cy_ + r_ * math.cos(k / 24 * math.tau) * u[1] + r_ * math.sin(k / 24 * math.tau) * v[1]) for k in range(25)]), fill=C['marking'], width=1)
        for s0, s1 in ((0, 16.5), (L, L - 16.5)):
            w0, w1 = W / 2 - 20.15, W / 2 + 20.15
            cd.line(P([pt(s0, w0), pt(s1, w0), pt(s1, w1), pt(s0, w1)]), fill=C['marking'], width=1)

land = load('land')
LAND = {'forest': 'forest', 'wood': 'forest', 'scrub': 'scrub', 'shrub': 'scrub', 'grassland': 'meadow',
        'wetland': 'wetland', 'bare_rock': 'rock', 'rock': 'rock'}
for _, r in land.iterrows():
    if r['class'] in LAND and r.geom.geom_type != 'Point':
        fill(r.geom, C[LAND[r['class']]])
# sjezdovky jsou v datech jen čáry: vykácený pás (v létě louka, v zimě sníh)
PISTE = [l for _, r in lu.iterrows() if r['class'] == 'downhill' for l in lines(r.geom)]
for l in PISTE: fill(l.buffer(22), C['piste'], block=True)
# les podle ortofota (build/les_maska.png = koruny po 2 m, tuning/les_chyby.py): kde nejsou koruny, je louka a žádné stromy
LESM = None
if os.environ.get('IZO_LES', '1') != '0' and os.path.exists('build/les_maska.png'):   # IZO_LES=0 vypne
    Image.MAX_IMAGE_PIXELS = None
    _MX0, _MY1, _MM = json.load(open('build/les_maska.json'))['x0y1m']     # z nastroje/les.py
    _m = Image.open('build/les_maska.png').crop((round((CX - HE - _MX0) / _MM), round((_MY1 - CY - HE) / _MM),
                                                 round((CX + HE - _MX0) / _MM), round((_MY1 - CY + HE) / _MM))).resize((TWE, TWE), Image.NEAREST)
    LESM = np.asarray(_m) > 0
    cls.paste(C['meadow'], mask=Image.fromarray(((np.asarray(cls) == C['forest']) & ~LESM).astype(np.uint8) * 255))
# ZABAGED (ČÚZK): trvalý travní porost = louka, orná půda = pole s plodinou a řádky ve směru delší strany, sad/zahrada
def _zpoly(rings):
    sh = [list(zip(*[np.asarray(v, float) for v in to_local([q[1] for q in r], [q[0] for q in r])])) for r in rings]
    return shapely.make_valid(Polygon(sh[0], sh[1:]))
ZAB = json.load(open('assets/zabaged.json')) if os.path.exists('assets/zabaged.json') else {'orna': [], 'ttp': [], 'sad': []}
_zb = box(-HE, -HE, HE, HE)
_pole = set(ZAB.get('pole', []))                # travní porost, který je na ortofotu žlutohnědý = pole (tuning/pole.py)
ZTTP = [g for i, r in enumerate(ZAB['ttp']) if i not in _pole for g in [_zpoly(r)] if g.intersects(_zb)]
# orna_dil: bloky rozdělené podle cest a ortofota (nastroje/pole_cesty.py), orna_plodina: plodina podle barvy na ortofotu
_orna = ZAB['orna_dil'] if 'orna_dil' in ZAB else ZAB['orna'] + [ZAB['ttp'][i] for i in sorted(_pole)]
_plod = ZAB.get('orna_plodina') if 'orna_dil' in ZAB else None
ZORNA = [(g, _plod[i] if _plod else None) for i, r in enumerate(_orna) for g in [_zpoly(r)] if g.intersects(_zb)]
ZSAD = [g for g in map(_zpoly, ZAB['sad']) if g.intersects(_zb)]
for g in ZTTP: fill(g, C['meadow'])
CROPS = ['wheat'] * 4 + ['rape'] * 2 + ['maize'] * 2 + ['soil'] * 2
for g, cr in ZORNA:
    # plodina a směr řádků podle celého pole (ne podle kusu v tomto čtverci), aby pole na švu čtverců navazovalo
    o = g.minimum_rotated_rectangle; oc = list(o.exterior.coords)[:4]
    e1 = np.subtract(oc[1], oc[0]); e2 = np.subtract(oc[2], oc[1])
    if np.linalg.norm(e1) < np.linalg.norm(e2): e1, e2 = e2, e1
    u = e1 / np.linalg.norm(e1)
    if u[0] < 0 or (u[0] == 0 and u[1] < 0): u = -u              # stejná orientace ve všech čtvercích
    v = np.array([-u[1], u[0]]); c0 = np.array(g.centroid.coords[0])
    cr = cr or CROPS[int(h01(wkey(c0[0], c0[1]) + 'pole') * len(CROPS))]   # wkey sám přičte CX, CY (světové souřadnice)
    for p in polys(g.intersection(DRAWBOX)):
        if p.area < 400: continue
        fill(p, C[cr])
        pc = np.array(p.exterior.coords) - c0; pu_, pv_ = pc @ u, pc @ v
        k = math.floor(pv_.min() / 2.0) * 2.0
        while k < pv_.max():                         # řádky po 2 m na mřížce celého pole
            l = LineString([tuple(c0 + v * k + u * (pu_.min() - 1)), tuple(c0 + v * k + u * (pu_.max() + 1))]).intersection(p)
            if not l.is_empty: line(l, C[cr + '2'], 0.6)
            k += 2.0

inf = load('infrastructure')
parkings = []
for _, r in inf.iterrows():
    if r['class'] == 'parking' and r.geom.geom_type in ('Polygon', 'MultiPolygon'):
        fill(r.geom, C['parking'], block=True)
        tg = dict(r.source_tags) if r.get('source_tags') is not None else {}
        parkings += [(r.id, p, tg) for p in polys(r.geom.intersection(AREA))]
for _, r in inf.iterrows():                             # autobusové nádraží: asfalt bez stání, nástupiště dlážděná
    if r['class'] == 'bus_station' and r.geom.geom_type in ('Polygon', 'MultiPolygon'): fill(r.geom, C['parking'], block=True)
for _, r in inf.iterrows():
    if r['class'] == 'platform' and r.subtype == 'transit' and r.geom.geom_type in ('Polygon', 'MultiPolygon') and r.geom.area < 2000: fill(r.geom, C['paved'], block=True)
for q in UP['paved']: fill(Polygon([to_local(lo, la) for la, lo in q]), C['paved'], block=True)

wat = load('water')
POTOKY = bool(geo.MESTO.get('potoky'))           # potoky (waterway=stream) jen na přání: v datech často vedou pod zemí (zatrubněné)
def podzemni(r):                                 # zatrubněný / podzemní úsek vodního toku (OSM tunnel=culvert|yes, layer < 0)
    st = dict(r['source_tags']) if r.get('source_tags') is not None else {}
    try: lay = float(st.get('layer', 0))
    except ValueError: lay = 0
    return st.get('tunnel') in ('yes', 'culvert', 'flooded') or lay < 0
def carkovane(g, c, w, on=3.0, off=3.0):          # přerušovaná čára (zatrubněný potok): úseky po délce celé čáry, na švech navazují
    for l in lines(g):
        s = 0.0
        while s < l.length:
            q = shapely.ops.substring(l, s, min(s + on, l.length))
            if q.length > 0.3: line(q, c, w)
            s += on + off
_bld_stream_excl = shapely.unary_union([p.buffer(1.2) for g in load('building').geom for p in polys(g) if p.intersects(DRAWBOX)]) if POTOKY else shapely.geometry.GeometryCollection()
for _, r in wat.iterrows():
    g = r.geom
    if g.geom_type in ('Polygon', 'MultiPolygon'):
        if r['class'] == 'swimming_pool': fill(g, C['pool'], outline=C['pool_edge'], block=True)
        else: fill(g, C['water'], block=True)
    elif r['class'] in ('river', 'stream') and podzemni(r):          # pod zemí: jen tenká přerušovaná čára
        if r['class'] == 'river' or POTOKY: carkovane(g, C['stream'], 1.6 if r['class'] == 'stream' else 2.4)
    elif r['class'] == 'river':
        line(g, C['stream'], 6, block=True)
    elif r['class'] == 'stream' and POTOKY:   # potoky (mimo půdorysy budov, kde bývají zatrubněné)
        g_vis = g.difference(_bld_stream_excl) if not _bld_stream_excl.is_empty else g
        if not g_vis.is_empty:
            line(g_vis, C['stream'], 4.8 if sname(r) else 2.8, block=True)

seg = load('segment')
# dálnice ve výstavbě se nekreslí (staveniště je vidět ve využití území)
_uc = lambda r: r['class'] == 'motorway' and any('is_under_construction' in list(f.get('values')) for f in (r.road_flags if r.road_flags is not None else []))
seg = seg[[not _uc(r) for _, r in seg.iterrows()]].reset_index(drop=True)
# uzly sítě (connectors): bod, ve kterém se potkávají aspoň dva úseky, je úrovňové křížení nebo připojení – ne cesta pod mostem
_cn = {}
for _g, _cs in zip(seg.geom, seg.connectors if 'connectors' in seg else [None] * len(seg)):
    if _cs is None or _g.geom_type != 'LineString': continue
    for _q in _cs: _cn.setdefault(_q['connector_id'], []).append((_g, float(_q['at'])))
_JP = [v[0][0].interpolate(v[0][1], normalized=True) for v in _cn.values() if len(v) > 1]
_JP_T = shapely.STRtree(_JP) if _JP else None
def is_node(g, r=1.5):
    return _JP_T is not None and len(_JP_T.query(g, predicate='dwithin', distance=r)) > 0
TUNNEL_MIN = 60.0     # kratší „tunel“ je podjezd pod silnicí nebo tratí: kreslí se jako cesta, nad ní vede most
def seg_flags(r):
    """příznaky úseku: silnice je mají v road_flags, tratě v rail_flags"""
    v = r.get('rail_flags') if r.subtype == 'rail' else r.road_flags
    return list(v) if isinstance(v, (list, np.ndarray)) else []
def tunnel_parts(r):
    """části segmentu mimo tunel (0..1); dlouhé tunely se nekreslí, silnice je pod zemí"""
    fl = seg_flags(r)
    tn = [f.get('between') for f in fl if 'is_tunnel' in list(f.get('values'))]
    tn = [t for t in tn if (1.0 if t is None else float(t[1]) - float(t[0])) * r.geom.length >= TUNNEL_MIN]
    if not tn: return None
    if any(t is None for t in tn): return []
    out, a = [], 0.0
    for t0, t1 in sorted((float(t[0]), float(t[1])) for t in tn):
        if t0 > a: out.append((a, t0))
        a = max(a, t1)
    if a < 1: out.append((a, 1.0))
    return out
_rows, portals = [], []
for _, r in seg.iterrows():
    tp = tunnel_parts(r)
    if tp is None: _rows.append(r); continue
    for i, (a, b_) in enumerate(tp):
        q = r.copy(); q['geom'] = shapely.ops.substring(r.geom, a, b_, normalized=True); _rows.append(q)
    if r['class'] in _TUN_CAR:                          # portály na koncích tunelu (hw = poloviční světlá šířka)
        _hw = 6.6 if r['class'] in ('trunk', 'motorway') else 4.4 if r['class'] != 'service' else 3.2
        for a, b_ in tp:
            for t, sg in ((a, 1), (b_, -1)):
                if 0 < t < 1:
                    p0 = r.geom.interpolate(t, normalized=True); p1 = r.geom.interpolate(max(0, min(1, t + sg * 0.004)), normalized=True)
                    portals.append((p0.x, p0.y, math.atan2(p1.y - p0.y, p1.x - p0.x), _hw))
seg = pd.DataFrame(_rows).reset_index(drop=True)
# trať nad podjezdem silnice: Overture ji nemá jako most, proto se přidá úsek is_bridge přes pás podjezdu (postaví se mostovka)
if TUNNEL_PASSES:
    _zb = shapely.unary_union([l.buffer(hw + 2.0, cap_style='flat') for l, hw in TUNNEL_PASSES])
    for _i, _r in seg.iterrows():
        if _r.subtype != 'rail' or not _r.geom.intersects(_zb): continue
        _fl = _r.rail_flags; _fl = list(_fl) if isinstance(_fl, (list, np.ndarray)) else []
        for _g in lines(_r.geom.intersection(_zb)):
            if _g.length < 4: continue
            _t0 = _r.geom.project(Point(_g.coords[0])) / _r.geom.length; _t1 = _r.geom.project(Point(_g.coords[-1])) / _r.geom.length
            _fl.append({'values': np.array(['is_bridge']), 'between': np.array([min(_t0, _t1), max(_t0, _t1)])})
        seg.at[_i, 'rail_flags'] = _fl
# mosty a lávky: úsek označený is_bridge se nekreslí do terénu, ale postaví se jako mostovka (scene.bridges)
BRIDGE_MIN = UP.get('bridge_min', 8.0)      # kratší „most“ (propustek nad potokem) zůstane obyčejnou cestou
def bridge_parts(r):
    fl = seg_flags(r)
    br = [f.get('between') for f in fl if 'is_bridge' in list(f.get('values'))]
    if not br: return None
    rng = sorted((0.0, 1.0) if t is None else (float(t[0]), float(t[1])) for t in br)
    out, a = [], 0.0
    for t0, t1 in rng:
        if t0 > a: out.append((a, t0, False))
        out.append((max(a, t0), t1, True)); a = max(a, t1)
    if a < 1: out.append((a, 1.0, False))
    return out
_rows, bridge_segs, _bridge_raw = [], [], []          # _bridge_raw: kusy mostů před spojením (jednosměrky pro mostovky)
for _, r in seg.iterrows():
    bp = bridge_parts(r)
    if bp is None: _rows.append(r); continue
    for a, b_, isb in bp:
        if b_ - a < 1e-6: continue
        g = shapely.ops.substring(r.geom, a, b_, normalized=True)
        if isb and g.length >= BRIDGE_MIN: bridge_segs.append((g, r)); _bridge_raw.append((g, r)); continue
        q = r.copy(); q['geom'] = g; _rows.append(q)
seg = pd.DataFrame(_rows).reset_index(drop=True)
# nesmyslná křížení: dálnice se neprotíná v úrovni terénu. Cesta (bez mostu a tunelu, bez společného uzlu), která hlavní jízdní pás dálnice kříží, se u něj
# přeruší (ve skutečnosti končí u plotu nebo vede po straně; v OSM/Overture bývá napojená přes dálnici omylem, i se společným uzlem). Vypnout IZO_DALNICE_KRIZENI=0.
if os.environ.get('IZO_DALNICE_KRIZENI', '1') != '0':
    _mw = [r_.geom for _, r_ in seg.iterrows() if r_['class'] == 'motorway' and r_.subtype == 'road' and str(r_.get('subclass')) != 'link']
    if _mw:
        _mwt = shapely.STRtree(_mw); _rows2, _ncl = [], 0
        for _, r_ in seg.iterrows():
            if r_['class'] == 'motorway' or r_.subtype == 'rail' or any('is_tunnel' in list(f_.get('values')) for f_ in seg_flags(r_)):
                _rows2.append(r_); continue
            _cut = []
            for k_ in _mwt.query(r_.geom, predicate='crosses'):
                x_ = r_.geom.intersection(_mw[int(k_)])
                for pt_ in ([x_] if x_.geom_type == 'Point' else list(getattr(x_, 'geoms', []))):
                    if pt_.geom_type == 'Point': _cut.append(pt_.buffer(19.0))   # i při společném uzlu: dálnice nemá úrovňové křižovatky s cestami (chyba dat)
            if not _cut: _rows2.append(r_); continue
            _ncl += 1
            for g_ in lines(r_.geom.difference(shapely.unary_union(_cut))):
                if g_.length >= 3.0: q_ = r_.copy(); q_['geom'] = g_; _rows2.append(q_)
        if _ncl: print('cest přerušených u dálnice (křížení bez mostu a uzlu):', _ncl)
        seg = pd.DataFrame(_rows2).reset_index(drop=True)
RW = {'motorway': 18, 'trunk': 12, 'primary': 10, 'secondary': 9, 'tertiary': 8, 'residential': 6, 'unclassified': 6,
      'living_street': 5, 'service': 3.6, 'pedestrian': 4, 'track': 3, 'footway': 1.8, 'path': 1.6,
      'cycleway': 2, 'steps': 2, 'bridleway': 1.6, 'unknown': 3}
def rwidth(r):
    """šířka silnice: RW je obousměrná; jednosměrný pás dvoupásové silnice ~60 %, sjezd (link) jeden pruh 5 m"""
    w = RW.get(r['class'], 3)
    if r['class'] not in ('motorway', 'trunk', 'primary', 'secondary', 'tertiary'): return w
    if str(r.get('subclass')) == 'link': return min(w, 5.0)
    acc = r.get('access_restrictions')
    oneway = acc is not None and not isinstance(acc, float) and any(
        a.get('access_type') == 'denied' and (a.get('when') or {}).get('heading') == 'backward' and a.get('between') is None for a in acc)
    return round(w * 0.6, 1) if oneway else w
RCLS = {'track': 'dirt', 'path': 'dirt', 'bridleway': 'dirt', 'footway': 'footway', 'cycleway': 'footway',
        'steps': 'paved', 'pedestrian': 'cobble'}
DRIVE = {'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'residential', 'unclassified', 'living_street', 'service'}
roads = []
for _, r in seg.iterrows():
    c = r['class']
    if r.subtype == 'rail': roads.append((0, r.geom, 'rail', 3, sname(r))); continue
    if c in RW: w_ = rwidth(r); roads.append((w_, r.geom, c, w_, sname(r)))
# ---------------- mosty a lávky: výška mostovky a nájezdy ----------------
# Mostovka nad silnicí/tratí/vodou musí mít podjezdnou výšku. Aby to nebyl „skokánek“, nájezd se rozloží do navazující
# cesty se stoupáním nejvýš GRADE (silnice 6 %, trať 3 %, lávka 8 %); ta část cesty se pak nekreslí do terénu, ale jako mostovka.
FOOT = {'footway', 'path', 'cycleway', 'steps', 'pedestrian', 'bridleway', 'track'}
GRADE = {'road': 0.06, 'rail': 0.03, 'foot': 0.08}
roads = [(a_, l_, c_, w_, n_) for a_, g_, c_, w_, n_ in roads for l_ in lines(g_)]
if os.environ.get('IZO_PLACHTA') == '1' and os.path.exists('assets/plachta_studie.json'):    # sídliště nahrazuje dnešní lesní cesty v zóně
    _zp = Polygon([to_local(lo, la) for la, lo in _PS['zona']])
    roads = [r_ for r_ in roads if not (r_[2] in ('track', 'path', 'footway', 'cycleway', 'steps', 'bridleway') and r_[1].intersects(_zp))]
_under = shapely.STRtree([g for _, g, c, w, _n in roads])
_water = shapely.unary_union([r.geom.buffer(4) for _, r in wat.iterrows()] or [Point(1e9, 1e9)])
_rused, _rcut = set(), {}                 # cesty nájezdů tohoto mostu; index -> odříznuté úseky [(a, b)]
def _approach(pt, dv, kind):
    """navazující cesty od konce mostu směrem dv (stejný druh), nejvýš 8 kusů / 200 m: [(index, směr, odkud)]
    směr True = po směru čáry od parametru t, False = proti směru od t (konec mostu může ležet i uprostřed cesty)"""
    out, tot = [], 0.0
    for _ in range(8):
        best = None
        for j in _under.query(Point(pt).buffer(1.0)):
            j = int(j)
            if j in _rused: continue
            _a, l_, c_, _w, _n = roads[j]
            if (c_ == 'rail') != (kind == 'rail') or (kind != 'rail' and (c_ in FOOT) != (kind == 'foot')): continue
            if l_.length < 0.5 or l_.distance(Point(pt)) > 1.0: continue
            t = l_.project(Point(pt))
            for fs in (True, False):
                rest = l_.length - t if fs else t
                if rest < 0.5: continue
                q = l_.interpolate(t + min(5.0, rest) if fs else t - min(5.0, rest)); pa = l_.interpolate(t)
                vx, vy = q.x - pa.x, q.y - pa.y; nv = math.hypot(vx, vy) or 1
                ca_ = (vx * dv[0] + vy * dv[1]) / nv
                if ca_ > {'road': 0.5, 'rail': 0.7, 'foot': -0.1}[kind] and (best is None or ca_ > best[0]): best = (ca_, j, fs, t)
        if best is None: break
        _, j, fs, t = best; _rused.add(j); out.append((j, fs, t))
        l_ = roads[j][1]; tot += (l_.length - t) if fs else t
        e = l_.coords[-1] if fs else l_.coords[0]; e2 = l_.interpolate(max(t, l_.length - 3)) if fs else l_.interpolate(min(t, 3.0))
        vx, vy = e[0] - e2.x, e[1] - e2.y; nv = math.hypot(vx, vy) or 1; dv = (vx / nv, vy / nv); pt = e[:2]
        if tot >= 200: break
    return out
def _oriented(j, fs, t):                   # souřadnice nájezdu ve směru od mostu
    l_ = roads[j][1]
    cs = [c_[:2] for c_ in (shapely.ops.substring(l_, t, l_.length) if fs else shapely.ops.substring(l_, 0, t)).coords]
    return cs if fs else cs[::-1]
def _cut(app, c):                          # odříznout z cest nájezdu délku c od mostu, zbytek zůstane v terénu
    for j, fs, t in app:
        l_ = roads[j][1]; avail = l_.length - t if fs else t
        a, b = (t, min(l_.length, t + c)) if fs else (max(0.0, t - c), t)
        if b - a > 0.3: _rcut.setdefault(j, []).append((a, b))
        c -= avail
        if c <= 0.3: break
AB_R = 40.0                               # jak daleko před mostem se hledá úroveň silnice u opěry
def _junction(pt, app, used, kind):
    """vzdálenost první křižovatky na nájezdu od konce mostu (inf = žádná); app = body nájezdu směrem od mostu.
    Silniční most: připojení jiné silnice; lávka: jakékoli cesty; trať: nesleduje se (výhybky).
    Křižovatka = jiná cesta se k nájezdu připojuje koncem nebo ho kříží ve společném uzlu (křížení bez uzlu je podjezd)."""
    if kind == 'rail' or not app: return math.inf
    al = LineString([tuple(pt)] + [tuple(q) for q in app]); best = math.inf
    for k in _under.query(al.buffer(0.7)):
        k = int(k)
        if k in used: continue
        c_ = roads[k][2]
        if c_ == 'rail' or (kind == 'road' and c_ not in DRIVE): continue
        for q in (roads[k][1].coords[0], roads[k][1].coords[-1]):
            if al.distance(Point(q[:2])) < 0.7: best = min(best, al.project(Point(q[:2])))
        x_ = roads[k][1].intersection(al)
        if not x_.is_empty and is_node(x_): best = min(best, al.project(x_.representative_point()))
    return best
# most bývá v datech rozdělený na víc kusů za sebou: spojit, ať mostovka mezi nimi nepřistává na zem
def _bkind(r): return 'rail' if r.subtype == 'rail' else 'foot' if r['class'] in FOOT else 'road'
_bg = {}
for g0, r in bridge_segs: _bg.setdefault(_bkind(r), []).append((g0, r))
bridge_segs = []
for _k, items in _bg.items():
    for l in lines(shapely.ops.linemerge(shapely.MultiLineString([q for g0, _r in items for q in lines(g0)]))):
        bridge_segs.append((l, max(items, key=lambda it: it[0].intersection(l.buffer(0.5)).length)[1]))
# chodník mostu zakreslený v OSM zvlášť (sidewalk=separate): lávka, která z většiny vede v pásu silničního mostu, se nekreslí
# jako druhá mostovka vedle (s vlastními pilíři a odbočkou k nábřeží), silniční mostovka se o ni rozšíří
_road_b = [(l, r) for l, r in bridge_segs if _bkind(r) == 'road']
_road_tree = shapely.STRtree([l for l, _ in _road_b]) if _road_b else None
_sidewalk_w, _keep = {}, []
for l, r in bridge_segs:
    if _bkind(r) == 'foot' and _road_tree is not None:
        hit = next((k for k in _road_tree.query(l.buffer(15))
                    if l.intersection(_road_b[k][0].buffer(rwidth(_road_b[k][1]) / 2 + 3.5, cap_style=2)).length >= 0.7 * l.length), None)
        if hit is not None:
            _sidewalk_w[_road_b[hit][0].wkb] = _sidewalk_w.get(_road_b[hit][0].wkb, 0.0) + 2.4
            continue
    _keep.append((l, r))
if len(_keep) < len(bridge_segs): print('chodníků sloučených se silničním mostem', len(bridge_segs) - len(_keep))
bridge_segs = _keep
DECKS = []                                  # (čára, vzdálenosti, výšky mostovky, výšky terénu, šířka, druh, třída, název)
_back = []                                  # konce mostů z dat, které leží na terénu: (čára, úsek) -> zpět mezi cesty
bridge_segs.sort(key=lambda it: -it[0].length)
# Mostovky se počítají společně ve třech krocích: 1) podklady každého kusu (nájezdy, terén, podjezdné výšky), 2) vazby mezi kusy
# (konec kusu na jiné mostovce = uzel estakády, sjezd z mostu; souběžné kusy jednoho mostu = pásy pro každý směr a chodníky zvlášť)
# a výšky opakovaně, dokud se v uzlech a mezi souběžnými pásy neshodnou, 3) oříznutí nájezdů na terénu a zápis do DECKS.
def _abut(P, emin=(-1e9, -1e9)):
    """opěry: laser (DMR) má pod mostem břeh, ne mostovku, a konec mostu v datech bývá až nad svahem břehu. Úroveň opěry je proto
    úroveň navazující cesty do AB_R m před mostem (sklon k mostu nejvýš G/2); emin = úroveň opěry souběžného pásu téhož mostu
    (společná opěra). Vrací (ge, E): ge = „terén“ pro nájezdy s vyplněným břehem u konců, E = úrovně obou opěr."""
    d, gz, G = P['d'], P['gz'], P['G']
    ge, E = gz.copy(), []
    for e_, (e_d, zone) in enumerate(((P['ds0'], (d > P['ds0'] - AB_R) & (d <= P['ds0'] + 0.01)), (P['ds1'], (d < P['ds1'] + AB_R) & (d >= P['ds1'] - 0.01)))):
        zi = np.where(zone)[0]
        zi = zi[np.argsort(np.abs(d[zi] - e_d))]                     # od konce mostu ven
        so = np.abs(d[zi] - e_d)
        sup = np.array([max(np.max(gz[zi[k:]] - G / 2 * (so[k:] - so[k])), emin[e_] - G / 2 * so[k]) for k in range(len(zi))])   # podpírá jen terén dál od mostu
        low = np.where(sup - gz[zi] <= 0.3)[0]                       # výplň břehu jen souvisle od konce mostu po první místo na terénu
        n_ = int(low[0]) if len(low) else len(zi)
        ge[zi[:n_]] = sup[:n_]
        E.append(max(float(ge[zi[0]]), float(emin[e_])))
    return ge, E
def _niveleta(P, zx, En, jn):
    """výška mostovky kusu P; zx = výšky vyžádané jinými mostovkami (uzly, souběžné pásy), En = výška uzlu na konci, který leží
    na jiné mostovce (jn), jinak -1e9. Vrací (z, ge, req, E)."""
    d, gz, G, ds0, ds1, span, kind = P['d'], P['gz'], P['G'], P['ds0'], P['ds1'], P['span'], P['kind']
    E = [max(P['E'][k], En[k]) for k in (0, 1)]
    # mezi opěrami vede mostovka přímo (ge = „terén“ pro nájezdy: břeh u konců vyplněný, v rozpětí spojnice opěr). Most přes řeku tak
    # leží v rovině silnice a nepotřebuje nájezdy; ty vzniknou jen tam, kde spojnice opěr nestačí na podjezdnou výšku.
    ge = P['ge'].copy(); ge[span] = np.interp(d[span], [ds0, ds1], E)
    req = np.maximum(np.maximum(ge, gz) + 0.15, np.maximum(P['rx'], zx))
    # nájezd nesmí pokračovat přes křižovatku (křižovatka je na zemi): za první křižovatkou od konce mostu je mostovka na terénu,
    # před ní přistane strměji (max. 20 %). Konec na jiné mostovce nepřistává.
    jd = P['jd']
    dcl = np.minimum(np.maximum(d - max(0.0, ds0 - jd[0]), 0) if not jn[0] else np.full_like(d, 1e9),
                     np.maximum(min(d[-1], ds1 + jd[1]) - d, 0) if not jn[1] else np.full_like(d, 1e9))
    hr = req - ge                                  # požadovaná výška nad terénem; nájezd ji ubírá o G na metr (cesta dál kopíruje svah)
    hz = np.max(hr[None, :] - G * np.abs(d[:, None] - d[None, :]), axis=1)
    hz = np.minimum(hz, 0.15 + 0.2 * dcl)   # konce vždy na terénu (krátký nájezd = strmější), mimo napojení na jinou mostovku
    z = np.maximum(ge + np.maximum(hz, 0.15), gz + 0.15)
    si = np.where(span)[0]
    hull = []                                      # v rozpětí mostu horní konvexní obálka (bez propadů)
    for pt_ in zip(d[si], z[si]):
        while len(hull) >= 2 and (hull[-1][0] - hull[-2][0]) * (pt_[1] - hull[-2][1]) - (hull[-1][1] - hull[-2][1]) * (pt_[0] - hull[-2][0]) >= 0: hull.pop()
        hull.append(pt_)
    z[si] = np.interp(d[si], [q[0] for q in hull], [q[1] for q in hull])
    return z, ge, req, E
# ---- 1) podklady kusů ----
_PP = []
for g0, r in bridge_segs:
    for l in lines(g0):
        if not l.intersects(DRAWBOX): continue
        c = r['class']
        kind = 'rail' if r.subtype == 'rail' else 'foot' if c in FOOT else 'road'
        w = 4.5 if kind == 'rail' else rwidth(r) + _sidewalk_w.get(g0.wkb, 0.0)
        bc = [q[:2] for q in l.coords]
        def _dir(a, b):
            n_ = math.dist(a, b) or 1; return ((a[0] - b[0]) / n_, (a[1] - b[1]) / n_)
        _rused.clear()
        b0 = l.interpolate(min(3.0, l.length / 2)); b1 = l.interpolate(max(0.0, l.length - 3))
        A0 = _approach(bc[0], _dir(bc[0], (b0.x, b0.y)), kind); A1 = _approach(bc[-1], _dir(bc[-1], (b1.x, b1.y)), kind)
        pre = []
        for j, fs, t in A0: pre += _oriented(j, fs, t)[1:]
        post = []
        for j, fs, t in A1: post += _oriented(j, fs, t)[1:]
        ext = LineString(pre[::-1] + bc + post)
        ds0 = LineString(pre[::-1] + bc[:1]).length if pre else 0.0
        ds1 = ds0 + l.length
        lz = ext.segmentize(4.0); xy = np.array(lz.coords)[:, :2]
        d = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
        gz = ground(xy[:, 0], xy[:, 1])
        span = (d >= ds0 - 0.01) & (d <= ds1 + 0.01)
        # cesty a tratě pod mostem: podjezdná výška nad terénem té cesty (ne nad terénem pod mostovkou, kde už bývá svah břehu);
        # pod mostem přes řeku vede po břehu jen pěšina nebo cyklostezka, té stačí podchodná výška
        rx = np.full(len(d), -1e9)
        ends = l.boundary.buffer(1.5); _fp = l.buffer(w / 2 + 1.0); _pts = shapely.points(xy)
        for j in _under.query(l):
            cg = _under.geometries[j]
            if not cg.intersects(l) or cg.intersects(ends): continue
            if is_node(cg.intersection(l)): continue           # společný uzel = úrovňové křížení na mostě (most v datech sahá až na břeh)
            part = [c_[:2] for q_ in lines(cg.intersection(_fp)) for c_ in q_.segmentize(2.0).coords]
            if not part: continue
            part = np.array(part)
            clr = 3.0 if roads[int(j)][2] in FOOT and roads[int(j)][2] != 'track' else 6.0 if kind == 'rail' else 5.2
            near = span & shapely.dwithin(_pts, cg, w / 2 + 3)
            rx[near] = np.maximum(rx[near], float(np.min(ground(part[:, 0], part[:, 1]))) + clr)
        # nad vodou kus nad hladinou; hladina = nejnižší místo souvislého úseku nad vodou (obrys vody přesahuje na břeh)
        _inw = span & shapely.contains(_water, _pts); _wi = np.where(_inw)[0]
        for _run in (np.split(_wi, np.where(np.diff(_wi) > 1)[0] + 1) if len(_wi) else []):
            rx[_run] = np.maximum(rx[_run], float(gz[_run].min()) + (1.0 if kind == 'foot' else 1.3))
        jd = [_junction(bc[0], pre, {j for j, _fs, _t in A0}, kind), _junction(bc[-1], post, {j for j, _fs, _t in A1}, kind)]
        si = np.where(span)[0]
        _t = xy[np.minimum(np.arange(len(xy)) + 1, len(xy) - 1)] - xy[np.maximum(np.arange(len(xy)) - 1, 0)]
        _PP.append(dict(l=l, r=r, c=c, kind=kind, w=w, A0=A0, A1=A1, lz=lz, xy=xy, d=d, gz=gz, span=span, G=GRADE[kind], ds0=ds0, ds1=ds1,
                        rx=rx, jd=jd, ke=(int(si[0]), int(si[-1])), pe=(Point(bc[0]), Point(bc[-1])), tg=_t / np.maximum(np.hypot(*_t.T), 1e-6)[:, None],
                        cons=[], jn=[False, False], comp=[]))
# ---- 2) vazby mezi kusy ----
# a) konec kusu leží na jiné mostovce stejného druhu (rozdělená estakáda, sjezd z mostu; u široké mostovky se sjezd napojuje na její
#    okraj, ne na osu): nezačíná na terénu, ale ve výšce té mostovky. Na mostě samém (uzel estakády) vždy a obě mostovky se v uzlu
#    srovnají na vyšší z nich; na nájezdu jiné mostovky jen tam, kde je nájezd nad terénem.
# b) souběžné kusy (do 20 m od sebe, aspoň 70 % délky jednoho z nich; trať jen s tratí): pásy jednoho mostu pro každý směr a chodníky
#    vedené v datech zvlášť mají společnou úroveň opěr a stejnou výšku ve stejném místě (jinak by desky téhož mostu měly schodek)
_ptree = shapely.STRtree([_p['lz'] for _p in _PP]) if _PP else None
for i, _p in enumerate(_PP):
    for e in (0, 1):
        pe = _p['pe'][e]
        for j in _ptree.query(pe.buffer(12.0)):
            j = int(j); _q = _PP[j]
            if j == i or _q['kind'] != _p['kind']: continue
            tol = max(2.0, _q['w'] / 2 + 1.0)
            if _q['lz'].distance(pe) > tol: continue
            st = _q['l'].distance(pe) <= tol; s_ = float(_q['lz'].project(pe))
            if st and min(abs(s_ - _q['ds0']), abs(s_ - _q['ds1'])) <= 2.5:   # uzel na konci obou kusů: přesně konec (jinak by se kusy ve sklonu zvedaly navzájem)
                s_ = float(_q['ds0'] if abs(s_ - _q['ds0']) < abs(s_ - _q['ds1']) else _q['ds1'])
            _p['cons'].append(('end', e, _p['ke'][e], j, s_, st))
            if st:
                _p['jn'][e] = True
                if min(abs(s_ - _q['ds0']), abs(s_ - _q['ds1'])) > 2.5:      # uprostřed mostovky: i ona se zvedne k vyššímu sjezdu
                    _q['cons'].append(('pt', 0, int(np.argmin(np.abs(_q['d'] - s_))), i, float(_p['d'][_p['ke'][e]]), True))
def _along(P, Q):
    """body rozpětí kusu P, které mají do 20 m souběžný kus Q: (indexy bodů P, staničení na Q, počet bodů rozpětí P)"""
    K = np.where(P['span'])[0]
    s_ = shapely.line_locate_point(Q['l'], shapely.points(P['xy'][K]))
    q_ = shapely.get_coordinates(shapely.line_interpolate_point(Q['l'], s_))
    k_ = np.clip(np.searchsorted(Q['d'], Q['ds0'] + s_), 0, len(Q['d']) - 1)
    ok = (s_ > 0.5) & (s_ < Q['l'].length - 0.5) & (np.hypot(*(q_ - P['xy'][K]).T) <= 20.0) & (np.abs(np.sum(P['tg'][K] * Q['tg'][k_], axis=1)) > 0.9)
    return K[ok], Q['ds0'] + s_[ok], len(K)
_ltree = shapely.STRtree([_p['l'] for _p in _PP]) if _PP else None
for i, _p in enumerate(_PP):
    for j in _ltree.query(_p['l'].buffer(20.0)):
        j = int(j); _q = _PP[j]
        if j <= i or (_p['kind'] == 'rail') != (_q['kind'] == 'rail'): continue
        Ki, Si, ni = _along(_p, _q); Kj, Sj, nj = _along(_q, _p)
        if max(len(Ki) / max(ni, 1), len(Kj) / max(nj, 1)) < 0.7: continue
        if len(Ki): _p['cons'].append(('lat', 0, Ki, j, Si, True))
        if len(Kj): _q['cons'].append(('lat', 0, Kj, i, Sj, True))
        for e in (0, 1):
            for f in (0, 1):
                if _p['pe'][e].distance(_q['pe'][f]) <= 25.0: _p['comp'].append((e, j, f)); _q['comp'].append((f, i, e))
for _p in _PP: _p['ge'], _p['E'] = _abut(_p)
for _it in range(6):                           # společná úroveň opěr souběžných pásů = nejvyšší z nich
    _ch = False
    for _p in _PP:
        em = [max([_p['E'][e]] + [_PP[j]['E'][f] for e_, j, f in _p['comp'] if e_ == e]) for e in (0, 1)]
        if max(em[0] - _p['E'][0], em[1] - _p['E'][1]) > 0.01: _p['ge'], _p['E'] = _abut(_p, em); _ch = True
    if not _ch: break
# výšky: nejdřív jen s uzly (opakovaně, uzel se srovná na nejvyšší z mostovek), pak se souběžné pásy zvednou na výšku souseda
# z prvního kola (pevná, ne průběžná: šikmo ukončené pásy by se jinak navzájem zvedaly pořád dál)
_Z = [None] * len(_PP); _Zb = None
for _it in range(24):
    _dz = 0.0
    for i, _p in enumerate(_PP):
        zx = np.full(len(_p['d']), -1e9); En = [-1e9, -1e9]; jn = list(_p['jn'])
        for typ, e, _K, j, _S, st in _p['cons']:
            _q = _PP[j]
            if typ == 'lat':
                if _Zb is not None: zx[_K] = np.maximum(zx[_K], np.interp(_S, _q['d'], _Zb[j]))
                continue
            if _Z[j] is None: continue
            zj = np.interp(_S, _q['d'], _Z[j])
            if typ == 'end':
                if not st and zj - float(np.interp(_S, _q['d'], _q['gz'])) <= 0.25: continue
                jn[e] = True; En[e] = max(En[e], float(zj) - 0.15)
            zx[_K] = np.maximum(zx[_K], zj)
        _p['res'] = _niveleta(_p, zx, En, jn); _p['jnf'] = jn
        _dz = max(_dz, float(np.max(np.abs(_p['res'][0] - _Z[i]))) if _Z[i] is not None else 1e9)
        _Z[i] = _p['res'][0]
    if _dz < 0.02 or _it == 11:
        if _Zb is not None: break
        _Zb = [z_.copy() for z_ in _Z]
print('mostovek', len(_PP), 'uzlů mostovek', sum(sum(_p['jnf']) for _p in _PP), 'souběžných vazeb', sum(1 for _p in _PP for q in _p['cons'] if q[0] == 'lat') // 2, 'kol výpočtu', _it + 1)
# ---- 3) oříznutí a zápis ----
_dapp = {}                                  # mostovka -> cesty jejích nájezdů (v zářezech pod mosty se neberou jako cesta pod mostem)
for _p in _PP:
    l, r, c, kind, w, A0, A1, xy, d, gz, span, ds0, ds1, jd, jn = (_p[k_] for k_ in ('l', 'r', 'c', 'kind', 'w', 'A0', 'A1', 'xy', 'd', 'gz', 'span', 'ds0', 'ds1', 'jd', 'jnf'))
    z, ge, req, E = _p['res']
    si = np.where(span)[0]
    hi = np.where(z - gz > 0.25)[0]                 # oříznout nájezdy tam, kde mostovka leží na terénu
    # i konec mostu z dat, který už leží na terénu (most v datech sahá za břeh na louku): ta část je zase obyčejná cesta
    # v terénu, ať se na ni dá odbočit a nevede přes ni zábradlí
    i0, i1 = (max(int(hi[0]) - 1, 0), min(int(hi[-1]) + 1, len(d) - 1)) if len(hi) else (si[0], si[-1])
    for a_, b_ in ((si[0], i0), (i1, si[-1])):
        if b_ > a_ and d[b_] - d[a_] > 0.3: _back.append((LineString(xy[a_:b_ + 1]), r))
    _cut(A0, ds0 - d[i0]); _cut(A1, d[i1] - ds1)
    lz = LineString(xy[i0:i1 + 1]); d = d[i0:i1 + 1] - d[i0]
    _dapp[id(lz)] = {j for j, _fs, _t in A0 + A1}
    DECKS.append((lz, d, z[i0:i1 + 1], gz[i0:i1 + 1], w, kind, c, sname(r), int(l.intersects(_water))))
DECKS_SKRYTE = []
for qb in UP.get('bridges', []):
    bl = LineString([to_local(lo, la) for la, lo in qb['line']]).segmentize(2.0)
    if bl.intersects(DRAWBOX):
        bxy = np.array(bl.coords)[:, :2]
        bd = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(bxy, axis=0).T))])
        bgz = ground(bxy[:, 0], bxy[:, 1])
        t_ = bd / max(bd[-1], 0.1)
        bz = bgz + 0.35 + qb.get('h', 1.2) * np.sin(np.pi * t_)
        DECKS.append((bl, bd, bz, bgz, qb.get('w', 2.5), qb.get('k', 'foot'), qb.get('c', 'footway'), None, 1))
# mosty z dat, které nahrazuje vlastní model (assets/upresneni.json "skryt_mosty": [[lat, lon], …], mostovka do 12 m od bodu)
if UP.get('skryt_mosty'):
    _sk = [Point(*to_local(lo, la)) for la, lo in UP['skryt_mosty']]
    _n0 = len(DECKS); DECKS_SKRYTE = [q for q in DECKS if any(q[0].distance(p_) < 12 for p_ in _sk)]   # hook: povrch pod vlastním modelem mostu
    DECKS = [q for q in DECKS if not any(q[0].distance(p_) < 12 for p_ in _sk)]
    if _n0 > len(DECKS): print('skrytých mostů z dat (vlastní model)', _n0 - len(DECKS))
print('mostů', len(DECKS), 'z toho lávek', sum(k[5] == 'foot' for k in DECKS), 'nájezdů', len(_rcut))
# zářez pod mostem v násypu: laser má nad křížením mostovku, ne cestu pod ní. Terén pod mostovkou podél cesty pod mostem (silnice, trať, pěšina,
# ne voda) klesne na přímku mezi výškami cesty 12 m před mostem a za mostem (jen dolů). Mostovka pak nesedí na násypu jen 1–2 m nad terénem
# (v render.html by to byl zemní násyp bez průjezdu) a cesta pod mostem nestoupá přes hrb. Výška terénu pod mostovkou (gz) se přepočte.
_nc = 0; _DK = []
for _D in DECKS:
    _lz, _dd, _zz, _gz, _w, _kd, _c, _nm, _wt = _D
    _fp = _lz.buffer(_w / 2 + 1.0)
    for _j in _under.query(_fp):
        _cg = _under.geometries[_j]
        if _cg.distance(_lz) > 0.5: continue
        if int(_j) in _dapp.get(id(_lz), ()): continue      # vlastní nájezd mostu není cesta pod mostem (zářez by podkopal opěru)
        if is_node(_cg.intersection(_lz)): continue
        _wi = lines(_cg.intersection(_fp))
        if not _wi: continue
        _wi = max(_wi, key=lambda q_: q_.length)
        if _wi.intersection(_lz.buffer(1.5)).length > 0.6 * _wi.length: continue   # cesta vedená po mostě nebo podél jeho osy (souběžný nájezd), ne pod ním
        # osa cesty pod mostem v pořadí od jednoho konce průniku k druhému, prodloužená o 12 m na obě strany
        _s0, _s1 = sorted((_cg.project(Point(_wi.coords[0])), _cg.project(Point(_wi.coords[-1]))))
        if _s1 - _s0 < 3.0: continue
        _a0, _a1 = max(0.0, _s0 - 12.0), min(_cg.length, _s1 + 12.0)
        _pa, _pb = _cg.interpolate(_a0), _cg.interpolate(_a1)
        _z0, _z1 = float(ground(_pa.x, _pa.y)), float(ground(_pb.x, _pb.y))
        _sub = shapely.ops.substring(_cg, _a0, _a1)
        _hw = max(roads[int(_j)][3] if len(roads[int(_j)]) > 3 else 3.0, 3.0) / 2 + 1.5
        if _gpt is None: _gpt = shapely.points(gx.ravel(), gy.ravel()).reshape(gx.shape)
        _bb = _sub.buffer(_hw + 5.0).bounds
        _m = (gx >= _bb[0]) & (gx <= _bb[2]) & (gy >= _bb[1]) & (gy <= _bb[3])
        if not _m.any(): continue
        _pp = _gpt[_m]
        _t = np.clip(shapely.line_locate_point(_sub, _pp) / max(_sub.length, 0.1), 0, 1)
        _d = shapely.distance(_pp, _sub)
        _zt = _z0 + (_z1 - _z0) * _t
        _wgt = np.clip((_hw + 5.0 - _d) / 5.0, 0, 1)
        _cur = HX[_m]
        _hit = _cur > _zt + 0.7
        if not (_hit & (_wgt > 0)).any(): continue
        HX[_m] = np.where(_hit, _cur * (1 - _wgt) + _zt * _wgt, _cur); _nc += 1
    _DK.append(_D)
if _nc:
    DECKS = [(q[0], q[1], q[2], np.asarray(ground(*np.array(q[0].coords)[:, :2].T)) if len(q[0].coords) == len(q[3]) else q[3], *q[4:]) for q in DECKS]
    print('zářezů pod mosty', _nc)
def _rest(l_, cuts):                       # cesta bez úseků pod mostovkami
    out, a = [], 0.0
    for c0, c1 in sorted(cuts):
        if c0 - a > 0.3: out.append(shapely.ops.substring(l_, a, c0))
        a = max(a, c1)
    if l_.length - a > 0.3: out.append(shapely.ops.substring(l_, a, l_.length))
    return out
roads = [(a_, q, c_, w_, n_) for j, (a_, l_, c_, w_, n_) in enumerate(roads) for q in (_rest(l_, _rcut[j]) if j in _rcut else [l_])]
for _l, _r in _back:
    if _r.subtype == 'rail': roads.append((0, _l, 'rail', 3, sname(_r)))
    elif _r['class'] in RW: roads.append((rwidth(_r), _l, _r['class'], rwidth(_r), sname(_r)))
if _back: print('konců mostů na terénu vrácených mezi cesty', len(_back))
roads.sort(key=lambda t: t[0])
# chodníky podél ulic tam, kde v datech není souběžný chodník a nestojí budova
SIDEWALK = {'trunk', 'primary', 'secondary', 'tertiary', 'residential', 'unclassified'}
foot_tree = shapely.STRtree([l for _, g, c, w, _n in roads if c in ('footway', 'pedestrian', 'path', 'cycleway', 'steps') for l in lines(g)])
bld_early = shapely.STRtree([p for g in load('building').geom for p in polys(g)])
for _, g, c, w, _n in roads:
    if c not in SIDEWALK: continue
    for l in lines(g.intersection(DRAWBOX)):
        for side in (-1, 1):
            try: off = l.offset_curve(side * (w / 2 + 1.05))
            except Exception: continue
            for ol in lines(off):
                d = 0.0
                while d < ol.length:
                    piece = shapely.ops.substring(ol, d, min(d + 6, ol.length))
                    mid = piece.interpolate(0.5, normalized=True)
                    fi = foot_tree.query(mid.buffer(3.0)); bi = bld_early.query(mid.buffer(0.9))
                    if len(fi) == 0 and len(bi) == 0 and piece.length > 0.5:
                        line(piece, C['footway'], 1.7, block=True)
                    d += 6
for _, g, c, w, _n in roads:
    if c != 'rail' and w >= 3.5: line(g, C['curb'], w + 0.7, block=True)
# zrušená trať (OSM railway=abandoned) má jen těleso bez kolejí; ostatní kolejnice kreslí 3D render (scene.koleje), čára v textuře zůstává pod ním
_ABAND = shapely.STRtree([r.geom for _, r in seg.iterrows() if r.subtype == 'rail' and any('is_abandoned' in list(f.get('values')) for f in seg_flags(r))] or [Point(1e9, 1e9)])
for _, g, c, w, _n in roads:
    if c == 'rail':
        line(g, C['ballast'], 3.2, block=True)
        if not len(_ABAND.query(g.interpolate(0.5, normalized=True), predicate='dwithin', distance=0.5)): line(g, C['rail'], 1.4)
        continue
    line(g, C[RCLS.get(c, 'road')], w, block=w >= 3)
# ruční povrchy (assets/upresneni.json, "plochy"): přes cesty, stromy pak určí assets/oblasti.json
for pl in UP.get('plochy', []):
    g_ = Polygon([to_local(lo, la) for la, lo in pl['q']])
    fill(g_, C[pl['k']])
# dětská a workoutová hřiště (assets/hriste.json z nastroje/hriste.py, OSM): 3D vybavení pro render.html (scene.play).
# Zakreslené prvky (playground=*, fitness_station=*) na své místo, zbytek automaticky podle velikosti hřiště, pod
# houpačkou, skluzavkou a prolézačkou písek. Poloha je deterministická (stejná i v pásu sousedního čtverce).
HR = json.load(open('assets/hriste.json')) if os.path.exists('assets/hriste.json') else {'hriste': [], 'prvky': []}
HR['hriste'] = HR['hriste'] + [{'id': f'u{_k}', 'k': _h.get('k', 'detske'), 'poly': _h['q'], 'll': _h['q'][0]}   # ruční (chybí v OSM)
                               for _k, _h in enumerate(UP.get('hriste', []))]
play = []
_PRV = [(Point(*to_local(lo, la)), t) for (la, lo), t in ((q['ll'], q['t']) for q in HR['prvky'])]
for h in HR['hriste']:
    det = h['k'] == 'detske'
    _g = Polygon([to_local(lo, la) for la, lo in h['poly']]) if h['poly'] else Point(*to_local(h['ll'][1], h['ll'][0])).buffer(7.0 if det else 5.0)
    if not _g.is_valid: _g = _g.buffer(0)
    if _g.is_empty or not _g.intersects(EXT) or _g.area < 12: continue
    _r = random.Random(h['id'])
    _o = list(_g.minimum_rotated_rectangle.exterior.coords)
    _e = max(((_o[i], _o[i + 1]) for i in range(2)), key=lambda e: math.dist(*e))
    _a = math.atan2(_e[1][1] - _e[0][1], _e[1][0] - _e[0][0])
    _in = _g.buffer(-1.8); _in = _in if not _in.is_empty and _in.area > 4 else _g
    mine = []
    for _p, _t in _PRV:
        if _g.buffer(3).contains(_p): mine.append([_p.x, _p.y, _a, _t])
    n = max(2, min(6, round(_g.area / 70))) if det else max(2, min(4, round(_g.area / 45)))
    seq = ['piskoviste', 'houpacka', 'skluzavka', 'prolezacka', 'houpadlo', 'kolotoc'] if det else ['hrazda', 'bradla', 'zebriny', 'lavice']
    seq = [t for t in seq if t not in {m[3] for m in mine}]
    x0_, y0_, x1_, y1_ = _in.bounds
    for _t in seq[:max(0, n - len(mine))]:
        for _ in range(150):
            _x, _y = _r.uniform(x0_, x1_), _r.uniform(y0_, y1_)
            if _in.contains(Point(_x, _y)) and all(math.hypot(_x - m[0], _y - m[1]) > 4.6 for m in mine): mine.append([_x, _y, _a, _t]); break
    for _x, _y, _aa, _t in mine:
        if _t in ('houpacka', 'skluzavka', 'prolezacka', 'kolotoc'): fill(Point(_x, _y).buffer(2.0 if _t != 'houpacka' else 2.4), C['sand'])
        play.append([_x, _y, _aa, _t])
# středová přerušovaná čára
for _, g, c, w, _n in roads:
    if c in ('trunk', 'primary', 'secondary', 'tertiary') or (c == 'motorway' and w >= 7):     # dálnice: čára mezi pruhy, ne na sjezdu
        for l in lines(g.intersection(AREA)):
            d = 0.0
            while d < l.length - 3:
                cd.line(P([l.interpolate(d).coords[0], l.interpolate(d + 3).coords[0]]), fill=C['marking'], width=1)
                d += 9

drive_lines = [(l, w, c, n) for _, g, c, w, n in roads if c in DRIVE for l in lines(g)]
# kanály (poklopy) a stopčáry u vjezdu na důležitější silnici
RANK = {'service': 0, 'living_street': 1, 'residential': 2, 'unclassified': 2, 'tertiary': 3, 'secondary': 4, 'primary': 5, 'trunk': 6, 'motorway': 7}
nodes_rank = {}
for l, w, c, n in drive_lines:
    for pt in (l.coords[0], l.coords[-1]):
        nodes_rank.setdefault((round(pt[0]), round(pt[1])), []).append(RANK[c])
for l, w, c, n in drive_lines:
    if l.length < 10 or not AREA.buffer(-5).intersects(l): continue
    if w >= 5:
        d = 18.0
        while d < l.length - 5:
            q = l.interpolate(d); a_ = l.interpolate(d - 1); b_ = l.interpolate(d + 1)
            ang = math.atan2(b_.y - a_.y, b_.x - a_.x)
            x, y = q.x + math.cos(ang - math.pi / 2) * w / 4, q.y + math.sin(ang - math.pi / 2) * w / 4
            r_ = 0.38 / TEX_RES
            cx_, cy_ = P([(x, y)])[0]
            cd.ellipse([cx_ - r_, cy_ - r_, cx_ + r_, cy_ + r_], fill=C['manhole'])
            d += 38
    for end in (0, 1):
        pt = l.coords[-1] if end else l.coords[0]
        ranks = nodes_rank.get((round(pt[0]), round(pt[1])), [])
        if len(ranks) < 3 or max(ranks) <= RANK[c] or RANK[c] == 0: continue
        d = l.length - 3.5 if end else 3.5
        q = l.interpolate(d); a_ = l.interpolate(max(0, d - 1)); b_ = l.interpolate(min(l.length, d + 1))
        tx, ty = (b_.x - a_.x), (b_.y - a_.y); tl = math.hypot(tx, ty) or 1; tx, ty = tx / tl, ty / tl
        if not end: tx, ty = -tx, -ty            # směr jízdy ke křižovatce
        rx, ry = ty, -tx                          # pravá strana
        cd.line(P([(q.x, q.y), (q.x + rx * (w / 2 - 0.3), q.y + ry * (w / 2 - 0.3))]), fill=C['marking'], width=max(1, round(0.45 / TEX_RES)))
all_lines = [(l, w, c, n) for _, g, c, w, n in roads if c != 'rail' for l in lines(g)]

# ---------------- koleje: štěrkové lože, pražce, kolejnice a výhybky (scene.koleje, kreslí render.html) ----------------
# Textura terénu (~0,29 m/px) na kolejnice nestačí, trať je proto 3D pás: lože, pražce po 0,6 m a dvě kolejnice.
# Výhybky se odvodí z topologie (data nemají body výhybek): uzel, kde se kolej větví pod ostrým úhlem. Kde jsou dvě
# souběžné koleje blíž než SL_SEP (výhybka, kolejová spojka), mají společné dlouhé pražce: kreslí je delší kolej
# a natáčí je vějířovitě k odbočce, kratší kolej tam vlastní pražce nemá. Pražce jsou vždy kolmo k ose (i v oblouku).
# V přejezdu (silnice nebo chodník přes kolej v úrovni) lože a pražce chybí a kolejnice jsou zapuštěné do vozovky.
GAUGE = 1.435
RAIL_O = (GAUGE + 0.07) / 2           # osa kolejnice od osy koleje (rozchod se měří mezi vnitřními hranami hlav)
PITCH, SL_HW, SL_SEP = 0.6, 1.3, 3.2  # rozteč pražců, půldélka pražce, do jaké vzdálenosti os mají dvě koleje společné pražce
RAIL3D = {'standard_gauge', 'unknown'}   # tramvaj, metro a úzký rozchod zůstávají jen v textuře


def _koleje():
    keep = [r.geom for _, r in seg.iterrows() if r.subtype == 'rail' and r['class'] in RAIL3D
            and not any('is_abandoned' in list(f.get('values')) for f in seg_flags(r))]      # zrušená trať (jen těleso) bez kolejí
    if not keep: return None
    kt = shapely.STRtree(keep)
    WB = box(-HALF - 60, -HALF - 60, HALF + 60, HALF + 60)
    pcs = []
    for _a, g, c, _w, _n in roads:
        if c != 'rail': continue
        for l in lines(g.intersection(WB)):
            if l.length >= 0.5 and len(kt.query(l.interpolate(0.5, normalized=True), predicate='dwithin', distance=0.5)): pcs.append(l)
    if not pcs: return None
    ch = [l for l in lines(shapely.ops.linemerge(shapely.MultiLineString(pcs))) if l.length >= 1.0]
    LEN = [l.length for l in ch]
    tree = shapely.STRtree(ch)

    def pts(l, s): return shapely.get_coordinates(shapely.line_interpolate_point(l, np.clip(s, 0, l.length)))

    def tang(l, s):
        t = pts(l, np.asarray(s) + 0.8) - pts(l, np.asarray(s) - 0.8)
        return t / np.maximum(np.hypot(*t.T), 1e-9)[:, None]
    # přejezdy: úseky koleje pod silnicí nebo chodníkem v úrovni (ne podchod: cesta v tunelu se nepočítá)
    tun = []
    for _, r in load('segment').iterrows():
        if r.subtype != 'road': continue
        for f in seg_flags(r):
            if 'is_tunnel' in list(f.get('values')):
                t = f.get('between'); t0, t1 = (0.0, 1.0) if t is None else (float(t[0]), float(t[1]))
                tun.append(shapely.ops.substring(r.geom, t0, t1, normalized=True))
    tun_t = shapely.STRtree(tun) if tun else None
    rl = [(l, w) for _a, g, c, w, _n in roads if c != 'rail' for l in lines(g)]
    rt = shapely.STRtree([l for l, _w in rl]) if rl else None
    XS = []
    for A in ch:
        iv = []
        for j in (rt.query(A.buffer(6.0)) if rt is not None else []):
            l, w = rl[int(j)]
            if not A.intersects(l) or lines(A.intersection(l)): continue          # cesta musí kolej křížit (ne vést podél ní)
            for q in lines(A.intersection(l.buffer(w / 2 + 0.05, cap_style='flat'))):
                if q.length > 40 or not q.intersects(l): continue
                m = q.interpolate(0.5, normalized=True)
                if tun_t is not None and len(tun_t.query(m, predicate='dwithin', distance=1.5)): continue
                sm = A.project(m); iv.append((sm - q.length / 2, sm + q.length / 2))   # přes střed (kolej se může vracet blízko sebe)
        iv.sort(); mg = []
        for a, b in iv:
            if mg and a <= mg[-1][1] + 0.5: mg[-1][1] = max(mg[-1][1], b)
            else: mg.append([a, b])
        XS.append(mg)

    def in_x(i, s):
        s = np.asarray(s); m = np.zeros(s.shape, bool)
        for a, b in XS[i]: m |= (s >= a - 0.1) & (s <= b + 0.1)
        return m
    # pražce: hranice mezi pražci (sudé indexy) a středy pražců (liché), pak úseky bez potlačených pražců
    strips, COS = [], math.cos(math.radians(25))
    for i, A in enumerate(ch):
        n_sl = int(A.length // PITCH)
        if n_sl < 1: continue
        S = (A.length - n_sl * PITCH) / 2 + np.arange(2 * n_sl + 1) * PITCH / 2
        Pp = pts(A, S); T = tang(A, S); Nn = np.stack([-T[:, 1], T[:, 0]], 1)
        ext = np.full((len(S), 2), SL_HW); rot = np.zeros(len(S)); sup = in_x(i, S)
        for j in tree.query(A.buffer(SL_SEP + 0.5)):
            j = int(j)
            if j == i: continue
            Bj = ch[j]
            sB = shapely.line_locate_point(Bj, shapely.points(Pp))
            D = pts(Bj, sB) - Pp; d = np.hypot(*D.T); TB = tang(Bj, sB); cs = np.sum(T * TB, 1)
            m = (sB > 0.3) & (sB < Bj.length - 0.3) & (d < SL_SEP) & (np.abs(cs) > COS)
            if not m.any(): continue
            if (LEN[j], j) > (LEN[i], i): sup |= m; continue          # pražce tu kreslí delší kolej
            TB = TB * np.sign(cs)[:, None]
            ang = np.arctan2(T[:, 0] * TB[:, 1] - T[:, 1] * TB[:, 0], np.sum(T * TB, 1))
            lat = np.sum(D * Nn, 1); e = np.abs(lat) + SL_HW
            for k, sel in ((0, m & (lat > 0)), (1, m & (lat <= 0))):
                sel = sel & (e > ext[:, k])
                ext[sel, k] = e[sel]; rot[sel] = ang[sel] / 2 * np.clip(d[sel] / SL_SEP, 0, 1)   # vějíř: natočení roste s rozjezdem
        cr, sr = np.cos(rot), np.sin(rot)
        M = np.stack([Nn[:, 0] * cr - Nn[:, 1] * sr, Nn[:, 0] * sr + Nn[:, 1] * cr], 1)
        L = Pp + M * ext[:, :1]; R = Pp - M * ext[:, 1:]
        ok = ~sup[1::2]                                               # pražec k (střed 2k+1) se kreslí?
        k = 0
        while k < n_sl:
            if not ok[k]: k += 1; continue
            k1 = k
            while k1 + 1 < n_sl and ok[k1 + 1]: k1 += 1
            bi = np.arange(k, k1 + 2) * 2                             # hranice pražců k..k1+1
            Lb, Rb = L[bi], R[bi]
            kp, a = [0], 0
            while a < len(bi) - 1:                                    # vynechat hranice, které leží na spojnici sousedních
                b_ = min(a + 4, len(bi) - 1)
                while b_ > a + 1:
                    t = ((np.arange(a + 1, b_) - a) / (b_ - a))[:, None]
                    err = max(np.abs(Lb[a] + (Lb[b_] - Lb[a]) * t - Lb[a + 1:b_]).max(), np.abs(Rb[a] + (Rb[b_] - Rb[a]) * t - Rb[a + 1:b_]).max())
                    if err < 0.03: break
                    b_ -= 1
                kp.append(b_); a = b_
            strips.append([v for q in kp for v in (round(float(Lb[q][0]), 2), round(float(Lb[q][1]), 2),
                                                   round(float(Rb[q][0]), 2), round(float(Rb[q][1]), 2), q)])
            k = k1 + 1
    # kolejnice: osy +- RAIL_O, třetí číslo bodu 1 = na pražcích, 0 = zapuštěná v přejezdu; typ 0 kolejnice, 1 přídržnice, 2 srdcovka
    rails = []

    def offs(i, s0, s1, o, typ, step=2.0):
        A = ch[i]; s0, s1 = max(0.0, s0), min(A.length, s1)
        if s1 - s0 < 0.2: return
        S = np.arange(s0, s1, step)
        S = np.unique(np.concatenate([S, [s1], [v for a, b in XS[i] for v in (a - 0.6, a, b, b + 0.6) if s0 < v < s1]]))
        Q = pts(A, S); T = tang(A, S); Q = Q + np.stack([-T[:, 1], T[:, 0]], 1) * o
        f = (~in_x(i, S)).astype(int)
        rails.append([typ] + [v for q, f_ in zip(Q, f) for v in (round(float(q[0]), 2), round(float(q[1]), 2), int(f_))])
    for i, A in enumerate(ch):
        for o in (RAIL_O, -RAIL_O): offs(i, 0, A.length, o, 0)
    # výhybky: uzel, ze kterého vedou tři větve a dvě z nich svírají ostrý úhel. Overture nedělí kusy v každém uzlu:
    # odbočka často končí uprostřed průběžné koleje (ta pak dává dvě větve). Větev = (kolej, staničení uzlu, směr od uzlu).
    ends = {}
    for i, A in enumerate(ch):
        for s0, sg, q in ((0.0, 1.0, A.coords[0]), (LEN[i], -1.0, A.coords[-1])): ends.setdefault((round(q[0], 1), round(q[1], 1)), []).append((i, s0, sg))
    for key in list(ends):
        if len(ends[key]) != 1: continue
        q = Point(key)
        for j in tree.query(q.buffer(0.2)):
            j = int(j); sj = ch[j].project(q)
            if j != ends[key][0][0] and ch[j].distance(q) < 0.1 and 0.5 < sj < LEN[j] - 0.5:
                ends[key] += [(j, sj, 1.0), (j, sj, -1.0)]; break
    pm, nsw = [], 0
    for key, E in ends.items():
        if len(E) != 3: continue
        node = np.array(key)
        dirs = []
        for i, s0, sg in E:
            q = pts(ch[i], [s0 + sg * min(6.0, LEN[i] / 2)])[0] - node
            dirs.append(q / (np.hypot(*q) or 1))
        best = None
        for a in range(3):
            for b in range(a + 1, 3):
                c_ = 3 - a - b; ca = float(np.dot(dirs[a], dirs[b]))
                if ca > math.cos(math.radians(30)) and float(np.dot(dirs[c_], dirs[a] + dirs[b])) < -1.4 and (best is None or ca > best[0]): best = (ca, a, b, c_)
        if best is None: continue
        _ca, a, b, c_ = best
        thr, dv = (a, b) if np.dot(dirs[a], -dirs[c_]) >= np.dot(dirs[b], -dirs[c_]) else (b, a)
        (it, s0t, sgt), (iv_, s0v, sgv) = E[thr], E[dv]
        if it == iv_: continue
        nsw += 1
        # srdcovka: vnitřní kolejnice obou větví se kříží tam, kde jsou osy od sebe 2 * RAIL_O
        dd = np.arange(0.5, min(LEN[iv_] - s0v if sgv > 0 else s0v, 80.0), 0.25)
        if len(dd) < 2: continue
        Q = pts(ch[iv_], s0v + sgv * dd); dist = shapely.distance(ch[it], shapely.points(Q))
        hit = np.where(dist >= 2 * RAIL_O)[0]
        if not len(hit) or dist[-1] < 2 * RAIL_O: continue
        k = int(hit[0]); sf = s0v + sgv * dd[k]                          # staničení srdcovky na odbočce
        sat = ch[it].project(Point(*Q[k])); Qt = pts(ch[it], [sat])[0]
        tv_ = tang(ch[iv_], [sf])[0]; tt_ = tang(ch[it], [sat])[0]
        sdv = 1.0 if np.dot(Qt - Q[k], [-tv_[1], tv_[0]]) > 0 else -1.0   # na které straně odbočky leží přímá větev
        sdt = 1.0 if np.dot(Q[k] - Qt, [-tt_[1], tt_[0]]) > 0 else -1.0   # na které straně přímé větve leží odbočka
        offs(iv_, min(sf - 0.6 * sgv, sf + 2.2 * sgv), max(sf - 0.6 * sgv, sf + 2.2 * sgv), sdv * RAIL_O, 2, 0.4)   # srdcovka
        offs(it, sat - 2.2, sat + 2.2, -sdt * (RAIL_O - 0.26), 1, 0.5)    # přídržnice proti srdcovce na vnějších kolejnicích
        offs(iv_, sf - 2.2, sf + 2.2, -sdv * (RAIL_O - 0.26), 1, 0.5)
        s1 = s0t + sgt * 1.5; q0 = pts(ch[it], [s1])[0]; t0 = tang(ch[it], [s1])[0]
        n0 = np.array([-t0[1], t0[0]]) * -sdt * (SL_HW + 0.45)            # přestavník u hrotu jazyků, z vnější strany
        pm.append([round(float(q0[0] + n0[0]), 2), round(float(q0[1] + n0[1]), 2), round(math.atan2(t0[1], t0[0]), 3)])
    ax = [[round(v, 2) for q in A.coords for v in q[:2]] for A in ch]
    print('koleje', len(ch), 'kusů', round(sum(LEN) / 1000, 1), 'km, výhybek', nsw, 'pásů pražců', len(strips), 'přejezdů', sum(len(x) for x in XS))
    return {'o': ax, 'x': [[round(v, 2) for q in x for v in q] for x in XS], 's': strips, 'r': rails, 'pm': pm}
KOLEJE = _koleje()

def deck_runs(pts):
    """mostovka jen nad terénem mapy: nájezd, který pokračuje cestou za okraj mapy, by visel do prázdna (hráz u okraje) -> souvislé kusy uvnitř EXT"""
    out, cur = [], []
    for q in pts:
        if EXT_P.contains(Point(q[0], q[1])): cur.append(q)
        else:
            if len(cur) > 1: out.append(cur)
            cur = []
    if len(cur) > 1: out.append(cur)
    return out


def deck_line(D):
    lz, d, z = D[0], D[1], D[2]
    return [[round(x, 1), round(y, 1), round(float(h), 2)] for (x, y), h in zip(np.array(lz.coords)[:, :2], z)]
drive_tree = shapely.STRtree([l for l, *_ in drive_lines])
all_tree = shapely.STRtree([l for l, *_ in all_lines])


def nearest_dir(pt, tree, items, maxd):
    i = tree.nearest(pt)
    if i is None: return None
    l = items[i][0]
    if l.distance(pt) > maxd: return None
    d = l.project(pt)
    a = l.interpolate(max(0, d - 1)); b = l.interpolate(min(l.length, d + 1))
    return math.atan2(b.y - a.y, b.x - a.x), items[i]


# přechody pro chodce (zebry)
for _, r in inf.iterrows():
    if r['class'] != 'crossing' or not AREA.contains(r.geom): continue
    nd_ = nearest_dir(r.geom, drive_tree, drive_lines, 6)
    if not nd_: continue
    ang, (l, w, *_rest) = nd_
    q = l.interpolate(l.project(r.geom))
    ux, uy = math.cos(ang), math.sin(ang); vx, vy = -uy, ux
    k = -w / 2 + 0.5
    while k < w / 2 - 0.3:
        cx, cy = q.x + vx * k, q.y + vy * k
        corners = [(cx + ux * s * 1.5 + vx * t * 0.25, cy + uy * s * 1.5 + vy * t * 0.25) for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        cd.polygon(P(corners), fill=C['marking'])
        k += 1.0

# parkovací stání + zaparkovaná auta podle OSM (parking=surface|street_side|lane|…, orientation=parallel|perpendicular|diagonal):
#  - patrové, podzemní a střešní parkoviště, přístřešky a garáže: na zemi žádná auta (jen plocha)
#  - stání u ulice (street_side, lane, on_kerb, half_on_kerb, nebo úzký dlouhý pruh): jedna řada, zajíždí se ze silnice;
#    lane/kerb a úzké pruhy podélně, jinak podle orientation (kolmo / šikmo 60°)
#  - plošné parkoviště: kolmo k zmapovaným uličkám, z obou stran; bez uliček vzor řada 5 m – ulička 6 m – řada 5 m
#    (řady zády k sobě), stání jen tam, kde se celé vejde do plochy a nezasahuje do vozovky
cars = []
drive_cover = shapely.prepared.prep(shapely.unary_union([l.buffer(w / 2 + 0.2) for l, w, c, n in drive_lines]) or Point(1e9, 1e9).buffer(1))
STREET_PK = {'street_side', 'lane', 'on_kerb', 'half_on_kerb', 'on_street', 'street'}
def stall(cx, cy, ang, ln=4.8, wd=2.4):
    """obdélník stání: ang = směr podélné osy auta"""
    ca, sa = math.cos(ang), math.sin(ang)
    return Polygon([(cx + ca * dl * ln / 2 - sa * dw * wd / 2, cy + sa * dl * ln / 2 + ca * dw * wd / 2) for dl, dw in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
_aisles = [l for _, g, c, _w, _n in roads if c == 'service' for l in lines(g)]
_aisle_tree = shapely.STRtree(_aisles) if _aisles else None
_stani = {}                                     # středy stání v mřížce 3 m: sousední uličky a plochy se nepřekryjí
def _stani_volne(x, y):
    kx, ky = int(x // 3), int(y // 3)
    for a_ in range(kx - 1, kx + 2):
        for b_ in range(ky - 1, ky + 2):
            for q_ in _stani.get((a_, b_), []):
                if (q_[0] - x) ** 2 + (q_[1] - y) ** 2 < 4.0: return False
    _stani.setdefault((kx, ky), []).append((x, y))
    return True
for pid, p, tg in parkings:
    pk, ori = tg.get('parking', ''), tg.get('orientation', '')
    if pk in ('multi-storey', 'underground', 'rooftop', 'carports', 'garage_boxes'): continue
    if p.area < 25: continue
    crng = random.Random(f'{pid}{wkey(p.centroid.x, p.centroid.y)}')
    o = p.minimum_rotated_rectangle
    oc = [np.array(c) for c in list(o.exterior.coords)[:4]]
    e1, e2 = oc[1] - oc[0], oc[3] - oc[0]
    if np.linalg.norm(e1) < np.linalg.norm(e2): e1, e2 = e2, e1; oc = [oc[0], oc[3], oc[2], oc[1]]
    L, W = float(np.linalg.norm(e1)), float(np.linalg.norm(e2))
    if L < 3 or W < 1: continue
    u, v = e1 / L, e2 / W
    au, av = math.atan2(u[1], u[0]), math.atan2(v[1], v[0])
    if pk in STREET_PK or (not pk and W < 7 and L > 3 * W):
        # ---- stání podél ulice: jedna řada ----
        loose = shapely.prepared.prep(p.buffer(0.6))
        if ori == 'parallel' or (not ori and (pk in ('lane', 'on_kerb', 'half_on_kerb') or W < 4.0)): mode = 'par'
        elif ori == 'diagonal': mode = 'diag'
        else: mode = 'perp' if W >= 4.0 else 'par'
        step = {'par': 6.0, 'perp': 2.5, 'diag': 3.0}[mode]
        ang = {'par': au, 'perp': av, 'diag': au + math.radians(60)}[mode]
        s_ = step / 2
        while s_ < L - step / 2 + 1e-6:
            c = oc[0] + u * s_ + v * W / 2
            if loose.contains(stall(c[0], c[1], ang, 4.4 if mode == 'par' else 4.2, 1.8)):
                if mode != 'par':
                    a = oc[0] + u * (s_ - step / 2); b = a + v * W
                    if loose.contains(Point(*a)) and loose.contains(Point(*b)): cd.line(P([tuple(a), tuple(b)]), fill=C['marking'], width=1)
                if crng.random() < 0.62:                    # stání v pruhu smí ležet na okraji vozovky
                    cars.append([float(c[0]), float(c[1]), ang, crng.randrange(8)])
            s_ += step
        continue
    if p.area < 120: continue
    _ais = []
    if _aisle_tree is not None:
        _p05 = p.buffer(0.5)
        for i_ in sorted(int(v) for v in _aisle_tree.query(p)):
            _ais += [l_ for l_ in lines(_aisles[i_].intersection(_p05)) if l_.length >= 6]
    if _ais:
        _pp = shapely.prepared.prep(p.buffer(-0.3))
        _ais_tree = shapely.STRtree(_ais)
        for a_l in _ais:
            _s = 1.25
            while _s < a_l.length - 1.25:
                _q0, _q1, _q = a_l.interpolate(_s - 1.0), a_l.interpolate(_s + 1.0), a_l.interpolate(_s)
                _tl = math.hypot(_q1.x - _q0.x, _q1.y - _q0.y) or 1.0
                _tx, _ty = (_q1.x - _q0.x) / _tl, (_q1.y - _q0.y) / _tl
                for _sg in (1, -1):
                    _nx, _ny = -_ty * _sg, _tx * _sg
                    _pa, _pb, _pc = [Point(_q.x + _nx * d_, _q.y + _ny * d_) for d_ in (3.0, 8.0, 5.5)]
                    if not (_pp.contains(_pa) and _pp.contains(_pb) and _pp.contains(_pc)): continue
                    if len(_ais_tree.query(_pc, predicate='dwithin', distance=4.6)) or not _stani_volne(_pc.x, _pc.y): continue   # blíž k jiné uličce než ke své
                    cd.line(P([(_pa.x - _tx * 1.25, _pa.y - _ty * 1.25), (_pb.x - _tx * 1.25, _pb.y - _ty * 1.25)]), fill=C['marking'], width=1)
                    cd.line(P([(_pa.x + _tx * 1.25, _pa.y + _ty * 1.25), (_pb.x + _tx * 1.25, _pb.y + _ty * 1.25)]), fill=C['marking'], width=1)
                    if crng.random() < 0.58: cars.append([_pc.x, _pc.y, math.atan2(_ny, _nx), crng.randrange(8)])
                _s += 2.5
        continue
    # bez uliček: pásy řad napříč kratší osou (řada 5 m – ulička 6 m – řada 5 m), stání celé v ploše a mimo vozovku
    inner = shapely.prepared.prep(p.buffer(0.3))
    if W < 6.5: bands = [(W / 2 - 2.5, W / 2 + 2.5)]
    else:
        bands, pos = [], 0.0
        while True:
            bands.append((pos, pos + 5)); pos += 5 + 6
            if pos + 5 <= W + 0.3: bands.append((pos, pos + 5)); pos += 5
            if pos + 11 > W + 0.3: break
        sh = max(0.0, (W - max(b for a, b in bands)) / 2)
        bands = [(a + sh, b + sh) for a, b in bands]
    for r0, r1 in bands:
        s = 1.25
        while s < L - 1.2:
            c = oc[0] + u * s + v * (r0 + r1) / 2
            st_ = stall(c[0], c[1], av)
            if inner.contains(st_) and not drive_cover.intersects(st_) and _stani_volne(c[0], c[1]):
                ca, sa = math.cos(av), math.sin(av)
                for dw in (-1.25, 1.25):                          # čáry po stranách stání
                    cd.line(P([(c[0] - ca * 2.4 - sa * dw, c[1] - sa * 2.4 + ca * dw), (c[0] + ca * 2.4 - sa * dw, c[1] + sa * 2.4 + ca * dw)]), fill=C['marking'], width=1)
                if crng.random() < 0.58: cars.append([float(c[0]), float(c[1]), av, crng.randrange(8)])
            s += 2.5
# auta podél ulic (ne na kolejích u přejezdu)
_rail_park = shapely.STRtree([l for _, g, c, _w, _n in roads if c == 'rail' for l in lines(g)] or [Point(1e9, 1e9)])
for l, w, c, n in drive_lines:
    if c not in ('residential', 'unclassified', 'living_street', 'tertiary'): continue
    d = 4.0
    crng = wrng(*l.coords[0], 'car')
    while d < l.length - 4:
        if crng.random() < 0.07:
            a = l.interpolate(d - 1); b = l.interpolate(d + 1)
            ang = math.atan2(b.y - a.y, b.x - a.x)
            off = w / 2 - 1.1
            q = l.interpolate(d)
            x, y = q.x + math.cos(ang - math.pi / 2) * off, q.y + math.sin(ang - math.pi / 2) * off
            if AREA.contains(Point(x, y)):
                ci_ = crng.randrange(8)                      # náhoda se volá stejně, ostatní auta zůstanou na místě
                _pp = Point(x, y)
                # zaparkované auto jen u úzké ulice a mimo křižovatku: na víceproudé silnici by stálo uprostřed jízdních pruhů,
                # v křižovatce přímo na vozovce druhé silnice
                _kriz = any(drive_lines[int(k_)][0] is not l and drive_lines[int(k_)][0].distance(_pp) < drive_lines[int(k_)][1] / 2 + 1.5
                            for k_ in drive_tree.query(_pp.buffer(14)))
                if w <= 9.0 and not _kriz and not len(_rail_park.query(_pp, predicate='dwithin', distance=8.0)): cars.append([x, y, ang, ci_])
        d += 7

# ---------------- budovy ----------------
bld = load('building')
# jen budovy z OpenStreetMap (nebo ručně potvrzené v upresneni.json)
bld = bld[[(s is not None and any(x['dataset'] == 'OpenStreetMap' for x in s)) or i_ in UP['b'] for s, i_ in zip(bld.sources, bld.id)]].reset_index(drop=True)
bld = bld[~bld.id.isin(UP.get('skryt_budovy', []))].reset_index(drop=True)   # duplicitní budovy v datech (např. části kostela přes celý obrys)
for i, r in bld.iterrows():                             # výšky z upřesnění mají přednost před daty
    if 'h' in UP['b'].get(r.id, {}): bld.at[i, 'height'] = UP['b'][r.id]['h']
if len(bld) and UP['roofs']:                            # přístřešky nástupišť (nejsou v OSM jako budovy)
    t0 = bld.iloc[0]; rows = []
    for i, q in enumerate(UP['roofs']):
        g = LineString([to_local(lo, la) for la, lo in q['line']]).buffer(q['w'] / 2, cap_style='flat', join_style='mitre')
        rows.append({**t0.to_dict(), 'id': f'up-roof-{i}', 'class': 'roof', 'subtype': None, 'names': None, 'height': q['h'], 'num_floors': float('nan'), 'roof_shape': None, 'geom': g, 'geometry': None})
    bld = pd.concat([bld, pd.DataFrame(rows)], ignore_index=True)
if len(bld) and UP.get('custom_bld'):                   # ručně doplněné drobné stavby (výdejní box, kiosek, přístřešek)
    t0 = bld.iloc[0]; rows = []
    for q in UP['custom_bld']:
        g = Polygon([to_local(lo, la) for la, lo in q['poly']])
        SAT['b'][q['id']] = {k: q[k] for k in ('h', 'r', 'wc', 'rc') if k in q}
        rows.append({**t0.to_dict(), 'id': q['id'], 'class': q.get('cls', 'service'), 'subtype': None, 'names': {'primary': q.get('name')} if q.get('name') else None, 'height': q['h'], 'num_floors': float('nan'), 'roof_shape': q.get('r', 'flat'), 'geom': g, 'geometry': None})
    bld = pd.concat([bld, pd.DataFrame(rows)], ignore_index=True)
WALLS = [(232, 220, 192), (241, 234, 216), (217, 201, 163), (230, 211, 179), (214, 208, 196), (239, 230, 207),
         (216, 185, 143), (226, 196, 160), (205, 214, 206)]
PANEL = [(232, 226, 208), (213, 217, 222), (236, 236, 230), (222, 224, 222), (226, 199, 154), (169, 195, 201), (238, 232, 218), (204, 210, 214)]   # sídliště hlavně bílá a světle šedá
ROOF_P = [(168, 68, 47), (150, 60, 44), (142, 58, 42), (107, 59, 47), (74, 74, 82), (63, 74, 90), (156, 90, 60), (128, 52, 40)]
ROOF_F = [(141, 141, 141), (122, 122, 122), (156, 154, 146), (110, 112, 116)]
PITCHED_CLS = {'church', 'house', 'detached', 'semidetached_house', 'residential', 'terrace', 'farm', 'chapel', 'bungalow',
               'villa', 'cabin', 'religious', 'civic', 'hut', 'barn', 'farm_auxiliary', 'kindergarten', 'allotment_house'}
FLAT_CLS = {'garage', 'garages', 'apartments', 'industrial', 'warehouse', 'commercial', 'retail', 'school',
            'university', 'hospital', 'office', 'carport', 'parking', 'service', 'transportation', 'sports_hall',
            'sports_centre', 'greenhouse', 'roof'}
ROOF_MAP = {'gabled': 'gabled', 'hipped': 'hipped', 'half_hipped': 'hipped', 'pyramidal': 'pyramidal',
            'saltbox': 'gabled', 'gambrel': 'gabled', 'skillion': 'gabled', 'mansard': 'hipped', 'flat': 'flat',
            'round': 'flat', 'dome': 'pyramidal'}
CLS_CZ = {'house': 'rodinný dům', 'detached': 'rodinný dům', 'residential': 'obytný dům', 'apartments': 'bytový dům',
          'garage': 'garáž', 'garages': 'garáže', 'industrial': 'průmyslová budova', 'warehouse': 'sklad',
          'civic': 'občanská stavba', 'school': 'škola', 'university': 'univerzita', 'retail': 'obchod',
          'commercial': 'komerční budova', 'church': 'kostel', 'chapel': 'kaple', 'kindergarten': 'mateřská škola',
          'shed': 'kůlna', 'barn': 'stodola', 'service': 'technická budova', 'office': 'kanceláře',
          'semidetached_house': 'dvojdům', 'terrace': 'řadový dům', 'bungalow': 'bungalov', 'hotel': 'hotel',
          'dormitory': 'kolej', 'hospital': 'zdravotnictví', 'greenhouse': 'skleník', 'roof': 'přístřešek',
          'cabin': 'chata', 'farm': 'usedlost', 'farm_auxiliary': 'hospodářská budova', 'transportation': 'stavba pro dopravu'}


def hexcol(s, fallback):
    if not isinstance(s, str): return fallback
    s = s.strip()
    if s.startswith('#') and len(s) == 7:
        try: return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError: return fallback
    named = {'white': (240, 238, 232), 'red': (168, 68, 47), 'brown': (110, 70, 50), 'grey': (130, 130, 130),
             'gray': (130, 130, 130), 'black': (60, 60, 64), 'yellow': (232, 208, 140), 'beige': (226, 210, 176),
             'darkred': (128, 46, 36), 'green': (80, 120, 80), 'blue': (80, 100, 140), 'orange': (204, 120, 60)}
    return named.get(s.lower(), fallback)


def max_rect(M):
    """největší obdélník jedniček v binární matici -> (r0, c0, r1, c1) včetně"""
    best = (0, None); h = np.zeros(M.shape[1], int)
    for r in range(M.shape[0]):
        h = np.where(M[r], h + 1, 0)
        st = []
        for c in range(M.shape[1] + 1):
            cur = h[c] if c < M.shape[1] else 0
            start = c
            while st and st[-1][1] >= cur:
                s0, hh = st.pop()
                if hh * (c - s0) > best[0]: best = (hh * (c - s0), (r - hh + 1, s0, r, c - 1))
                start = s0
            st.append((start, cur))
    return best[1]


def roof_parts(p, ang):
    """rozloží půdorys na obdélníky (tvar L/T/U) -> [[cx, cy, úhel, L, W], ...]"""
    cs = 0.6
    c0 = p.centroid
    q = shapely.affinity.rotate(p, -ang, origin=c0, use_radians=True)
    minx, miny, maxx, maxy = q.bounds
    xs = np.arange(minx + cs / 2, maxx, cs); ys = np.arange(miny + cs / 2, maxy, cs)
    if len(xs) < 3 or len(ys) < 3: return []
    XX, YY = np.meshgrid(xs, ys)
    M = shapely.contains_xy(q, XX, YY)
    total = M.sum(); out = []
    for _ in range(4):
        r = max_rect(M)
        if r is None: break
        r0, c0_, r1, c1 = r
        area = (r1 - r0 + 1) * (c1 - c0_ + 1)
        if area < max(0.14 * total, 20 / cs ** 2): break
        w_, h_ = (c1 - c0_ + 1) * cs, (r1 - r0 + 1) * cs
        if min(w_, h_) < 3.0: M[r0:r1 + 1, c0_:c1 + 1] = False; continue
        cx = (xs[c0_] + xs[c1]) / 2; cy = (ys[r0] + ys[r1]) / 2
        pt = shapely.affinity.rotate(Point(cx, cy), ang, origin=c0, use_radians=True)
        a = ang if w_ >= h_ else ang + math.pi / 2
        out.append([round(pt.x, 2), round(pt.y, 2), round(a, 4), round(max(w_, h_), 2), round(min(w_, h_), 2)])
        M[r0:r1 + 1, c0_:c1 + 1] = False
    return out


addr = load('address')
addr = addr[addr.geom.map(lambda g: EXT_P.contains(g))]
addr_pts = list(addr.geom)
addr_tree = shapely.STRtree(addr_pts)
addr_txt = [f"{s} {n}" if isinstance(s, str) else f"{c} {n}" if isinstance(c, str) else str(n) for s, n, c in zip(addr.street, addr.number, addr.postal_city)]

buildings, binfo, chimneys = [], [], []
bmask = Image.new('L', (TWE, TWE), 0); bmd = ImageDraw.Draw(bmask)
# centrum a další městské čtverce: činžáky v sevřených blocích (dům sdílí zeď se sousedem) mají šikmé střechy;
# rozhoduje čtverec, kterému budova patří (těžiště), aby vypadala stejně i v sousedním čtverci


# ---------------- dominanty (assets/dominanty.json, popis podle fotek) ----------------
DOMS = [d for d in json.load(open('assets/dominanty.json', encoding='utf-8')) if d.get('spec')] if os.path.exists('assets/dominanty.json') else []
for d in DOMS:
    d['xy'] = [float(v) for v in to_local(d['lon'], d['lat'])]
    if 'face' in d['spec']: d['spec']['face_xy'] = [float(v) for v in to_local(d['spec']['face'][1], d['spec']['face'][0])]
DOM_BY_ID = {}                       # Overture id budovy -> dominanta


def match_doms():
    """budova dominanty = obsahuje bod, jinak největší do 25 m; u 'names' všechny budovy s tím názvem; 'glass' = všechny v okruhu"""
    idx = {i: r for i, r in zip(range(len(bld)), bld.itertuples())}
    geoms = list(bld.geom)
    tree = shapely.STRtree(geoms)
    for d in DOMS:
        sp = d['spec']; pt = Point(*d['xy'])
        if sp.get('only'): continue
        if 'names' in sp:
            for k, r in idx.items():
                if isinstance(r.names, dict) and (r.names.get('primary') or '').startswith(sp['names']): DOM_BY_ID[r.id] = d
            continue
        if 'glass' in sp:
            for k in tree.query(pt.buffer(sp['glass'])): DOM_BY_ID.setdefault(idx[k].id, {**d, 'spec': {'rc': [176, 204, 214], 'r': 'flat', 'win': 14}})
            continue
        hit = [k for k in tree.query(pt.buffer(25)) if geoms[k].area > 60]
        inside = sorted((k for k in hit if geoms[k].buffer(1.0).contains(pt)), key=lambda k: geoms[k].area)   # vnořené půdorysy (hala pod střechou): nejmenší
        cand = inside or sorted(hit, key=lambda k: -geoms[k].area)
        if cand: DOM_BY_ID[idx[cand[0]].id] = d


def dom_pos(p, at, sp, d, w, side=0.0, t=0.5):
    """poloha věže / komína na půdorysu: světová strana, průčelí k bodu 'face', střed, podél osy, nebo bod dominanty"""
    c = p.centroid
    if at == 'pt': return d['xy'][0], d['xy'][1], 0.0
    o = p.minimum_rotated_rectangle; cs = list(o.exterior.coords)[:3]
    e1 = np.subtract(cs[1], cs[0]); e2 = np.subtract(cs[2], cs[1])
    ax = e1 if np.linalg.norm(e1) >= np.linalg.norm(e2) else e2; L = float(np.linalg.norm(ax)); ax = ax / L
    ang = math.atan2(ax[1], ax[0])
    if at == 'c': return c.x + ax[0] * side, c.y + ax[1] * side, ang
    if at == 'along': return c.x + ax[0] * (t - 0.5) * L, c.y + ax[1] * (t - 0.5) * L, ang
    if at in ('front', 'back'):
        # průčelí = strana opsaného obdélníku natočená k bodu 'face' (náměstí); věže v řadě podél ní, odsazené dovnitř
        fx, fy = sp.get('face_xy', [c.x, c.y - 50])
        if at == 'back': fx, fy = 2 * c.x - fx, 2 * c.y - fy
        rc = list(o.exterior.coords)[:4]
        best = None
        for k in range(4):
            a0, a1 = np.array(rc[k]), np.array(rc[(k + 1) % 4]); m = (a0 + a1) / 2
            nrm = m - np.array([c.x, c.y]); nl = np.linalg.norm(nrm) or 1; nrm /= nl
            dv = np.array([fx - c.x, fy - c.y]); dv /= (np.linalg.norm(dv) or 1)
            sc = float(nrm @ dv)
            if best is None or sc > best[0]: best = (sc, a0, a1, m, nrm)
        _, a0, a1, m, nrm = best
        tg = (a1 - a0) / (np.linalg.norm(a1 - a0) or 1)
        x, y = m - nrm * (w / 2 + 0.6) + tg * side
        return float(x), float(y), math.atan2(tg[1], tg[0])
    dirs = {'n': (0, 1), 's': (0, -1), 'e': (1, 0), 'w': (-1, 0), 'ne': (1, 1), 'nw': (-1, 1), 'se': (1, -1), 'sw': (-1, -1)}
    vx, vy = dirs[at]; vl = math.hypot(vx, vy); vx, vy = vx / vl, vy / vl
    pts = np.array(p.exterior.coords); k = int(np.argmax(pts[:, 0] * vx + pts[:, 1] * vy))
    x, y = pts[k]
    inside = Point(x - vx * (w / 2 + 0.4), y - vy * (w / 2 + 0.4))
    x, y = (inside.x, inside.y) if p.contains(inside) else (x + (c.x - x) * 0.15, y + (c.y - y) * 0.15)
    return x + ax[0] * side, y + ax[1] * side, ang


def unhole(p):
    """budova s dvorem -> kusy bez děr (renderer kreslí jen vnější obrys); řez vede dvorem napříč delší osou"""
    if not p.is_valid: p = p.buffer(0)
    out, todo = [], polys(p)
    while todo:
        q = todo.pop()
        hs = [h for h in q.interiors if Polygon(h).area > 4]          # malé světlíky se zaplní
        if not hs or len(out) > 40: out.append(Polygon(q.exterior)); continue
        c = Polygon(hs[0]).centroid
        cs = list(q.minimum_rotated_rectangle.exterior.coords)[:3]
        e1 = np.subtract(cs[1], cs[0]); e2 = np.subtract(cs[2], cs[1])
        a = e2 if np.linalg.norm(e1) >= np.linalg.norm(e2) else e1
        a = a / (np.linalg.norm(a) or 1) * 1e4
        cut = LineString([(c.x - a[0], c.y - a[1]), (c.x + a[0], c.y + a[1])])
        parts = [g for g in polys(shapely.ops.split(q, cut)) if g.area > 1]
        if len(parts) < 2: out.append(Polygon(q.exterior)); continue
        todo += parts
    return out


def L_obb_ok(p):
    # obří nebo hodně protáhlé bloky (haly, obchodní domy) nejsou činžák
    o = p.minimum_rotated_rectangle; cs = list(o.exterior.coords)[:3]
    a, b = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
    return max(a, b) < 70

match_doms()
print('dominant napárováno na budovy', len(DOM_BY_ID))
bpolys, bh = [], []
bdmp = []
for i_, g, h_, f_ in zip(bld.id, bld.geom, bld.height, bld.num_floors):
    for p in polys(g):
        bdmp.append(DMP[i_][0] if i_ in DMP else None)
        bpolys.append(p); bh.append(h_ if h_ == h_ and h_ else (f_ * 2.9 if f_ == f_ and f_ else None))
btree = shapely.STRtree(bpolys)
bcent = shapely.STRtree([p.centroid for p in bpolys]); barea = np.array([p.area for p in bpolys])


def density(pt, r=70.0):
    """podíl zastavěné plochy v okruhu r (podle těžišť budov); činžovní bloky ~0,25, vesnice ~0,06"""
    q = pt.buffer(r)
    return float(barea[[i for i in bcent.query(q) if q.contains(bcent.geometries[i])]].sum()) / q.area


def group_med(pb, med):
    """společná změřená výška navazujících sekcí"""
    seen, todo = set(), [i for i in btree.query(pb) if bpolys[i].intersects(pb)]
    while todo and len(seen) < 60:
        i = todo.pop()
        if i in seen: continue
        seen.add(i); q = bpolys[i].buffer(0.8)
        todo += [j for j in btree.query(q) if j not in seen and bpolys[j].intersects(q)]
    v = [bdmp[i] for i in seen if bdmp[i]]
    return float(np.median(v)) if v else med


def rect_dims(p):
    cs = list(p.minimum_rotated_rectangle.exterior.coords)[:3]
    a, b = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
    return p.area / max(a * b, 1e-6), min(a, b)


def group_key(pb):
    """klíč skupiny navazujících budov (nejmenší souřadnice) – stejná barva sekcí jednoho domu ve všech čtvercích"""
    seen, todo = set(), [i for i in btree.query(pb) if bpolys[i].intersects(pb)]
    while todo and len(seen) < 60:
        i = todo.pop()
        if i in seen: continue
        seen.add(i); q = bpolys[i].buffer(0.8)
        todo += [j for j in btree.query(q) if j not in seen and bpolys[j].intersects(q)]
    m = min((bpolys[i].bounds[0], bpolys[i].bounds[1]) for i in seen)
    return wkey(*m)


def panel_like(pb):
    """sekce panelového domu: navazující přesné obdélníky se stejnou hloubkou a výškou (činžáky jsou nepravidelné)"""
    nb_ = [i for i in btree.query(pb) if bpolys[i].intersects(pb)]
    if len(nb_) < 2: return False
    dims = [rect_dims(bpolys[i]) for i in nb_]
    if min(f for f, _ in dims) < 0.95: return False
    ws = [w for _, w in dims]
    if max(ws) - min(ws) > 1.5 or min(ws) < 8: return False
    hs = [bh[i] for i in nb_ if bh[i]]
    if hs and (max(hs) - min(hs) > 3.5 or min(hs) < 11): return False
    return True
def garage_row(p):
    """řada aspoň 3 navazujících malých budov bez typu (do 45 m²) = garáže (OSM je často nemá označené)"""
    seen, todo = set(), [i for i in btree.query(p.buffer(0.8)) if barea[i] < 45 and bpolys[i].intersects(p.buffer(0.8))]
    while todo and len(seen) < 3:
        i = todo.pop()
        if i in seen: continue
        seen.add(i); q = bpolys[i].buffer(0.8)
        todo += [j for j in btree.query(q) if j not in seen and barea[j] < 45 and bpolys[j].intersects(q)]
    return len(seen) >= 3
def zone_split(pieces, zones):
    """části dominanty podle zón ze satelitu (pořadí = priorita) -> (díly, zóna dílu nebo None)"""
    out, zof = [], []
    for p in pieces:
        rem = p
        for z in zones:
            if '_P' not in z: z['_P'] = Polygon([to_local(lon, lat) for lat, lon in z['poly']]).buffer(0)
            q = rem.intersection(z['_P'])
            for g in polys(q):
                for u in unhole(g):
                    if u.area > 4: out.append(u); zof.append(z)
            rem = rem.difference(z['_P'])
        for g in polys(rem):
            for u in unhole(g):
                if u.area > 4: out.append(u); zof.append(None)
    return out, zof


ROOF_CARS = []


def roof_deco(p, deco, top, key):
    """výbava střechy z popisu dominanty -> [[druh, x0, y0, x1, y1, šířka, výška, r, g, b], ...]
    druh 0 = shedy (řady pilové střechy), 1 = pás (světlík, rám skla), 2 = fotovoltaika, 3 = valený oblouk,
    4 = sedlový hřeben (střecha ze štítů, nástavec) s pásem světlíků; 'park' přidá auta na střechu.
    Čáry: 'lines' (lat, lon), 'rel' (zlomky delší a kratší osy půdorysu), 'axis': n (n pruhů podél delší osy), jinak řady 'a' + 'gap'"""
    out = []
    o = p.minimum_rotated_rectangle; oc = list(o.exterior.coords)[:3]
    e1 = np.subtract(oc[1], oc[0]); e2 = np.subtract(oc[2], oc[1])
    if np.linalg.norm(e1) < np.linalg.norm(e2): e1, e2 = e2, e1
    OL, OW = float(np.linalg.norm(e1)), float(np.linalg.norm(e2)); ou, ov = e1 / OL, e2 / OW
    O0 = np.array(o.centroid.coords[0]) - ou * OL / 2 - ov * OW / 2
    rel = lambda s_, t_: tuple(O0 + ou * s_ * OL + ov * t_ * OW)
    for d in deco:
        k = d['k']
        if 'axis' in d:
            n = d['axis']; d = {**d, 'w': OW / n * d.get('fill', 1.0)}
            segs = [LineString([rel(-0.1, (i + 0.5) / n), rel(1.1, (i + 0.5) / n)]) for i in range(n)]
        elif 'rel' in d:
            segs = [LineString([rel(a_, b_), rel(c_, d_)]) for a_, b_, c_, d_ in d['rel']]
        elif 'lines' in d:
            segs = [LineString([to_local(l[1], l[0]), to_local(l[3], l[2])]) for l in d['lines']]
        else:
            a = math.radians(d['a']) if 'a' in d else math.atan2(ou[1], ou[0]); c = p.centroid; R = math.sqrt(p.area) * 3 + 50
            ux, uy, nx, ny = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
            segs = [LineString([(c.x + nx * t - ux * R, c.y + ny * t - uy * R), (c.x + nx * t + ux * R, c.y + ny * t + uy * R)])
                    for t in np.arange(-R + d['gap'] / 2, R, d['gap'])]
        inner = p.buffer(-max(0.6, d.get('w', 0) / 2 + 0.3) if k == 'solar' else -0.6)   # panely nesmí přečnívat přes okraj
        for sg in segs:
            for q in polys_lines(sg.intersection(inner)):
                if q.length < 1.5: continue
                (x0, y0), (x1, y1) = q.coords[0], q.coords[-1]
                if k == 'park':
                    L = q.length; ux, uy = (x1 - x0) / L, (y1 - y0) / L
                    rng = random.Random(key + f'{x0:.0f}{y0:.0f}')
                    for side in (-1, 1):
                        for t in np.arange(1.6, L - 1.6, 2.6):
                            cx, cy = x0 + ux * t - uy * side * 4.2, y0 + uy * t + ux * side * 4.2
                            if inner.contains(Point(cx, cy)) and rng.random() < d.get('p', 0.72):
                                ROOF_CARS.append([cx, cy, top, math.atan2(ux, -uy) + (math.pi if rng.random() < 0.5 else 0), rng.randrange(8)])
                    for side in (-1, 1):       # vodorovné značení: okraj řady stání a čáry mezi stáními
                        out.append([1, round(x0 - uy * side * 6.6, 2), round(y0 + ux * side * 6.6, 2), round(x1 - uy * side * 6.6, 2),
                                    round(y1 + ux * side * 6.6, 2), 0.25, 0.04, 226, 226, 220])
                        for t in np.arange(0.3, L - 0.3, 2.6):
                            ax_, ay_ = x0 + ux * t - uy * side * 1.8, y0 + uy * t + ux * side * 1.8
                            bx_, by_ = x0 + ux * t - uy * side * 6.6, y0 + uy * t + ux * side * 6.6
                            if inner.contains(Point(ax_, ay_)) and inner.contains(Point(bx_, by_)):
                                out.append([1, round(ax_, 2), round(ay_, 2), round(bx_, 2), round(by_, 2), 0.2, 0.04, 222, 222, 216])
                    continue
                kk = {'saw': 0, 'strip': 1, 'solar': 2, 'barrel': 3, 'ridge': 4}[k]
                w = d.get('w', d.get('gap', 4))
                cs = d.get('cs', [d.get('c', [200, 200, 200])]); col = cs[len(out) % len(cs)]
                out.append([kk, round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2), round(w, 2), d.get('h', 0.6), *col, *d.get('c2', [])])
    return out


def polys_lines(g):
    if g.is_empty: return []
    if g.geom_type == 'LineString': return [g]
    return [q for q in getattr(g, 'geoms', []) if q.geom_type == 'LineString']


TEN_WALLS = [(232, 206, 150), (226, 186, 160), (206, 214, 180), (236, 226, 200), (214, 196, 170), (204, 202, 196),
             (238, 214, 170), (220, 176, 146), (196, 208, 214), (230, 220, 210)]
TEN_ROOFS = [(70, 72, 80), (96, 64, 52), (150, 62, 44), (60, 64, 72), (128, 60, 46), (84, 88, 96)]
squares = [r.geom for _, r in lu.iterrows() if (sname(r) or '').startswith('náměstí doktora Edvarda Beneše')]
GND_DOM = {}
for _, r in bld.iterrows():
    if r.is_underground is True: continue
    pieces = [u for g in polys(r.geom) for u in unhole(g)]
    dom0 = DOM_BY_ID.get(r.id)
    zof = [None] * len(pieces); gnd_dom = None
    if dom0 and dom0['spec'].get('zones'):
        xy_ = np.array([c for q in pieces for c in q.exterior.coords]); gnd_dom = float(ground(xy_[:, 0], xy_[:, 1]).mean())   # jedna úroveň pro všechny díly
        GND_DOM[dom0['name']] = gnd_dom
        pieces, zof = zone_split(pieces, dom0['spec']['zones'])
    tw_piece = None
    if dom0 and pieces:
        pt0 = Point(*dom0['xy']); inside = [k for k, q in enumerate(pieces) if q.buffer(2).contains(pt0)]
        tw_piece = inside[0] if inside else max(range(len(pieces)), key=lambda k: pieces[k].area)
    for pi, p in enumerate(pieces):
        if not EXT.intersects(p): continue
        cen = p.centroid
        own = AREA.contains(cen)
        if not own and not CLIP.contains(cen): continue         # těžiště mimo mapu: budova nikomu nepatří
        if not CLIP.buffer(-1.0).contains(p): p = p.intersection(CLIP.buffer(-1.0))   # ořez jen na okraji mapy
        if p.geom_type != 'Polygon': continue
        URBAN = geo.chunk_of(cen.x + CX, cen.y + CY) != (0, 0)
        p = p.simplify(0.2)
        if p.area < 6 or not p.is_valid: continue
        p = shapely.geometry.polygon.orient(p, 1.0)
        bid = len(buildings)
        c = r['class'] if isinstance(r['class'], str) else ''
        nm = sname(r)
        key = r.id; area = p.area
        _ru = RUIAN.get(r.id)
        if _ru and _ru[0] and c in ('', 'yes', 'residential'):
            # třída apartments znamená plochou střechu, ale bytový dům může mít šikmou: bez potvrzení laserem zůstane obytný
            c = 'residential' if _ru[0] == 'apartments' and not (r.id in DMP and DMP[r.id][1] - DMP[r.id][0] < 0.4) else _ru[0]
        if not c and area < 45 and garage_row(p): c = 'garages'
        floors = r.num_floors if r.num_floors == r.num_floors and r.num_floors else None
        if not floors and _ru and _ru[1] and r.id not in DMP: floors = _ru[1]      # laser má přednost
        _so0 = SAT['b'].get(r.id, {})                                   # ruční opravy z hlášení (assets/upresneni.json "b"): cls, fl (podlaží), name
        if 'cls' in _so0: c = _so0['cls']
        if 'fl' in _so0: floors = _so0['fl']
        if 'name' in _so0: nm = _so0['name']
        hgt = r.height if r.height == r.height and r.height else None
        lm = None
        if c == 'chapel': lm = 'chapel'
        if c in ('church', 'cathedral') and area > 60: lm = 'church'       # každý kostel má věž
        _dm = DOM_BY_ID.get(r.id)
        if _dm and _dm['spec'].get('lm'): lm = _dm['spec']['lm']          # vlastní model z dominanty (např. radnice)
        hits = addr_tree.query(p.buffer(1.5))
        adrs = sorted({addr_txt[i] for i in hits if p.buffer(1.5).contains(addr_pts[i])})
        rs = ROOF_MAP.get(r.roof_shape if isinstance(r.roof_shape, str) else '', None)
        # paneláky a vyšší bytové domy mají ploché střechy
        if not lm and (c == 'apartments' or (floors and floors >= 5) or (hgt and hgt >= 14)): rs = 'flat'
        tenement = panel = False
        if URBAN and not lm:
            pb = p.buffer(0.8)
            attached = sum(1 for i in btree.query(pb) if bpolys[i].intersects(pb)) >= 2
            tall = (floors and floors >= 9) or (hgt and hgt >= 28)
            if attached and panel_like(pb): rs = 'flat'; panel = True
            elif attached and not tall and area < 1500 and L_obb_ok(p) and density(cen) >= 0.12 and c in ('', 'residential', 'apartments', 'house', 'civic', 'commercial', 'retail', 'hotel', 'office', 'yes', 'school'):
                tenement = True
                rs0 = ROOF_MAP.get(r.roof_shape if isinstance(r.roof_shape, str) else '', None)
                rs = rs0 if rs0 and rs0 != 'flat' else ('gabled' if h01(key + 't') < 0.75 else 'hipped')   # podle fotek centra: hlavně sedlové se štíty
        # tvar střechy podle měření DMP: plochá střecha má vršek (p90) skoro stejně vysoko jako medián, šikmá má hřeben výš
        if not lm and r.id in DMP and area > 80 and DMP[r.id][0] >= 6 and DMP[r.id][1] - DMP[r.id][0] < 0.4:
            rs = 'flat'
            if tenement or (DMP[r.id][0] >= 11 and c in ('', 'residential', 'apartments', 'yes')): tenement = False; panel = True
        # i malý dům: laser na celé střeše ve stejné výšce znamená plochou nebo téměř plochou střechu (ověřeno na ortofotu)
        if not lm and r.id in DMP and area >= 25 and DMP[r.id][0] >= 2.2 and DMP[r.id][1] - DMP[r.id][0] < 0.35:
            rs = 'flat'; tenement = False
        if lm == 'radnice': rs = 'hipped'
        if URBAN and not lm and rs not in (None, 'flat') and area > 2500: rs = 'flat'
        if c == 'roof': rs = 'flat'                     # přístřešek (nástupiště, zastávka): střecha na sloupech
        so = SAT['b'].get(r.id, {})
        dom = DOM_BY_ID.get(r.id); dsp = dom['spec'] if dom else None
        if dsp:
            lm = dsp.get('lm', 'dom'); tenement = panel = False      # vlastní model z assets/custom_models.js má přednost
            if 'r' in dsp: rs = 'flat' if dsp['r'] == 'flat' else dsp['r']
        if not lm and so.get('rs') == 'flat': rs = 'flat'; tenement = False
        # šikmá ze snímku jen u menších domů: velké a vysoké budovy mají na snímku vlastní stín a techniku (falešný hřeben)
        if not lm and not panel and so.get('rs') == 'pitched' and rs in (None, 'flat') and area < 700 and c not in FLAT_CLS \
                and not (floors and floors >= 6) and not (hgt and hgt >= 18):
            rs = 'hipped' if h01(key + 't') < 0.6 else 'gabled'
        if rs is None:
            if c in FLAT_CLS or area > 650: rs = 'flat'
            elif c in PITCHED_CLS or (not c and 25 < area < 400): rs = 'gabled' if h01(key) < 0.62 else 'hipped'
            else: rs = 'flat'
        if not lm and so.get('r'): rs = so['r']; tenement = panel = False
        obb = p.minimum_rotated_rectangle
        oc = list(obb.exterior.coords)[:4]
        e1 = np.subtract(oc[1], oc[0]); e2 = np.subtract(oc[2], oc[1])
        if np.linalg.norm(e1) < np.linalg.norm(e2): e1, e2 = e2, e1
        L, Wd = float(np.linalg.norm(e1)), float(np.linalg.norm(e2))
        ang = math.atan2(e1[1], e1[0])
        if HREBENY.get(r.id) == 'S': ang += math.pi / 2; L, Wd = Wd, L      # hřeben podél kratší strany (změřeno laserem)
        parts = []
        if rs != 'flat':
            parts = [[round(obb.centroid.x, 2), round(obb.centroid.y, 2), round(ang, 4), round(L, 2), round(Wd, 2)]] \
                if area / max(obb.area, 1) > 0.9 else roof_parts(p, ang)
            if not parts: rs = 'flat'
        roofh = min(max(pp[4] for pp in parts) / 2 * math.tan(math.radians(40)), 7.0) if parts else 0.0
        if tenement:
            roofh = min(roofh, 6.5)
            total = (hgt if hgt and hgt > 9 else (floors or (2 if area < 130 else 4)) * 3.2 + 0.6) + roofh * 0.6   # malé řadovky 2 patra
        elif hgt: total = hgt
        elif floors: total = floors * 2.9 + 0.4 + roofh * 0.8
        else:
            total = {'garage': 2.6, 'garages': 2.6, 'shed': 2.4, 'carport': 2.4, 'apartments': 16, 'industrial': 7,
                     'warehouse': 7, 'school': 12, 'university': 14, 'civic': 9, 'commercial': 9, 'retail': 6}.get(c)
            if total is None: total = 2.8 if area < 30 else (6.0 + roofh) if area < 300 else 9.0
        if dsp and 'rh' in dsp and parts: roofh = float(dsp['rh'])
        eave = max(2.2, total - roofh) if rs != 'flat' else max(2.2, total)
        if dsp and 'h' in dsp: eave = float(dsp['h'])
        xs_, ys_ = np.array(p.exterior.coords).T
        zs = ground(xs_, ys_)
        base, gnd = float(zs.min()) - 0.6, float(zs.mean())
        if c in ('garage', 'garages', 'carport', 'shed'): style = 2
        elif c == 'apartments' or (floors and floors >= 4) or total > 11: style = 1
        elif c in ('industrial', 'warehouse', 'commercial', 'retail'): style = 3
        else: style = 0
        if tenement: style = 11
        if panel: style = 1
        if r.id in DMP and not dsp and not lm and 'h' not in _so0 and c not in ('garage', 'garages', 'carport', 'shed', 'roof'):
            med, top = DMP[r.id]
            if panel: med = group_med(p.buffer(0.8), med)   # sekce jednoho paneláku stejně vysoké
            if rs == 'flat': total = eave = med
            else: total = max(top, med + 1); eave = max(2.2, total - roofh)
        if c == 'roof': style = 12; total = hgt if hgt and hgt < 12 else 4.5; eave = total
        if c in ('retail', 'commercial') and area > 1500 and not tenement: style = 3     # obchodní centra: pásy oken
        pal = TEN_WALLS if style == 11 else PANEL if style == 1 else WALLS
        wc = hexcol(r.facade_color, pal[int(h01((group_key(p.buffer(0.8)) if panel else key) + 'w') * 1000) % len(pal)])
        if style == 2: wc = (196, 190, 178)
        rp = ROOF_F if rs == 'flat' else TEN_ROOFS if tenement else ROOF_P
        rc = hexcol(r.roof_color, rp[int(h01(key + 'r') * 1000) % len(rp)])
        if 'rc' in so and not lm: rc = tuple(so['rc'])
        if 'wc' in so and not lm: wc = tuple(so['wc'])
        if dsp:
            if 'wc' in dsp: wc = tuple(dsp['wc'])
            if 'rc' in dsp: rc = tuple(dsp['rc'])
            if 'win' in dsp: style = dsp['win']
        ring = [[round(x, 2), round(y, 2)] for x, y in list(p.exterior.coords)[:-1]]
        b = {'p': ring, 'b': round(base, 2), 'g': round(gnd, 2), 'e': round(gnd + eave, 2), 'r': rs, 'rh': round(roofh, 2),
             'parts': parts, 'wc': wc, 'rc': rc, 's': style, 'id': bid}
        if lm: b['lm'] = lm
        if dsp and dsp.get('hangar'):          # hangár: posuvná vrata ve stěně obrácené k bodu 'face' (plocha letiště), ostatní stěny vlnitý plech
            b['hd'] = [*[round(v, 2) for v in dsp.get('face_xy', dom['xy'])], dsp.get('vrata', 5.0)]; b['s'] = 21
        if dsp:
            b['dn'] = dom['name']
            if dsp.get('canopy'): b['cn'] = dsp['canopy']
            for blk in (dsp.get('blocks', []) if pi == tw_piece else []):
                o = p.minimum_rotated_rectangle; cs = list(o.exterior.coords)[:3]
                e1 = np.subtract(cs[1], cs[0]); e2 = np.subtract(cs[2], cs[1])
                if np.linalg.norm(e1) < np.linalg.norm(e2): e1, e2 = e2, e1
                bl, bw = float(np.linalg.norm(e1)) * blk['l'], float(np.linalg.norm(e2)) * blk['w']
                b.setdefault('blk', []).append([round(p.centroid.x, 2), round(p.centroid.y, 2), round(math.atan2(e1[1], e1[0]), 4),
                                                round(bl, 2), round(bw, 2), round(gnd + blk['h'], 2), list(blk.get('rc', rc))])
            for tw in (dsp.get('towers', []) if pi == tw_piece else []):
                x, y, a = dom_pos(pieces[pi], tw['at'], dsp, dom, tw['w'], tw.get('side', 0.0), tw.get('t', 0.5))
                if not own and not AREA.contains(Point(x, y)) and not EXT.contains(Point(x, y)): continue
                b.setdefault('tw', []).append({'x': round(x, 2), 'y': round(y, 2), 'a': round(a, 4), 'w': tw['w'], 'h': round(gnd + tw['h'], 2),
                    'to': round(gnd + tw.get('to', tw['h']), 2), 'top': tw['top'], 'tc': tw.get('tc', [90, 96, 104]), 'wc': list(tw.get('wc', wc)),
                    'clock': tw.get('clock', 0), 'round': tw.get('round', 0), 'stone': tw.get('stone', 0), 'ruin': tw.get('ruin', 0), 'b': round(base, 2)})
            if dsp.get('skylights') and pi == tw_piece:          # světlíky na ploché střeše
                inner = p.buffer(-6.0)
                if not inner.is_empty:
                    minx, miny, maxx, maxy = inner.bounds; b['rt'] = []
                    for gx in np.arange(minx, maxx, 13):
                        for gy in np.arange(miny, maxy, 11):
                            if inner.contains(Point(gx, gy)) and h01(f'sk{gx:.0f}{gy:.0f}') < 0.45: b['rt'].append([round(gx, 2), round(gy, 2), 1, round(ang, 3)])
            for ch in (dsp.get('chimneys', []) if pi == tw_piece else []):
                x, y, a = dom_pos(p, ch['at'], dsp, dom, ch['r'] * 2, ch.get('side', 0.0))
                b.setdefault('chs', []).append([round(x, 2), round(y, 2), round(base, 2), round(gnd + ch['h'], 2), ch['r'], list(ch['col'])])
        if lm == 'church' and 'Antonín' not in (nm or ''):
            # menší kostel = nižší loď a věž (velké kostely mají výchozí 11 / 31 / 47 m)
            tw = min(31.0, 10 + L * 0.5)
            b['cht'] = [round(min(11.0, 5 + L * 0.15), 1), round(tw, 1), round(tw + min(16.0, 4 + L * 0.3), 1)]
        # technologie a světlíky na velkých plochých střechách (jen městské čtverce)
        if URBAN and rs == 'flat' and style != 2 and area > 300 and not lm:
            inner = p.buffer(-2.0)
            if not inner.is_empty:
                trng = random.Random(key)
                minx, miny, maxx, maxy = inner.bounds
                rt = []
                for _ in range(int(min(90, area / 60))):
                    x_, y_ = trng.uniform(minx, maxx), trng.uniform(miny, maxy)
                    if inner.contains(Point(x_, y_)):
                        rt.append([round(x_, 2), round(y_, 2), trng.choice((0, 0, 1, 1, 2)), round(ang, 3)])
                b['rt'] = rt
        if SAT['b'].get(r.id, {}).get('sachta') and rs == 'flat' and not lm:                 # chybějící výtahová šachta (nástavba typu 2) uprostřed střechy
            b['rt'] = list(b.get('rt', [])) + [[round(p.centroid.x, 2), round(p.centroid.y, 2), 2, round(ang, 3)]]
        if lm == 'radnice' and squares:
            # průčelí s věžemi = bod obrysu nejblíž náměstí, tečna podél fasády
            sq = squares[0].centroid
            near = shapely.ops.nearest_points(p.exterior, sq)[0]
            dd = p.exterior.project(near)
            a_ = p.exterior.interpolate(dd - 2); b_ = p.exterior.interpolate(dd + 2)
            b['rad'] = [round(near.x, 2), round(near.y, 2), round(math.atan2(b_.y - a_.y, b_.x - a_.x), 4),
                        round(math.atan2(sq.y - near.y, sq.x - near.x), 4)]
            b['wc'] = (226, 212, 176); b['rc'] = (58, 66, 72); b['e'] = round(gnd + 17.5, 2)
        # komín u rodinných domů a vikýř u větších střech
        if parts and style in (0, 1, 11) and not lm:
            cx, cy, a, pl, pw = max(parts, key=lambda q: q[3] * q[4])
            s_ = (h01(key + 'c') - 0.5) * pl * 0.6; t_ = (0.12 + 0.18 * h01(key + 'd')) * pw * (1 if h01(key + 'e') > 0.5 else -1)
            hx, hy = cx + math.cos(a) * s_ - math.sin(a) * t_, cy + math.sin(a) * s_ + math.cos(a) * t_
            ridge = gnd + eave + roofh
            top = ridge - abs(t_) / (pw / 2 + 0.45) * roofh + 1.1
            b['ch'] = [round(hx, 2), round(hy, 2), round(top, 2)]
            if own: chimneys.append([hx, hy, top, bid])
            if rs == 'gabled' and pl > 9 and pw > 6.5 and h01(key + 'v') < 0.55:
                b['dm'] = 1
        if dsp:                                  # díly podle zón ze satelitu a výbava střechy
            z = zof[pi]; zs = z or {}
            g0 = gnd if gnd_dom is None else gnd_dom
            b['e'] = round(g0 + zs.get('h', b['e'] - gnd), 2); b['g'] = round(g0, 2)
            if 'rc' in zs: b['rc'] = tuple(zs['rc'])
            if 'wc' in zs: b['wc'] = tuple(zs['wc'])
            if 'win' in zs: b['s'] = zs['win']
            if z: b['r'] = 'flat'; b['parts'] = []; b['rh'] = 0.0; b.pop('rt', None)
            deco = zs.get('deco') if z else dsp.get('deco')
            if deco: b['dz'] = roof_deco(p, deco, b['e'], key + str(pi))
        if not own: b['gh'] = 1                  # budova sousedního čtverce (jen kvůli švu)
        buildings.append(b)
        bmd.polygon(P(p.exterior.coords), fill=255)
        if not own: continue
        lon, lat = to_lonlat(p.centroid.x, p.centroid.y)
        # obrys při najetí myší: skutečný vršek vykreslené budovy (zóny, výbava střechy, věže, modely)
        top_, ring_ = gnd + eave + roofh, ring
        if dsp:
            top_ = b['e'] + (b['rh'] if b['r'] != 'flat' else 0.0)
            if b.get('dz'): top_ = max(top_, b['e'] + max(q[6] for q in b['dz']))
            if b.get('tw'): top_ = max(top_, max(t['h'] for t in b['tw']))           # věže dominanty (vozidla se za ně schovají)
            if 'top' in dsp: top_ = max(top_, gnd + float(dsp['top']))               # vlastní model (lm) vyšší než budova v datech
        pam_ = pam_vrsek(key)                                          # vlastní model památky: vršek modelu (i s věží)
        if pam_ is not None: top_ = pam_
        binfo.append({'id': bid, 'oid': key, 'name': nm, 'cls': _so0.get('cls_cz') or CLS_CZ.get(c, 'budova' if not c else c), 'floors': floors,
                      'h': round(total, 1), 'roof': rs, 'addr': adrs, 'lon': round(float(lon), 6), 'lat': round(float(lat), 6),
                      'ring': ring_, 'top': round(top_, 2), 'base': round(base, 2), **({'pam': 1} if pam_ is not None else {}),
                      **({'roof_geometry': {'eave': b['e'], 'height': b['rh'], 'parts': b['parts']}}
                         if not lm and pam_ is None and rs in ('gabled', 'hipped') and b['parts'] else {})})
# samostatné stavby dominant (zřícenina, rozhledna, VTE): jen věž na bodu dominanty
for d in DOMS:
    sp = d['spec']
    if not sp.get('only'): continue
    x, y = d['xy']
    if not EXT_P.contains(Point(x, y)): continue
    own = AREA.contains(Point(x, y)); g = float(ground(x, y))
    bid = len(buildings)
    tw0 = (sp.get('towers') or [{'w': sp.get('w', 4), 'h': sp.get('h', 0)}])[0]   # bez věží (jen vlastní model 'lm'): půdorys w × w m (výchozí 4), výška 'h'
    w0 = tw0['w'] / 2
    ring = [[round(x - w0, 2), round(y - w0, 2)], [round(x + w0, 2), round(y - w0, 2)], [round(x + w0, 2), round(y + w0, 2)], [round(x - w0, 2), round(y + w0, 2)]]
    b = {'p': ring, 'b': round(g - 0.6, 2), 'g': round(g, 2), 'e': round(g, 2), 'r': 'flat', 'rh': 0.0, 'parts': [], 'wc': (150, 146, 136), 'rc': (150, 146, 136),
         's': 4, 'id': bid, 'lm': sp.get('lm', 'dom'), 'dn': d['name'], 'only': 1, 'tw': []}
    # výšky terénu ve vybraných bodech pro vlastní model ("probe": {"jméno": [lat, lon]} -> b['probe'][jméno], stejné měřítko jako b.g)
    if sp.get('probe'): b['probe'] = {k: round(float(ground(*to_local(lo, la))), 2) for k, (la, lo) in sp['probe'].items()}
    # osa vlastního modelu na mostě ("os": [[lat, lon], …]) -> b['os'] = [[dx, dy, výška mostovky - g]] po ~2,9 m (mostovka z DECKS, jinak terén)
    if sp.get('os'):
        oc_ = [to_local(lo, la) for la, lo in sp['os']]
        for _ in range(2):                                      # Chaikin: osa z OSM má zlomy, skutečný tunel je plynule zakřivený
            oc_ = [oc_[0]] + [q_ for p0, p1 in zip(oc_, oc_[1:]) for q_ in ((0.75 * p0[0] + 0.25 * p1[0], 0.75 * p0[1] + 0.25 * p1[1]), (0.25 * p0[0] + 0.75 * p1[0], 0.25 * p0[1] + 0.75 * p1[1]))] + [oc_[-1]]
        ol = LineString(oc_); n_ = max(2, int(round(ol.length / 2.875)))
        b['os'] = []
        for k_ in range(n_ + 1):
            q = ol.interpolate(ol.length * k_ / n_); zq = float(ground(q.x, q.y)); bd_ = 12.0
            for D_ in DECKS:
                dd = D_[0].distance(q)
                if D_[5] == 'road' and dd < bd_: bd_ = dd; zq = float(np.interp(D_[0].project(q), D_[1], D_[2]))
            b['os'].append([round(q.x - x, 2), round(q.y - y, 2), round(zq - g, 2)])
        zs_ = np.array([v[2] for v in b['os']])             # přeskok mezi dvěma mostovkami z dat vyhladit (klouzavý průměr)
        for _ in range(3): zs_ = np.convolve(np.pad(zs_, 2, mode='edge'), np.ones(5) / 5, mode='valid')
        for v, z_ in zip(b['os'], zs_): v[2] = round(float(z_), 2)
    for tw in sp.get('towers', []):
        b['tw'].append({'x': round(x, 2), 'y': round(y, 2), 'a': 0.0, 'w': tw['w'], 'h': round(g + tw['h'], 2), 'to': round(g + tw.get('to', tw['h']), 2),
                        'top': tw['top'], 'tc': tw.get('tc', [90, 96, 104]), 'wc': [150, 146, 136], 'clock': 0, 'round': tw.get('round', 0),
                        'stone': tw.get('stone', 0), 'ruin': tw.get('ruin', 0), 'b': round(g - 0.6, 2)})
    if not own: b['gh'] = 1
    buildings.append(b)
    r_ = 10 + tw0['w'] * 0.75; nd.ellipse([*P([(x - r_, y + r_)])[0], *P([(x + r_, y - r_)])[0]], fill=255)   # bez stromů kolem
    if own:
        th_ = sp.get('top', tw0.get('to', tw0['h']))
        binfo.append({'id': bid, 'oid': d['name'], 'name': d['name'], 'cls': sp.get('cls', 'dominanta'),
                      'floors': None, 'h': round(float(th_), 1), 'roof': 'cone', 'addr': [], 'lon': round(float(d['lon']), 6), 'lat': round(float(d['lat']), 6),
                      'ring': ring, 'top': round(g + th_, 2), 'base': round(g - 0.6, 2)})
# komíny a chladicí věže z OSM (nastroje/kominy.py), vzhled jednotlivých v assets/upresneni.json: "kominy": [{"lat", "lon", "wc", "pr"}]
for k_ in (json.load(open('assets/kominy.json')) if os.path.exists('assets/kominy.json') else []):
    x, y = to_local(k_['lon'], k_['lat'])
    if not EXT_P.contains(Point(x, y)): continue
    own = AREA.contains(Point(x, y)); g = float(ground(x, y)); h_ = float(k_['h'])
    vz = next((q for q in UP.get('kominy', []) if math.dist((x, y), to_local(q['lon'], q['lat'])) < 20), {})
    vez = k_['k'] == 'vez'; dr = {'vez': 'v', 'stozar': 'm', 'nadrz': 't', 'rozhledna': 'r'}.get(k_['k'], 'c')
    rp = k_.get('r') or {'v': 10.0, 'm': 2.5, 't': 5.0, 'r': 3.2, 'c': max(2.5, h_ * 0.045)}[dr]
    wc = list(vz.get('wc', {'v': [176, 172, 160], 'm': [150, 152, 156], 't': [186, 184, 176], 'r': [176, 112, 62]}.get(dr, [168, 162, 150])))
    b = {'p': [[round(x - 0.1, 2), round(y - 0.1, 2)], [round(x + 0.1, 2), round(y - 0.1, 2)], [round(x + 0.1, 2), round(y + 0.1, 2)]],
         'b': round(g - 0.6, 2), 'g': round(g, 2), 'e': round(g + h_, 2), 'r': 'flat', 'rh': 0.0, 'parts': [], 'wc': tuple(wc), 'rc': tuple(wc),
         's': 4, 'id': len(buildings), 'lm': 'dom', 'dn': 'komín', 'only': 1, 'tw': [],
         'stk': {'k': dr, 'x': round(x, 2), 'y': round(y, 2), 'r': round(rp, 2), 'wc': wc, 'pr': vz.get('pr', 1 if h_ >= 100 and dr == 'c' else 0)}}   # vysoké komíny mívají výstražné pruhy
    if not own: b['gh'] = 1
    elif dr == 'c': chimneys.append([x, y, g + h_, b['id']])
    buildings.append(b)
    r_ = rp + 3; nd.ellipse([*P([(x - r_, y + r_)])[0], *P([(x + r_, y - r_)])[0]], fill=255)   # bez stromů kolem
# hráze nádrží: kamenná zeď s korunou (v datech polygon), budova bez oken
for _, r in inf.iterrows():
    if r['class'] != 'dam' or r.geom.geom_type not in ('Polygon', 'MultiPolygon'): continue
    for p in polys(r.geom):
        if not EXT.intersects(p) or p.area < 20: continue
        p = shapely.geometry.polygon.orient(p.simplify(0.3), 1.0)
        xs_, ys_ = np.array(p.exterior.coords).T; zs = ground(xs_, ys_)
        own = AREA.contains(p.centroid)
        b = {'p': [[round(x, 2), round(y, 2)] for x, y in list(p.exterior.coords)[:-1]], 'b': round(float(zs.min()) - 0.6, 2),
             'g': round(float(zs.mean()), 2), 'e': round(float(zs.max()) + 1.2, 2), 'r': 'flat', 'rh': 0.0, 'parts': [],
             'wc': (150, 146, 136), 'rc': (172, 168, 158), 's': 5, 'id': len(buildings)}
        if not own: b['gh'] = 1
        for d in DOMS:                     # dominanta na hrázi (věžičky přehrady Harcov)
            if 'towers' in d['spec'] and not d['spec'].get('only') and p.buffer(30).contains(Point(*d['xy'])) and r.id not in DOM_BY_ID:
                b['lm'] = 'dom'; b['dn'] = d['name']; b['tw'] = []
                for tw in d['spec']['towers']:
                    x, y, a = dom_pos(p, tw['at'], d['spec'], d, tw['w'], tw.get('side', 0.0), tw.get('t', 0.5))
                    g2 = float(ground(x, y))
                    b['tw'].append({'x': round(x, 2), 'y': round(y, 2), 'a': round(a, 4), 'w': tw['w'], 'h': round(b['e'] + tw['h'], 2),
                                    'to': round(b['e'] + tw.get('to', tw['h']), 2), 'top': tw['top'], 'tc': tw.get('tc', [90, 96, 104]),
                                    'wc': [150, 146, 136], 'clock': 0, 'round': tw.get('round', 0), 'stone': 1, 'ruin': 0, 'b': round(b['e'] - 0.5, 2)})
        buildings.append(b); bmd.polygon(P(p.exterior.coords), fill=255)
hk = [r.geom for _, r in lu.iterrows() if r['class'] == 'barracks' and 'Horní' in (sname(r) or '')]
if hk:
    gates = sorted([r.geom for _, r in inf.iterrows() if r['class'] == 'gate' and r.geom.geom_type == 'Point' and hk[0].buffer(5).contains(r.geom)], key=lambda g: g.x)[:2]
    if gates:
        gx_, gy_ = sum(g.x for g in gates) / len(gates), sum(g.y for g in gates) / len(gates)
        cand = [b for b in buildings if hk[0].contains(shapely.geometry.Polygon(b['p']).centroid) and shapely.geometry.Polygon(b['p']).area > 300]
        if cand:
            hq = min(cand, key=lambda b: shapely.geometry.Polygon(b['p']).centroid.distance(Point(gx_, gy_)))
            hq['lm'] = 'hq'; hq.pop('ch', None); hq.pop('dm', None)
            if not hq['parts']:
                pq_ = shapely.geometry.Polygon(hq['p']); o = pq_.minimum_rotated_rectangle; oc = list(o.exterior.coords)[:4]
                e1 = np.subtract(oc[1], oc[0]); e2 = np.subtract(oc[2], oc[1])
                if np.linalg.norm(e1) < np.linalg.norm(e2): e1, e2 = e2, e1
                hq['parts'] = [[round(o.centroid.x, 2), round(o.centroid.y, 2), round(math.atan2(e1[1], e1[0]), 4), round(float(np.linalg.norm(e1)), 2), round(float(np.linalg.norm(e2)), 2)]]
                hq['r'] = 'hipped'; hq['rh'] = round(min(np.linalg.norm(e2) / 2 * math.tan(math.radians(40)), 7), 2)
                hq['e'] = round(hq['e'] - 0.0, 2)
            print('velitelství kasáren', hq['id'])
print('budov', len(buildings), 'z toho od sousedů', sum(1 for b in buildings if b.get('gh')), 'komínů', len(chimneys))

# ---------------- mobiliář, lampy, oplocení ----------------
props = {'bench': [], 'lamp': [], 'bin': [], 'recycling': [], 'shelter': [], 'tower': [], 'pole': []}
lamp_pts = []
for _, r in inf.iterrows():
    g = r.geom; k = r['class']
    if g.geom_type != 'Point' or not AREA.contains(g): continue
    z = float(ground(g.x, g.y))
    nd_ = nearest_dir(g, all_tree, all_lines, 15)
    ang = nd_[0] if nd_ else h01(wkey(g.x, g.y)) * 6.28
    if k == 'bench': props['bench'].append([g.x, g.y, z, ang])
    elif k == 'street_lamp':
        # lampy podchodu pod silnicí mají v datech polohu pod vozovkou: stožár uprostřed jízdních pruhů se nekreslí
        if any(drive_lines[int(k_)][1] / 2 - 0.6 > drive_lines[int(k_)][0].distance(g) for k_ in drive_tree.query(g.buffer(12))): continue
        props['lamp'].append([g.x, g.y, z, ang]); lamp_pts.append(g)
    elif k in ('waste_basket', 'waste_disposal'): props['bin'].append([g.x, g.y, z, ang])
    elif k == 'recycling': props['recycling'].append([g.x, g.y, z, ang])
    elif k == 'power_tower': props['tower'].append([g.x, g.y, z, ang])
    elif k == 'power_pole': props['pole'].append([g.x, g.y, z, ang])
    elif k in ('bus_stop', 'platform'):
        if any(math.hypot(g.x - s[0], g.y - s[1]) < 14 for s in props['shelter']): continue
        nd2 = nearest_dir(g, drive_tree, drive_lines, 20)
        a_s = nd2[0] if nd2 else ang
        if nd2:                                              # otevřená strana přístřešku (-y modelu = vpravo od směru) k silnici, ne podle náhodného směru čáry
            q_ = shapely.ops.nearest_points(nd2[1][0], g)[0]
            if math.cos(a_s) * (q_.y - g.y) - math.sin(a_s) * (q_.x - g.x) > 0: a_s += math.pi
        props['shelter'].append([g.x, g.y, z, a_s])
# lampy podél ulic (v datech jich je jen pár desítek)
lamp_tree = shapely.STRtree(lamp_pts) if lamp_pts else None
bm_arr = np.asarray(bmask)
for l, w, c, n in drive_lines:
    if c in ('service', 'motorway'): continue          # dálnice bez lamp
    d, side = 12.0, 1
    while d < l.length - 5:
        q = l.interpolate(d)
        a_ = l.interpolate(max(0, d - 1)); b_ = l.interpolate(min(l.length, d + 1))
        ang = math.atan2(b_.y - a_.y, b_.x - a_.x)
        off = (w / 2 + 1.3) * side
        x, y = q.x + math.cos(ang + math.pi / 2) * off, q.y + math.sin(ang + math.pi / 2) * off
        px_, py_ = pix(x, y)
        ok = AREA.contains(Point(x, y)) and 0 <= px_ < TWE and 0 <= py_ < TWE and bm_arr[py_, px_] == 0
        if ok and lamp_tree is not None:
            i = lamp_tree.nearest(Point(x, y)); ok = lamp_pts[i].distance(Point(x, y)) > 18
        if ok and not any(abs(x - s[0]) < 12 and abs(y - s[1]) < 12 for s in props['lamp'][-6:]):
            props['lamp'].append([x, y, float(ground(x, y)), ang])
        d += 34; side = -side

# popelnice před rodinnými domy, u chodníku na straně domu
props['wheelie'] = []
res_lines = [(l, w) for l, w, c, n in drive_lines if c in ('residential', 'unclassified', 'living_street', 'tertiary')]
res_tree = shapely.STRtree([l for l, w in res_lines])
for b in buildings:
    if b['s'] != 0 or b.get('lm') or b.get('gh'): continue
    pg = shapely.geometry.Polygon(b['p'])
    c0 = pg.centroid
    if pg.area < 50 or h01('bin' + wkey(c0.x, c0.y)) > 0.55: continue
    brng = wrng(c0.x, c0.y, 'bin')
    i = res_tree.nearest(c0)
    if i is None: break                                # čtverec bez obytných ulic (les, pole)
    l, w = res_lines[i]
    if l.distance(c0) > 28: continue
    q = l.interpolate(l.project(c0))
    dx, dy = c0.x - q.x, c0.y - q.y; dl = math.hypot(dx, dy) or 1; dx, dy = dx / dl, dy / dl
    a_ = l.interpolate(max(0, l.project(q) - 1)); b_ = l.interpolate(min(l.length, l.project(q) + 1))
    ang = math.atan2(b_.y - a_.y, b_.x - a_.x)
    for k in range(brng.choice((1, 2, 2, 3))):
        sx = (k - 0.5) * 0.75
        x = q.x + dx * (w / 2 + 2.4) + math.cos(ang) * sx; y = q.y + dy * (w / 2 + 2.4) + math.sin(ang) * sx
        if AREA.contains(Point(x, y)):
            props['wheelie'].append([x, y, float(ground(x, y)), math.atan2(dy, dx), (0, 0, 1, 2)[k % 4] if k else brng.choice((0, 0, 3))])

lines_out = {'fence': [], 'hedge': [], 'wall': [], 'power': [], 'lift': []}
_DKB = [(D, np.concatenate([[0], np.cumsum(np.hypot(*np.diff(np.array(D[0].coords)[:, :2], axis=0).T))])) for D in DECKS + DECKS_SKRYTE
        if len(D[0].coords) == len(D[2])]
_DKB_T = shapely.STRtree([D[0] for D, _c in _DKB]) if _DKB else None
def on_bridge(x, y, zg, m=4.0):
    """bod (terén zg) leží v pásu mostovky (půl šířky + m), která je tam aspoň 1,5 m nad ním"""
    if _DKB_T is None: return False
    q = Point(x, y)
    for k in _DKB_T.query(q, predicate='dwithin', distance=m + 10.0):
        D, cum = _DKB[int(k)]
        if D[0].distance(q) <= D[4] / 2 + m and float(np.interp(D[0].project(q), cum, D[2])) - zg > 1.5: return True
    return False
_WIN = shapely.prepared.prep(shapely.unary_union([p for g_ in wat.geom for p in polys(g_)] or [Polygon()]).buffer(-1.5))
for _, r in inf.iterrows():
    k = r['class']
    kk = {'fence': 'fence', 'hedge': 'hedge', 'wall': 'wall', 'retaining_wall': 'wall', 'power_line': 'power', 'minor_line': 'power',
          'chair_lift': 'lift', 'drag_lift': 'lift', 't-bar': 'lift', 'platter': 'lift', 'cable_car': 'lift', 'gondola': 'lift'}.get(k)
    if not kk: continue
    for l in lines(r.geom.intersection(AREA)):
        l = l.segmentize(4.0)
        xs_, ys_ = np.array(l.coords).T[:2]
        pl_ = [[round(x, 2), round(y, 2), round(float(zz), 2)] for x, y, zz in zip(xs_, ys_, ground(xs_, ys_))]
        if kk not in ('fence', 'hedge', 'wall'): lines_out[kk].append(pl_); continue
        # plot nebo zábradlí z dat na mostě by na terénu sbíhalo po břehu do vody: část v pásu mostovky nad terénem a nad vodou
        # se nekreslí (mostovka má vlastní zábradlí)
        run_ = []
        for q_ in pl_ + [None]:
            if q_ is not None and not (_WIN.contains(Point(q_[0], q_[1])) or on_bridge(q_[0], q_[1], q_[2])): run_.append(q_); continue
            if len(run_) > 1: lines_out[kk].append(run_)
            run_ = []
# hradby a opěrné zdi (útesy): [x, y, pata, koruna, hradba 0/1] po 2 m; pata a koruna z terénu 6 m po obou stranách
lines_out['cliff'] = []
for l, city, diff in CLIFFS:
    for q in lines(l.intersection(AREA)):
        if q.length < 1: continue
        q = q.segmentize(2.0); P_ = np.array(q.coords)[:, :2]
        d_ = np.gradient(P_, axis=0) if len(P_) > 1 else np.array([[1.0, 0.0]]); n_ = np.stack([-d_[:, 1], d_[:, 0]], 1); n_ /= np.linalg.norm(n_, axis=1, keepdims=True) + 1e-9
        za, zb = ground(*(P_ + n_ * 6).T), ground(*(P_ - n_ * 6).T)
        lo, hi = np.minimum(za, zb), np.maximum(za, zb)
        top = hi + (1.1 if city else 0.6)
        lines_out['cliff'].append([[round(x, 2), round(y, 2), round(float(a), 2), round(float(b), 2), int(city)] for (x, y), a, b in zip(P_, lo, top)])
if os.environ.get('IZO_PLACHTA') == '1' and os.path.exists('assets/plachta_studie.json'):      # okolí sídliště Plachta: lampy, lavičky, koše, zastávky, značky, auta na parkovištích
    for _k, _lst in (_PS.get('props') or {}).items():
        if _k == 'lamp': continue                                   # lampy se přidají až po úpravách z pasportu (viz světelná mapa)
        props.setdefault(_k, [])
        for _la, _lo, _a in _lst:
            _x, _y = (float(v) for v in to_local(_lo, _la))
            if AREA.contains(Point(_x, _y)): props[_k].append([_x, _y, float(ground(_x, _y)), _a])
    for _la, _lo, _a, _ci in _PS.get('auta') or []:
        _x, _y = (float(v) for v in to_local(_lo, _la))
        if AREA.contains(Point(_x, _y)): cars.append((_x, _y, _a, _ci))
# přístřešky zastávek, které stojí ve vozovce (poloha zastávky z dat leží na ose silnice), posunout na chodník vedle (hlášení z mapy)
for _s in props['shelter']:
    _q = Point(_s[0], _s[1])
    for _k in drive_tree.query(_q.buffer(10)):
        _l, _w, _c = drive_lines[int(_k)][:3]
        if _c == 'service' or _l.distance(_q) >= _w / 2 + 0.8: continue
        _n = shapely.ops.nearest_points(_l, _q)[0]; _v = np.array([_q.x - _n.x, _q.y - _n.y]); _d = float(np.hypot(*_v))
        if _d < 1e-3:
            _a = _l.project(_n); _p2 = _l.interpolate(min(_l.length, _a + 1.0)); _p1 = _l.interpolate(max(0.0, _a - 1.0))
            _v = np.array([-(_p2.y - _p1.y), _p2.x - _p1.x]); _d = float(np.hypot(*_v)) or 1.0
        _v = _v / _d; _s[0] = float(_n.x + _v[0] * (_w / 2 + 1.7)); _s[1] = float(_n.y + _v[1] * (_w / 2 + 1.7)); _s[2] = float(ground(_s[0], _s[1]))
        break
for k in props: props[k] = [[round(v, 3) for v in q] for q in props[k]]
cars = [[round(x, 2), round(y, 2), round(float(ground(x, y)), 2), round(a, 3), ci] for x, y, a, ci in cars]
cars += [[round(x, 2), round(y, 2), round(z, 2), round(a, 3), ci] for x, y, z, a, ci in ROOF_CARS if AREA.contains(Point(x, y))]   # parkoviště na střechách
buses = []
for a, e, k in UP['buses']:
    x1, y1 = to_local(a[1], a[0]); x2, y2 = to_local(e[1], e[0]); x, y = (x1 + x2) / 2, (y1 + y2) / 2
    if AREA.contains(Point(x, y)): buses.append([round(x, 2), round(y, 2), round(float(ground(x, y)), 2), round(math.atan2(y2 - y1, x2 - x1), 3), k])
portals = [[round(x, 2), round(y, 2), round(float(ground(x, y)), 2), round(a, 3), hw] for x, y, a, hw in portals if AREA.contains(Point(x, y))]
if os.path.exists('assets/potrubi.json'):         # nadzemní potrubí (nastroje/kominy.py)
    lines_out['pipe'] = []
    _skp = [Point(*to_local(lo, la)) for la, lo in UP.get('skryt_potrubi', [])]   # potrubí, které v datech vede nad zemí, ale ve skutečnosti ne
    for q in json.load(open('assets/potrubi.json')):
        _ln = LineString([to_local(lo, la) for la, lo in q])
        if any(_ln.distance(p_) < 10 for p_ in _skp): continue
        for l in lines(_ln.intersection(EXT)):
            xy_ = shapely.get_coordinates(shapely.segmentize(l, 10.0))
            lines_out['pipe'].append([[round(float(x), 2), round(float(y), 2), round(float(zz), 2)] for (x, y), zz in zip(xy_, ground(xy_[:, 0], xy_[:, 1]))])
print({k: len(v) for k, v in props.items()}, 'aut', len(cars), {k: len(v) for k, v in lines_out.items()})

# ---------------- stromy ----------------
import scipy.ndimage as _ndi13
_mx13 = _ndi13.maximum_filter(np.asarray(bmask), size=13)       # totéž co ImageFilter.MaxFilter(13) (ověřeno, včetně okrajů): 25 s -> <1 s
excl = np.maximum(np.asarray(notree), _mx13)


def free(x, y):
    px_, py_ = pix(x, y)
    return 0 <= px_ < TWE and 0 <= py_ < TWE and excl[py_, px_] == 0


def free_v(xs, ys):
    px_ = ((xs + HE) / TEX_RES).astype(int); py_ = ((HE - ys) / TEX_RES).astype(int)
    ok = (px_ >= 0) & (px_ < TWE) & (py_ >= 0) & (py_ < TWE)
    out = np.zeros(len(xs), bool)
    out[ok] = excl[py_[ok], px_[ok]] == 0
    return out


trees = []


def scatter(g, spacing, conifer, hmin, hmax, kind=0):
    """stromy na světové mřížce s náhodným posunem podle indexu buňky -> sousední čtverce mají stejné stromy"""
    sid = int(round(spacing * 10))
    for p in polys(g.intersection(EXT)):
        minx, miny, maxx, maxy = p.bounds
        kx = np.arange(math.floor((minx + CX) / spacing), math.ceil((maxx + CX) / spacing) + 1)
        ky = np.arange(math.floor((miny + CY) / spacing), math.ceil((maxy + CY) / spacing) + 1)
        KX, KY = [a.ravel() for a in np.meshgrid(kx, ky)]
        tx = KX * spacing - CX + (ihash(KX, KY, sid, 1) - 0.5) * 0.9 * spacing
        ty = KY * spacing - CY + (ihash(KX, KY, sid, 2) - 0.5) * 0.9 * spacing
        m = shapely.contains_xy(p, tx, ty)
        m[m] = free_v(tx[m], ty[m])
        hh = hmin + ihash(KX, KY, sid, 3) * (hmax - hmin)
        cf = ihash(KX, KY, sid, 4) < conifer
        for i in np.nonzero(m)[0]:
            trees.append((float(tx[i]), float(ty[i]), float(hh[i]), 1 if cf[i] else 0, kind))


for _, r in land.iterrows():
    c = r['class']; g = r.geom
    if c in ('forest', 'wood') and g.geom_type != 'Point': scatter(g, 4.2, 0.55, 12, 24)
    elif c in ('scrub', 'shrub') and g.geom_type != 'Point': scatter(g, 5, 0.1, 2, 4, 1)
    elif c == 'tree' and g.geom_type == 'Point':
        if EXT_P.contains(g): trees.append((g.x, g.y, 8 + h01('t' + wkey(g.x, g.y)) * 8, 0, 0))
    elif c == 'tree_row':
        for l in lines(g):
            d = 0
            while d < l.length:
                q = l.interpolate(d)
                if EXT_P.contains(q): trees.append((q.x, q.y, 8 + h01('r' + wkey(q.x, q.y)) * 6, 0, 0))
                d += 7
DENS = {'park': 11, 'cemetery': 9, 'residential': 16, 'garden': 12, 'grass': 20, 'village_green': 18,
        'recreation_ground': 20, 'allotments': 14, 'kindergarten': 14}
for _, r in lu.iterrows():
    s = DENS.get(r['class']) or (DENS['park'] if r.id in _PARK_Z else None)
    if s: scatter(r.geom, s, 0.25, 6, 15)
# řídké stromy všude kromě luk, polí a pastvin (tam ve skutečnosti stromy nejsou)
OPEN = shapely.unary_union([g for c, g in zip(lu['class'], lu.geom) if c in ('meadow', 'farmland', 'grass', 'village_green', 'downhill', 'pitch')]
                           + [g for c, g in zip(land['class'], land.geom) if c in ('grassland', 'meadow') and g.geom_type != 'Point'] + ZTTP + [g for g, _ in ZORNA])
scatter(EXT.difference(OPEN.buffer(0)) if not OPEN.is_empty else EXT, 26, 0.3, 6, 14)
if LESM is not None:                         # strom jen tam, kde je na ortofotu koruna; v zahradách a zástavbě pár řídkých i bez ní
    _sp = shapely.prepared.prep(shapely.unary_union(ZSAD + [r.geom for _, r in lu.iterrows() if r['class'] in ('residential', 'garden', 'allotments')]).buffer(0)
                                  .difference(shapely.unary_union([g for g, _ in ZORNA] + ZTTP).buffer(0)))
    def _ok(t):
        px_, py_ = pix(t[0], t[1])
        if not (0 <= px_ < TWE and 0 <= py_ < TWE) or LESM[py_, px_]: return True
        return h01('z' + wkey(t[0], t[1])) < 0.3 and _sp.contains(Point(t[0], t[1]))
    trees = [t for t in trees if _ok(t)]
for _o in OBL.values():                      # oblast podle skutečnosti: náhodné stromy pryč, místo nich změřené
    if _o.get('skryt'): continue
    _q = shapely.prepared.prep(Polygon([to_local(lo, la) for la, lo in _o['poly']]))
    trees = [t for t in trees if not _q.contains(Point(t[0], t[1]))]
    for la, lo, hh, con in _o['trees']:
        x, y = (float(v) for v in to_local(lo, la))
        if EXT_P.contains(Point(x, y)) and free(x, y): trees.insert(0, (x, y, hh, con, 0))
seen = set(); T = []
for t in trees:
    k = (round((t[0] + CX) / 3.0), round((t[1] + CY) / 3.0))
    if k in seen: continue
    seen.add(k); T.append(t)
for _o in OBL.values():                      # "skryt": změřené stromy na konec a původní jen skrýt (kind = 2), barvy ostatních stromů závisí na pořadí
    if not _o.get('skryt'): continue
    _q = shapely.prepared.prep(Polygon([to_local(lo, la) for la, lo in _o['poly']]))
    T = [t[:4] + (2,) if _q.contains(Point(t[0], t[1])) else t for t in T]
    for la, lo, hh, con in _o['trees']:
        x, y = (float(v) for v in to_local(lo, la))
        if EXT_P.contains(Point(x, y)): T.append((x, y, hh, con, 0))
# koruna nesmí sahat do vozovky, kudy jezdí auta (jinak auta „projíždějí stromy“): strom pryč, když je střed blíž než
# půl šířky silnice + poloměr koruny (listnatý ~0,33 h, jehličnan ~0,2 h). Platí i pro mostovky a nájezdy.
_drv = [(l, w) for _a, l, c, w, _n in roads if c in DRIVE and c != 'service'] + [(D[0], D[4]) for D in DECKS if D[6] in DRIVE and D[6] != 'service']
if _drv:
    _dt = shapely.STRtree([l for l, _w in _drv]); _n0 = len(T)
    def _clear(t):
        r_ = t[2] * (0.2 if t[3] else 0.33); P_ = Point(t[0], t[1])
        for k in _dt.query(P_.buffer(r_ + 8)):
            l_, w_ = _drv[k]
            if l_.distance(P_) < w_ / 2 + r_: return False
        return True
    T = [t for t in T if _clear(t)]
    print('stromů nad vozovkou odstraněno', _n0 - len(T))
tz = ground(np.array([t[0] for t in T]), np.array([t[1] for t in T]))
trees = [[round(t[0], 2), round(t[1], 2), round(float(z), 2), round(t[2], 1), t[3], t[4]] for t, z in zip(T, tz)]
print('stromů', len(trees))

# ---------------- hřbitovy: hroby, náhrobky, sochy ----------------
_cem_cfg = UP.get('cemetery', {})
cem_union = shapely.unary_union([r.geom for _, r in lu.iterrows() if r['class'] == 'cemetery'])
cem_prep = shapely.prepared.prep(cem_union)
# skryté stromy zůstávají v seznamu (kind = 2), aby se v rendereru neposunulo pořadí náhodných barev
# na hřbitovech prořídit stromy (výchozí 70 % skrýt), aby byly vidět hroby
trees = [t[:5] + [2] if cem_prep.contains(Point(t[0], t[1])) and h01(wkey(t[0], t[1])) >= _cem_cfg.get('tree_keep', 0.3) else t for t in trees]
nograve = shapely.geometry.GeometryCollection()
_hook('cemetery')
trees = [t for t in trees if EXT_P.contains(Point(t[0], t[1]))]
print('skrytých stromů na hřbitovech', sum(t[5] == 2 for t in trees))
grng = random.Random(7)
graves, statues = [], []
tree_pts = shapely.STRtree([Point(t[0], t[1]) for t in trees if t[5] != 2])
blockers = shapely.unary_union([l.buffer(w / 2 + 0.9) for l, w, c, n in all_lines]
                               + [shapely.geometry.Polygon(b['p']).buffer(1.5) for b in buildings]
                               + [l.buffer(1.2) for _, r in inf.iterrows() if r['class'] in ('wall', 'fence') for l in lines(r.geom)])
for _, r in lu.iterrows():
    if r['class'] != 'cemetery': continue
    for p in polys(r.geom.intersection(AREA)):
        inner = p.buffer(_cem_cfg.get('margin', -1.5))
        if inner.is_empty: continue
        pp = shapely.prepared.prep(inner.difference(blockers).difference(nograve.buffer(1.0)))
        o = p.minimum_rotated_rectangle
        oc = [np.array(q) for q in list(o.exterior.coords)[:4]]
        e1, e2 = oc[1] - oc[0], oc[3] - oc[0]
        if np.linalg.norm(e1) < np.linalg.norm(e2): e1, e2 = e2, e1; oc = [oc[0], oc[3], oc[2], oc[1]]
        L, W = np.linalg.norm(e1), np.linalg.norm(e2)
        u, v = e1 / L, e2 / W
        ang = math.atan2(v[1], v[0])                    # hrob leží podél kratší osy hřbitova
        jewish = 'Žid' in (sname(r) or '')
        row = _cem_cfg.get('row0', 1.0)
        while row + 2.2 < W:
            col = _cem_cfg.get('col0', 0.8)
            while col + 1.0 < L:
                c0 = oc[0] + u * (col + 0.5) + v * (row + 1.0)
                corners = [oc[0] + u * (col + a) + v * (row + b) for a, b in ((0, 0), (1.0, 0), (1.0, 2.0), (0, 2.0))]
                if all(pp.contains(Point(*q)) for q in corners) and grng.random() < _cem_cfg.get('prob', 0.75 if jewish else 0.9):
                    near = tree_pts.query(Point(*c0).buffer(_cem_cfg.get('tree_dist', 1.6)))
                    if len(near) == 0:
                        if not jewish: cd.polygon(P([tuple(q) for q in corners]), fill=C['grave'])
                        head = oc[0] + u * (col + 0.5) + v * (row + 1.9)
                        graves.append([round(float(head[0]), 2), round(float(head[1]), 2), round(float(ground(*head)), 2),
                                       round(ang, 3), round(grng.uniform(0.55, 1.15) if not jewish else grng.uniform(0.5, 0.9), 2), grng.randrange(4)])
                col += _cem_cfg.get('dcol', 1.45)
            row += _cem_cfg.get('drow', 3.1)
for _, r in inf.iterrows():
    g = r.geom
    if r['class'] == 'artwork' and g.geom_type == 'Point' and AREA.contains(g):
        if any(r2['class'] == 'cemetery' and r2.geom.buffer(3).contains(g) for _, r2 in lu.iterrows()):
            statues.append([round(g.x, 2), round(g.y, 2), round(float(ground(g.x, g.y)), 2), 0.0])
props['planter'] = props['slab'] = props['pavilion'] = props['shed'] = []
props['grave'] = graves
props['statue'] = statues
props['wheelie'] = [[round(v, 3) for v in q] for q in props['wheelie']]
_hook('props')
print('hrobů', len(graves), 'soch', len(statues))

# ---------------- textury podle ročního období ----------------
SEASON_PAL = {
    'summer': {'grass': (106, 160, 74), 'garden': (118, 168, 80), 'park': (104, 164, 72), 'meadow': (140, 172, 86),
               'forest': (66, 112, 56), 'scrub': (92, 128, 62), 'pitch': (80, 156, 72), 'track': (178, 92, 72),
               'sand': (214, 192, 138), 'paved': (196, 186, 160), 'industrial': (156, 152, 142), 'parking': (120, 120, 124),
               'road': (92, 92, 98), 'marking': (236, 232, 214), 'curb': (176, 172, 162), 'dirt': (170, 146, 102),
               'water': (64, 124, 190), 'pool': (92, 196, 230), 'stream': (72, 132, 196), 'rail': (88, 84, 82),
               'cemetery': (88, 132, 70), 'wetland': (100, 146, 92), 'rock': (150, 146, 136), 'construction': (164, 132, 96),
               'footway': (214, 206, 186), 'pool_edge': (236, 240, 240), 'farmland': (168, 172, 96), 'cobble': (200, 188, 164), 'grave': (156, 152, 144), 'manhole': (66, 66, 70),
               'court_blue': (70, 112, 170), 'zone': (255, 0, 220), 'zone2': (0, 230, 230),
               'piste': (150, 178, 92), 'skijump': (98, 160, 150),
               'wheat': (214, 186, 106), 'wheat2': (194, 162, 86), 'rape': (150, 148, 82), 'rape2': (128, 126, 70),
               'maize': (80, 134, 58), 'maize2': (58, 106, 44), 'soil': (110, 142, 66), 'soil2': (128, 104, 70),
               'plaza': (186, 186, 184), 'plaza2': (206, 206, 200), 'deck': (146, 104, 88), 'ballast': (150, 138, 116)},
}
sp = dict(SEASON_PAL['summer'])
sp.update({'grass': (122, 176, 80), 'garden': (132, 184, 86), 'park': (118, 180, 78), 'meadow': (150, 188, 90),
           'forest': (78, 128, 62), 'farmland': (132, 150, 90),
           'wheat': (104, 146, 72), 'wheat2': (88, 128, 62), 'rape': (238, 214, 60), 'rape2': (216, 194, 50),
           'maize': (138, 106, 74), 'maize2': (112, 86, 60), 'soil': (130, 98, 68), 'soil2': (106, 80, 56)})
SEASON_PAL['spring'] = sp
au = dict(SEASON_PAL['summer'])
au.update({'grass': (122, 154, 72), 'garden': (128, 158, 76), 'park': (120, 156, 70), 'meadow': (156, 160, 88),
           'forest': (92, 104, 58), 'scrub': (124, 116, 64), 'farmland': (176, 150, 96), 'cemetery': (104, 128, 70),
           'wheat': (204, 182, 126), 'wheat2': (164, 132, 88), 'rape': (112, 150, 74), 'rape2': (98, 134, 64),
           'maize': (152, 126, 86), 'maize2': (124, 98, 66), 'soil': (122, 92, 62), 'soil2': (98, 72, 50)})
SEASON_PAL['autumn'] = au
wi = dict(SEASON_PAL['summer'])
snow = (234, 239, 246)
wi.update({k: snow for k in ('grass', 'garden', 'park', 'meadow', 'pitch', 'sand', 'cemetery', 'farmland', 'construction', 'wetland', 'track', 'rock', 'piste', 'skijump',
                             'wheat', 'rape', 'maize', 'soil')})
wi.update({k: (212, 218, 228) for k in ('wheat2', 'rape2', 'maize2', 'soil2')})             # brázdy prosvítají sněhem
wi.update({'forest': (214, 222, 232), 'scrub': (220, 226, 234), 'paved': (222, 226, 232), 'industrial': (206, 210, 216),
           'parking': (176, 180, 188), 'road': (104, 106, 114), 'marking': (190, 192, 196), 'curb': (226, 230, 236),
           'dirt': (214, 214, 218), 'water': (186, 210, 228), 'pool': (150, 168, 184), 'stream': (58, 96, 136),
           'footway': (226, 230, 236), 'cobble': (206, 210, 218), 'pool_edge': (230, 234, 238), 'grave': (222, 226, 232), 'manhole': (90, 92, 98)})
wi.update({'plaza': (208, 212, 220), 'plaza2': (222, 226, 232), 'deck': (176, 160, 160), 'ballast': (212, 214, 220)})
SEASON_PAL['winter'] = wi

# letiště (assets/doplnky/letiste.json, doplněk „letiste“): posekané travnaté dráhy s pásy po sečení a bílými okrajovými
# značkami, betonová odstavná plocha ("odstavna") a asfaltová pojížděcí dráha ("pojizdeni"); body jsou [lat, lon]
if os.path.exists('assets/doplnky/letiste.json'):
    _L = json.load(open('assets/doplnky/letiste.json', encoding='utf-8'))
    LL = lambda q: to_local(q[1], q[0])
    for dr in _L.get('drahy', []):
        (ax, ay), (bx, by) = LL(dr['a']), LL(dr['b']); L_ = math.hypot(bx - ax, by - ay); ux, uy = (bx - ax) / L_, (by - ay) / L_
        nx_, ny_ = -uy, ux; w_ = dr.get('sirka', 24)
        Q = lambda s, t: (ax + ux * s + nx_ * t, ay + uy * s + ny_ * t)
        if not Polygon([Q(0, -w_ / 2), Q(L_, -w_ / 2), Q(L_, w_ / 2), Q(0, w_ / 2)]).intersects(DRAWBOX): continue
        if dr.get('povrch', 'trava') != 'trava':                 # zpevněná dráha: asfalt s bílou osou
            fill(Polygon([Q(0, -w_ / 2), Q(L_, -w_ / 2), Q(L_, w_ / 2), Q(0, w_ / 2)]), C['road'], block=True)
            line(LineString([Q(30, 0), Q(L_ - 30, 0)]), C['marking'], 0.6); continue
        fill(Polygon([Q(0, -w_ / 2), Q(L_, -w_ / 2), Q(L_, w_ / 2), Q(0, w_ / 2)]), C['park'], block=True)
        for k in range(1, int(w_ // 4), 2):                   # pásy po sečení podél dráhy
            fill(Polygon([Q(0, -w_ / 2 + k * 4), Q(L_, -w_ / 2 + k * 4), Q(L_, -w_ / 2 + k * 4 + 4), Q(0, -w_ / 2 + k * 4 + 4)]), C['pitch'], block=True)
        s_ = 0.0
        while s_ <= L_:                                        # okrajové značky (bílé desky) po 60 m
            for t_ in (-w_ / 2, w_ / 2):
                fill(Polygon([Q(s_ - 1.2, t_ - 0.6), Q(s_ + 1.2, t_ - 0.6), Q(s_ + 1.2, t_ + 0.6), Q(s_ - 1.2, t_ + 0.6)]), C['marking'])
            s_ += 60.0
        for s_ in (1.5, L_ - 1.5):                             # prahy: příčná řada značek
            for t_ in range(-int(w_ / 2) + 3, int(w_ / 2) - 2, 5):
                fill(Polygon([Q(s_ - 0.6, t_ - 1.2), Q(s_ + 0.6, t_ - 1.2), Q(s_ + 0.6, t_ + 1.2), Q(s_ - 0.6, t_ + 1.2)]), C['marking'])
    if _L.get('odstavna'): fill(Polygon([LL(q) for q in _L['odstavna']]), C['industrial'], block=True)
    if _L.get('pojizdeni'): line(LineString([LL(q) for q in _L['pojizdeni']]), C['road'], 9.0, block=True)

# kontrolní ohraničení zón upřesněných podle snímků (geo.SAT_OUTLINE, po kontrole vypnout)
if getattr(geo, 'SAT_OUTLINE', False):
    for fine, col in ((False, C['zone2']), (True, C['zone'])):     # tyrkys = jen barvy, purpur = barvy i typy střech
        zs = [Polygon(list(zip(*to_local(*np.array(z['ring']).T)))) for z in SAT['zones'] if bool(z.get('fine')) == fine]
        if not zs: continue
        for zp in polys(shapely.unary_union(zs)):
            cd.line(P(list(zp.exterior.coords)), fill=col, width=max(1, round(3.0 / TEX_RES)))
cls_a = np.asarray(cls)[MPX:MPX + TW, MPX:MPX + TW]     # textura jen vlastního čtverce
noise = np.random.default_rng(1).random((TW, TW), dtype=np.float32)
noise2 = np.random.default_rng(2).random((TW, TW), dtype=np.float32)
NATURAL = [C[k] for k in ('grass', 'garden', 'park', 'meadow', 'forest', 'scrub', 'cemetery', 'wetland', 'farmland',
                          'wheat', 'wheat2', 'rape', 'rape2', 'maize', 'maize2', 'soil', 'soil2')]
nat = np.isin(cls_a, NATURAL)
for season, pal in SEASON_PAL.items():
    lut = np.zeros((256, 3), np.uint8)
    for k, v in C.items(): lut[v] = pal[k]
    img = lut[cls_a].astype(np.int16)
    # pixel-art zrnitost trávy / sněhu
    dark = nat & (noise > 0.93); light = nat & (noise < 0.05)
    img[dark] -= 14 if season != 'winter' else 10
    img[light] += 14 if season != 'winter' else 6
    if season == 'spring':   # pampelišky a sedmikrásky
        img[nat & (noise2 < 0.006)] = (240, 214, 70)
        img[nat & (noise2 > 0.995)] = (246, 246, 240)
    if season == 'autumn':   # spadané listí
        img[nat & (noise2 < 0.006)] = (196, 120, 46)
        img[nat & (noise2 > 0.997)] = (170, 74, 40)
    if season == 'winter':   # sníh i na okrajích silnic
        road = cls_a == C['road']
        edge = road & (noise2 < 0.06)
        img[edge] = (200, 204, 212)
    asph = np.isin(cls_a, [C['road'], C['parking']])
    img[asph & (noise > 0.97)] += 8
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(f'{OUT}/ground_{season}.png', compress_level=1)   # mezisoubor pro render: slabší komprese = rychlejší zápis
    print('textura', season)

if os.environ.get('IZO_PLACHTA') == '1' and os.path.exists('assets/plachta_studie.json'):      # lampy sídliště (po filtru pasportu, aby je nesmazal)
    for _la, _lo, _a in (_PS.get('props') or {}).get('lamp', []):
        _x, _y = (float(v) for v in to_local(_lo, _la))
        if AREA.contains(Point(_x, _y)): props['lamp'].append([round(_x, 3), round(_y, 3), round(float(ground(_x, _y)), 3), _a])
# světelná mapa pro noc (kužely světla lamp na zemi), 0,5 m/px
LR = 0.5; LW = int(2 * HALF / LR)
lm_img = np.zeros((LW, LW), np.float32)
R = 14
yy, xx = np.mgrid[-R * 2:R * 2 + 1, -R * 2:R * 2 + 1]
blob = np.clip(1 - np.hypot(xx, yy) / (R * 2), 0, 1) ** 1.6
for x, y, *_r in props['lamp']:
    cx, cy = int((x + HALF) / LR), int((HALF - y) / LR)
    x0, y0 = cx - R * 2, cy - R * 2
    xs0, ys0 = max(0, x0), max(0, y0); xs1, ys1 = min(LW, x0 + blob.shape[1]), min(LW, y0 + blob.shape[0])
    if xs1 <= xs0 or ys1 <= ys0: continue
    lm_img[ys0:ys1, xs0:xs1] += blob[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]
Image.fromarray((np.clip(lm_img, 0, 1) * 255).astype(np.uint8)).save(f'{OUT}/lightmap.png')

# stáda zvířat na pastvinách (assets/upresneni.json -> stada)
herds_out = []
for h in UP.get('stada', UP.get('herds', [])):
    typ_raw = str(h.get('typ', h.get('type', 'cow'))).lower()
    typ = 'horse' if any(k in typ_raw for k in ('kun', 'kone', 'horse')) else 'deer' if any(k in typ_raw for k in ('srn', 'deer')) else 'cow'
    hx, hy = to_local(float(h['lon']), float(h['lat']))
    hr = float(h.get('radius', 30.0))
    hpt = Point(hx, hy)
    if EXT_P.contains(hpt) or hpt.buffer(hr).intersects(EXT):
        hz = float(ground(hx, hy))
        if not free(hx, hy):
            cand = [(hx + math.cos(a) * d, hy + math.sin(a) * d) for d in np.linspace(3, hr, 8) for a in np.linspace(0, math.tau, 12)]
            good = [p for p in cand if free(*p)]
            if good:
                hx, hy = min(good, key=lambda p: math.hypot(p[0] - hx, p[1] - hy))
                hz = float(ground(hx, hy))
        herds_out.append({
            'typ': typ, 'x': round(hx, 2), 'y': round(hy, 2), 'z': round(hz, 2),
            'n': int(h.get('pocet', h.get('count', 8))),
            'r': round(hr, 1),
            'mladata': bool(h.get('mladata', True))
        })

# vánoční stromy a kluziště (mesto.json "vanocni_strom", "kluziste"): v zimním renderu jako 3D stavba, prohlížeč nad ně kreslí
# jen blikající světýlka a bruslaře. Do scény patří i v pásu sousedů (kvůli švům a stínům).
_vs_ = geo.MESTO.get('vanocni_strom') or []
if _vs_ and not isinstance(_vs_[0], list): _vs_ = [_vs_]
xmas = []
for _la, _lo in _vs_:
    _x, _y = to_local(_lo, _la)
    if AREA.contains(Point(_x, _y)): xmas.append([round(float(_x), 2), round(float(_y), 2), round(float(ground(_x, _y)), 2)])
rinks = []
for _k in geo.MESTO.get('kluziste') or []:
    _x, _y = to_local(_k['lon'], _k['lat']); _a = math.radians(_k.get('a', 0)); _L, _W = _k.get('d', 40), _k.get('s', 20)
    if not AREA.contains(Point(_x, _y)): continue
    _zs = [float(ground(_x + math.cos(_a) * i * _L / 2 - math.sin(_a) * j * _W / 2, _y + math.sin(_a) * i * _L / 2 + math.cos(_a) * j * _W / 2)) for i in (-1, 0, 1) for j in (-1, 0, 1)]
    rinks.append([round(float(_x), 2), round(float(_y), 2), round(min(_zs), 2), round(max(_zs), 2), round(_a, 4), _L, _W])
# vánoční stánky (mesto.json "vanocni_stanky": [{lat, lon: střed řady, a: směr řady ve ° od východu, n: počet, w: šířka stánku m, m: mezera m}]),
# pult je na pravé straně od směru řady (lokální −t); jen v zimním renderu
stalls = []
for _k in geo.MESTO.get('vanocni_stanky') or []:
    _x, _y = to_local(_k['lon'], _k['lat']); _a = math.radians(_k.get('a', 0)); _n, _w, _m = _k.get('n', 5), _k.get('w', 3.0), _k.get('m', 1.2)
    for _i in range(_n):
        _s = (_i - (_n - 1) / 2) * (_w + _m); _sx, _sy = _x + math.cos(_a) * _s, _y + math.sin(_a) * _s
        if AREA.contains(Point(_sx, _sy)): stalls.append([round(float(_sx), 2), round(float(_sy), 2), round(float(ground(_sx, _sy)), 2), round(_a, 4), _w, _i])
TOP = max([b['e'] + b['rh'] for b in buildings] + [t[2] + t[3] for t in trees] + [float(H.max())])
json.dump({'chunk': CHUNK, 'center': [CX, CY], 'half': HALF, 'step': STEP, 'n': N, 'hmin': HMIN, 'heights': [round(float(v), 2) for v in H.ravel()],
           'ms': MS, 'hext': [round(float(v), 2) for v in HX.ravel()], 'nb': NB, 'margin': geo.MARGIN, 'skirt': geo.skirt_edges(CHUNK),
           'floor': geo.FLOOR, 'top': round(TOP, 1),
           'buildings': buildings, 'trees': trees, 'props': props, 'cars': cars, 'buses': buses, 'portals': portals, 'lines': lines_out,
           'herds': herds_out, 'koleje': KOLEJE,
           'xmas': xmas, 'rinks': rinks, 'stalls': stalls,
           'play': [[round(float(x), 2), round(float(y), 2), round(float(ground(x, y)), 2), round(a, 3), t] for x, y, a, t in play],
           'bridges': [{'p': run, 'w': D[4], 'k': D[5], 'c': D[6], 'wtr': D[8] if len(D) > 8 else 0} for D in DECKS if D[0].intersects(EXT)
                       for run in deck_runs([[*q, round(float(g_), 2)] for q, g_ in zip(deck_line(D), D[3])])]},
          open(f'{OUT}/scene.json', 'w'), separators=(',', ':'))

# podklady pro interaktivní vrstvu prohlížeče
streets = {}
for l, w, c, n in all_lines:
    if n:
        streets.setdefault(n, []).append(l)
street_out = []
for n, ls in streets.items():
    m = shapely.MultiLineString(ls).intersection(AREA)
    if m.is_empty: continue
    pt = m.interpolate(0.5, normalized=True) if m.geom_type == 'LineString' else max(lines(m), key=lambda q: q.length).interpolate(0.5, normalized=True)
    street_out.append({'name': n, 'x': round(pt.x, 1), 'y': round(pt.y, 1), 'z': round(float(ground(pt.x, pt.y)), 1)})
# jednosměrky pro auta: +1 = jen ve směru geometrie, -1 = jen proti němu
def _none(v):
    """prázdná hodnota z Overture: None, prázdný seznam nebo prázdné numpy pole (`not pole` s víc prvky spadne)"""
    return v is None or (not isinstance(v, str) and hasattr(v, '__len__') and len(v) == 0)
def _oneway(r):
    acc = r.get('access_restrictions')
    if acc is None or isinstance(acc, float): return 0
    for a in acc:
        w_ = a.get('when') or {}
        if a.get('access_type') == 'denied' and a.get('between') is None and _none(w_.get('mode')) and _none(w_.get('using')) and _none(w_.get('recognized')):
            if w_.get('heading') == 'backward': return 1
            if w_.get('heading') == 'forward': return -1
    return 0
_ow = [(l, _oneway(r), r['class']) for _, r in seg.iterrows() if r['class'] in DRIVE and r['class'] != 'service' for l in lines(r.geom)]
_ow += [(l, _oneway(r), r['class']) for g_, r in _bridge_raw if r['class'] in DRIVE and r['class'] != 'service' for l in lines(g_)]   # mosty jsou ze seg vyčleněné: bez tohohle by mostovka dvouproudé silnice byla obousměrná
# intenzita dopravy ze sčítání ŘSD ("doprava" v mesto.json, data z nastroje/scitani.py): vozidla za 24 h podle čísla silnice
_cfg = geo.MESTO.get('doprava')
_sv = {}
if _cfg:
    _useky = _cfg.get('useky', {})
    for s_ in json.load(open('build/scitani.json', encoding='utf-8')):
        chosen = s_['usek'] in _useky[s_['sil']] if s_['sil'] in _useky else s_['kraj'] == _cfg['kraj']
        if chosen: _sv.setdefault(s_['sil'], []).append((s_['sv'], s_['nak']))
    _nak = {k: round(100 * sum(n for _s, n in v) / max(1, sum(s for s, _n in v)), 1) for k, v in _sv.items()}   # % nákladních aut
    _sv = {k: float(np.median([s for s, _n in v])) for k, v in _sv.items()}
_V_CLASS = {'trunk': 10000, 'primary': 8000, 'secondary': 3000, 'tertiary': 1500, 'unclassified': 400, 'residential': 300, 'living_street': 100}   # silnice bez sčítání: odhad
def _intensity(r):
    routes = r.get('routes')
    for x in (routes if routes is not None and not isinstance(routes, float) else []):
        ref = str(x.get('ref') or '').replace(' ', '')
        if ref in _sv: return _sv[ref], _nak[ref], True
    return _V_CLASS.get(r['class'], 300), 0, False
# rampy (subclass link) mají v datech třídu silnice, na kterou vedou -> jen zlomek aut; kusy hlavní silnice bez čísla
# dostanou medián sčítaných kusů stejné třídy v tomto čtverci (jinak by průtah měl místy 10 000 a místy 25 000 aut)
_v = []
if _cfg:
    for _, r in seg.iterrows():
        if r['class'] not in DRIVE or r['class'] == 'service': continue
        lk_ = r.get('subclass') == 'link'
        for l in lines(r.geom): _v.append([l, *_intensity(r), lk_, r['class']])
    for c_ in {q[5] for q in _v}:
        ok_ = [q for q in _v if q[5] == c_ and q[3] and not q[4]]
        if ok_:
            med_, nak_ = float(np.median([q[1] for q in ok_])), float(np.median([q[2] for q in ok_]))
            for q in _v:
                if q[5] == c_ and not q[3] and not q[4]: q[1], q[2] = med_, nak_
    for q in _v:
        if q[4]: q[1] = q[1] * 0.2
_v_tree = shapely.STRtree([q[0] for q in _v]) if _v else None
def piece_intensity(l, c):
    """(vozidla za 24 h, % nákladních, rampa); přednost má kus stejné třídy, ať most nepřevezme intenzitu silnice pod sebou"""
    m_ = l.interpolate(0.5, normalized=True)
    near = list(_v_tree.query(m_.buffer(3.0)))
    same = [k for k in near if _v[k][5] == c] or near
    if not same: return None, 0, False
    q = _v[min(same, key=lambda k: _v[k][0].distance(m_))]
    return q[1], q[2], q[4]
# kruhové objezdy data často jednosměrné nemají: malý kruhový prstenec krátkých úseků, doprava proti směru hodinových ručiček
_short = [l for l, _o, _c in _ow if l.length < 60]
_ring_lines = []
for _poly in shapely.ops.polygonize(shapely.ops.unary_union(_short) if _short else []):
    if _poly.length < 250 and 4 * math.pi * _poly.area / _poly.length ** 2 > 0.85 and len(_poly.exterior.coords) >= 8:
        _ring_lines.append(shapely.geometry.polygon.orient(_poly, 1.0).exterior)
def _along(src, l):
    a_, b_ = src.project(l.interpolate(0.25, normalized=True)), src.project(l.interpolate(0.75, normalized=True))
    return 1 if b_ >= a_ else -1
_ow2 = []
for l, o, c in _ow:
    m_ = l.interpolate(0.5, normalized=True)
    for ring in _ring_lines:
        if l.length < 60 and ring.distance(m_) < 0.5 and ring.distance(Point(l.coords[0])) < 0.5 and ring.distance(Point(l.coords[-1])) < 0.5:
            o = _along(ring, l)
    if o: _ow2.append((l, o))
_ow_tree = shapely.STRtree([l for l, _o in _ow2])
def piece_oneway(l):
    """směr jednosměrky pro kus cesty (kus může být oříznutý nebo otočený proti zdroji)"""
    m_ = l.interpolate(0.5, normalized=True)
    for k in _ow_tree.query(m_.buffer(0.5)):
        src, o = _ow2[k]
        if src.distance(m_) < 0.5: return o * _along(src, l)
    return 0
# počet pruhů z OSM (nastroje/pruhy.py): [po směru kusu, proti směru], jen když je v některém směru víc než jeden pruh
_ln, _ln_tree = [], None
if os.path.exists('assets/pruhy.json'):
    for q in json.load(open('assets/pruhy.json')):
        x_, y_ = to_local([p_[1] for p_ in q['g']], [p_[0] for p_ in q['g']])
        _ln.append((LineString(list(zip(x_, y_))), q['f'], q['b']))
    _ln_tree = shapely.STRtree([l for l, _f, _b in _ln]) if _ln else None
def piece_lanes(l):
    if _ln_tree is None or l.length < 1: return None
    m_ = l.interpolate(0.5, normalized=True)
    a_, b_ = l.interpolate(max(0, l.length / 2 - 2)), l.interpolate(min(l.length, l.length / 2 + 2))
    dx, dy = b_.x - a_.x, b_.y - a_.y; d_ = math.hypot(dx, dy) or 1
    best = None
    for k in _ln_tree.query(m_.buffer(4.0)):
        src, f_, b2 = _ln[k]; dd = src.distance(m_)
        if dd > 4.0: continue
        s_ = src.project(m_); p0, p1 = src.interpolate(max(0, s_ - 2)), src.interpolate(min(src.length, s_ + 2))
        ex, ey = p1.x - p0.x, p1.y - p0.y; cs = (dx * ex + dy * ey) / (d_ * (math.hypot(ex, ey) or 1))
        if abs(cs) < 0.85: continue                # křížící se cesta
        if best is None or dd < best[0]: best = (dd, [f_, b2] if cs > 0 else [b2, f_])
    return best[1] if best else None
# rychlostní limity z dat (km/h): jen trvalé, bez podmínek
def _limit(r):
    sl = r.get('speed_limits')
    if sl is None or isinstance(sl, float): return 0
    for q in sl:
        m_ = q.get('max_speed')
        if m_ and not q.get('when') and q.get('between') is None and m_.get('unit') == 'km/h': return int(m_['value'])
    return 0
_sl = [(l, _limit(r)) for _, r in seg.iterrows() if r['class'] in DRIVE and _limit(r) for l in lines(r.geom)]
_sl_tree = shapely.STRtree([l for l, _q in _sl]) if _sl else None
def piece_limit(l):
    if _sl_tree is None: return 0
    m_ = l.interpolate(0.5, normalized=True)
    for k in _sl_tree.query(m_.buffer(0.5)):
        if _sl[k][0].distance(m_) < 0.5: return _sl[k][1]
    return 0
def _road(p3, l, c, n):
    o = {'p': p3, 'c': c, 'n': n}
    d_ = piece_oneway(l)
    if d_: o['o'] = d_
    lim = piece_limit(l)
    if lim: o['l'] = lim
    n_ = piece_lanes(l)
    if n_ and c != 'service':
        if d_: n_ = [n_[0], 0] if d_ > 0 else [0, n_[1]]       # jednosměrka: platí jen pruhy ve směru jízdy
        if max(n_) > 1: o['ln'] = n_                # 'n' je název ulice
    if _v_tree is not None and c != 'service':
        v_, t_, lk_ = piece_intensity(l, c)
        o['v'] = int(v_ or _V_CLASS.get(c, 300))
        if t_: o['t'] = t_
        if lk_: o['x'] = 1                    # rampa: pomaleji
    return o
graph = [_road([[round(x, 1), round(y, 1), round(float(z), 1)] for (x, y), z in zip(l.coords, ground(*np.array(l.coords).T))], l, c, n)
         for l0, w, c, n in drive_lines for l in lines(l0.intersection(AREA.intersection(CLIP.buffer(-4)))) if l.length > 2]   # auta jen uvnitř mapy, přes šev ano
for D in DECKS:                               # po mostech ve výšce mostovky
    if D[6] in DRIVE and AREA.intersects(D[0]):
        p3 = deck_line(D)
        graph.append({**_road(p3, LineString([(x, y) for x, y, _z in p3]), D[6], D[7]), '_deck': 1})
# nájezd, který se napojí doprostřed jiného kusu (rampa na průtah, cesta na mostovku), by v prohlížeči byl slepý
# konec – graf spojuje jen konce kusů. Takový kus se v místě napojení rozdělí na dva.
def _split3(p3, s, at):
    out_a, out_b, acc = [p3[0]], None, 0.0
    for i in range(1, len(p3)):
        a_, b_ = p3[i - 1], p3[i]; seg_ = math.hypot(b_[0] - a_[0], b_[1] - a_[1])
        if out_b is None and acc + seg_ >= s:
            t = (s - acc) / (seg_ or 1); m = [at[0], at[1], round(a_[2] + (b_[2] - a_[2]) * t, 1)]   # přesně do konce napojeného kusu
            out_a.append(m); out_b = [m, b_]
        elif out_b is None: out_a.append(b_)
        else: out_b.append(b_)
        acc += seg_
    return out_a, out_b
for _round in range(3):
    _lines = [LineString([(q[0], q[1]) for q in g_['p']]) for g_ in graph]
    _tree = shapely.STRtree(_lines); _cuts = {}
    for i, g_ in enumerate(graph):
        for e in (g_['p'][0], g_['p'][-1]):
            P_ = Point(e[0], e[1])
            for k in _tree.query(P_.buffer(1.0)):
                if k == i or _lines[k].distance(P_) > 1.0: continue
                s_ = _lines[k].project(P_)
                if not 2.0 < s_ < _lines[k].length - 2.0: continue
                q_ = _split3(graph[k]['p'], s_, (e[0], e[1]))[0][-1]
                if abs(q_[2] - e[2]) < 2.0: _cuts.setdefault(int(k), {})[round(s_, 1)] = (e[0], e[1])   # jen ve stejné výšce (ne cesta pod mostem)
    if not _cuts: break
    _new = []
    for k, g_ in enumerate(graph):
        if k not in _cuts: _new.append(g_); continue
        rest, done = g_['p'], 0.0
        for s_ in sorted(_cuts[k]):
            a_, b_ = _split3(rest, s_ - done, _cuts[k][s_])
            if b_ is None: break
            _new.append({**g_, 'p': a_}); rest, done = b_, s_
        _new.append({**g_, 'p': rest})
    print('napojení doprostřed kusu rozděleno', sum(len(v) for v in _cuts.values()))
    graph = _new
print('jednosměrných úseků pro auta', sum(1 for g_ in graph if g_.get('o')), 'kruhových objezdů', len(_ring_lines))
# železniční přejezdy (nastroje/prejezdy.py, OSM railway=level_crossing): kus silnice v úrovni terénu si nese [metry od začátku, x, y]
if os.path.exists('assets/prejezdy.json'):
    sys.path.insert(0, 'nastroje'); import prejezdy as _pj
    _pj_pts = [tuple(float(v) for v in to_local(lo, la)) for la, lo in json.load(open('assets/prejezdy.json'))]
    _rails = shapely.STRtree([l for _, g_, c_, _w, _n in roads if c_ == 'rail' for l in lines(g_)] or [Point(1e9, 1e9)])
    for g_ in graph:
        if g_.get('c') == 'service' or g_.get('_deck'): continue      # mostovka nad tratí přejezd nemá
        j_ = [q for q in _pj.na_kusu(g_['p'], _pj_pts) if len(_rails.query(Point(q[1], q[2]), predicate='dwithin', distance=3.0))]   # silnice opravdu kříží kolej (ne souběžná ulice)
        if j_: g_['j'] = j_
for g_ in graph: g_.pop('_deck', None)
print('železničních přejezdů', sum(len(g_.get('j', [])) for g_ in graph))
sys.path.insert(0, 'nastroje'); import kruhace as _kr
_kr.oznac(graph, _ring_lines)   # kruhový objezd: kusy okruhu ('rb') a vjezdy, které dávají přednost ('y')
print('vjezdů na kruhový objezd', sum(len(g_.get('y', [])) for g_ in graph))
stops = [{'name': sname(r), 'x': r.geom.x, 'y': r.geom.y} for _, r in inf.iterrows()
         if r['class'] == 'bus_stop' and AREA.contains(r.geom) and sname(r)]
def zline(l):
    l = l.segmentize(3.0); xs_, ys_ = np.array(l.coords).T
    return [[round(x, 1), round(y, 1), round(float(z), 1)] for x, y, z in zip(xs_, ys_, ground(xs_, ys_))]
water_out = {'ponds': [], 'streams': []}
for _, r in wat.iterrows():
    g = r.geom.intersection(AREA)
    if g.is_empty: continue
    if g.geom_type in ('Polygon', 'MultiPolygon'):
        for p in polys(g):
            if p.area > 15: water_out['ponds'].append(zline(p.exterior) + ([] if r['class'] != 'swimming_pool' else []))
    elif (r['class'] == 'river' or (r['class'] == 'stream' and POTOKY)) and not podzemni(r):
        water_out['streams'] += [zline(l) for l in lines(g)]
piste_out = []                                 # pro lyžaře v prohlížeči: vždy shora dolů
for l in PISTE:
    for q in lines(l.intersection(AREA)):
        if q.length < 30: continue
        z = zline(q); piste_out.append(z if z[0][2] >= z[-1][2] else z[::-1])
TRAM = [l for _, r in seg.iterrows() if r.subtype == 'rail' and r['class'] == 'tram' for l in lines(r.geom)]
tram_out = [zline(q) for l in TRAM for q in lines(l.intersection(AREA)) if q.length > 1] + \
           [deck_line(D) for D in DECKS if D[6] == 'tram' and AREA.intersects(D[0])]
_tt = shapely.STRtree(TRAM) if TRAM else None
tstop_out = [[round(r.geom.x, 1), round(r.geom.y, 1), sname(r)] for _, r in inf.iterrows() if _tt is not None and r['class'] == 'stop_position'
             and r.geom.geom_type == 'Point' and sname(r) and AREA.contains(r.geom) and len(_tt.query(r.geom.buffer(4)))]
walk_out = [zline(l) for l, w, c, n in all_lines if c in ('footway', 'path', 'pedestrian', 'cycleway') and l.intersects(AREA)
            for l in [l.intersection(AREA)] if l.geom_type == 'LineString' and l.length > 8]
json.dump({'buildings': binfo, 'chimneys': chimneys, 'streets': street_out, 'roads': graph, 'stops': stops, 'water': water_out, 'walks': walk_out, 'pistes': piste_out, 'trams': tram_out, 'tstops': tstop_out,
           'decks': [{'p': deck_line(D), 'w': D[4]} for D in DECKS if D[5] != 'foot' and AREA.intersects(D[0])],
           'lamps': props['lamp'], 'ground_small': [[round(float(ground(x, y)), 1) for x in np.linspace(-HALF, HALF, 81)]
                                                     for y in np.linspace(HALF, -HALF, 81)]},
          open(f'{OUT}/info_src.json', 'w'), separators=(',', ':'), ensure_ascii=False)
print('hotovo')
