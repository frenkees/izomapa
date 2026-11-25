// Doplněk mhd_live: živé zpoždění a poloha vozidel MHD (api/mhd_live, zdroj DPmHK) a špendlíky „Všechny spoje MHD“.
// 1) Každé živé vozidlo se spáruje se spojem jízdního řádu (stejná linka, poloha a směr při zpoždění, které vozidlo hlásí).
//    Spoj se pak vykreslí na trase o zpoždění „zpět“ (setMhdDelayHook): vozidlo 3 min po jízdním řádu stojí tam, kde mělo být před 3 min.
//    Poloha se ale NEvypočítá ze zpoždění (to se mění skokově, hlavně u zastávek, a vozidlo by skákalo o stovky metrů): spoj se vede po trase
//    „doháněcím“ modelem. Cíl = průmět GPS vozidla na trasu spoje + dojetí o stáří záznamu rychlostí vozidla; zobrazená poloha se k cíli
//    plynule blíží (rychlost nejméně 0, takže nikdy necouvá: je-li před cílem, zpomalí, případně zastaví a počká, je-li pozadu, přidá).
//    Háček setMhdElHook řídí polohu každý snímek, ne jen jednou za sekundu.
// 2) Přepínač ve Vrstvách ukáže na odzoomované mapě (kde se vozidla nekreslí) pixelové špendlíky s číslem linky:
//    zelený = včas, žlutý 1 min, oranžový 2 min, červený 3 min a víc, šedý = bez živých dat (jízdní řád).
// Jen window.Izomapa, žádné vnitřní proměnné stránky.
(() => {
  const ID = 'mhd_live';
  const PAL = {
    g: ['#4cc34d', '#8be37f', '#2a8a34', '#fff'], y: ['#f2d03b', '#fff08a', '#c29c12', '#14161d'], o: ['#f08a2b', '#ffc07a', '#b85a12', '#fff'],
    r: ['#e0382f', '#ff8b7e', '#9b1d1d', '#fff'], n: ['#8a93a3', '#c3cad6', '#5d6575', '#14161d'],
  };
  const OUT = '#14161d';
  const FONT = {   // pixelové písmo 3 × 5
    0: '111101101101111', 1: '010110010010111', 2: '111001111100111', 3: '111001111001111', 4: '101101111001001', 5: '111100111001111',
    6: '111100111101111', 7: '111001001010010', 8: '111101111101111', 9: '111101111001111', A: '010101111101101', B: '110101110101110',
    C: '011100100100011', D: '110101101101110', E: '111100110100111', F: '111100110100100', H: '101101111101101', K: '101101110101101',
    L: '100100100100111', N: '110101101101101', S: '011100010001110', V: '101101101101010', X: '101101010101101', Z: '111001010100111',
  };
  const kat = (d) => (d == null ? 'n' : d < 60 ? 'g' : d < 120 ? 'y' : d < 180 ? 'o' : 'r');   // kategorie zpoždění v s

  // ---------- párování živých vozidel na spoje ----------
  // vehicles: [{id, ln, la, lo, az, d}], raw: [[i, s od odjezdu podle jízdního řádu]], M: MHD (trips, routes, dur), api: latLonToWorld, mhdPos
  // prev: Map id -> index spoje z minula (stejné vozidlo se drží svého spoje). Vrací { match: Map i -> {id, d (zpoždění podle polohy), rep (hlášené)}, free: [vozidla bez spoje] }
  function parovani(vehicles, raw, M, api, prev = new Map()) {
    const byLine = new Map();
    for (const r of raw) { const ln = M.routes[M.trips[r[0]][0]][0]; if (!byLine.has(ln)) byLine.set(ln, []); byLine.get(ln).push(r); }
    const cands = [];
    for (const v of vehicles) {
      const list = byLine.get(v.ln); if (!list) continue;
      const [px, py] = api.latLonToWorld(v.la, v.lo), hx = Math.sin(v.az * Math.PI / 180), hy = Math.cos(v.az * Math.PI / 180);
      const ohodnot = (i, el0, d) => {
        const dur = M.dur[i], el = el0 - d; if (el < -60 || el > dur + 60) return null;
        const o = api.mhdPos(M.trips[i], Math.max(0, Math.min(dur, el))), l = Math.hypot(o.dx, o.dy) || 1;
        return Math.hypot(o.x - px, o.y - py) + ((o.dx * hx + o.dy * hy) / l < -0.3 ? 400 : 0);
      };
      for (const [i, el0] of list) {
        const s0 = ohodnot(i, el0, v.d); if (s0 == null || s0 > 1500) continue;
        let best = s0, bd = v.d;                                       // doladění zpoždění podle polohy (±90 s)
        for (let d = v.d - 90; d <= v.d + 90; d += 15) { const s = ohodnot(i, el0, d); if (s != null && s < best) { best = s; bd = d; } }
        if (best < 350) cands.push({ v, i, d: bd, el0, s: best - (prev.get(v.id) === i ? 100 : 0) });
      }
    }
    cands.sort((a, b) => a.s - b.s);
    const usedV = new Set(), usedI = new Set(), match = new Map();
    for (const c of cands) {
      if (usedV.has(c.v.id) || usedI.has(c.i)) continue;
      usedV.add(c.v.id); usedI.add(c.i); match.set(c.i, { id: c.v.id, d: c.d, rep: c.v.d, el0: c.el0 });
    }
    return { match, free: vehicles.filter((v) => !usedV.has(v.id)) };
  }

  // ---------- doháněcí model polohy ----------
  const JAM_S = 90, JAM_JUNC_M = 35, JAM_STOP_M = 45, JAM_SIG_M = 60, JAM_MOVE_M = 12, JAM_KMH = 3;   // zácpa: stojí aspoň 90 s (≤ 3 km/h, nehnul se o víc než 12 m) a není u zastávky, křižovatky, semaforu ani přejezdu
  const TAU = 8, ACC = 1.5, BRK = 2.5, VMAX = 22, AGE_EXTRA = 30, VALID_MS = 90e3, CAP_S = 22, SNAP_M = 20;   // CAP_S: jak dlouho (s od záznamu) drží zastávka extrapolaci; SNAP_M: stojící vůz se přichytí k zastávce do této vzdálenosti
  function schedS(trip, el, M) {                           // metr na trase podle jízdního řádu v čase el
    const q = trip[4]; let i = 2; while (i < q.length - 2 && q[i] < el) i += 2;
    const f = Math.max(0, Math.min(1, (el - q[i - 2]) / ((q[i] - q[i - 2]) || 1)));
    return Math.min(M.shapes[trip[1]].L, q[i - 1] + (q[i + 1] - q[i - 1]) * f);
  }
  function elFor(trip, sd, M) {                            // inverze: čas na jízdním řádu, kdy je spoj na metru sd (na zastávce stojí = čas příjezdu)
    const q = trip[4], L = M.shapes[trip[1]].L;
    if (sd >= L - 3) return q[q.length - 2] + 1;           // v cíli: spoj skončil
    let k = 1; while (k < q.length && q[k] < sd) k += 2;
    if (k >= q.length) return q[q.length - 2] + 1;
    if (k === 1) return q[0];
    const t0 = q[k - 3], s0 = q[k - 2], t1 = q[k - 1], s1 = q[k];
    return t0 + (sd - s0) / ((s1 - s0) || 1) * (t1 - t0);
  }
  function projekce(sh, x, y, s0, okno, hx = 0, hy = 0) {  // průmět bodu na trasu v okně kolem s0; (hx, hy) = směr jízdy vozidla
    let best = null, bd = 1e9, bo = 0;
    for (let k = 1; k < sh.w.length; k++) {
      if (sh.len[k] < s0 - okno || sh.len[k - 1] > s0 + okno) continue;
      const a = sh.w[k - 1], b = sh.w[k], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1, u = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l2));
      const d = Math.hypot(a[0] + dx * u - x, a[1] + dy * u - y), s = sh.len[k - 1] + u * (sh.len[k] - sh.len[k - 1]);
      // trasa jedoucí dvakrát týmž místem (smyčky, otočky): druhý průchod proti směru jízdy nebo hluboko za modelem se penalizuje; off zůstává čistě geometrický
      const c = d + ((hx || hy) && dx * hx + dy * hy < -0.3 * Math.sqrt(l2) ? 60 : 0) + Math.max(0, s0 - 40 - s) * 0.1;
      if (c < bd) { bd = c; bo = d; best = s; }
    }
    return best == null ? null : { s: best, off: bo };
  }
  // stav b: sd poloha (m po trase), v rychlost (m/s), tgt cíl v čase tt (ms), vg rychlost vozidla (m/s), tm čas posledního kroku (ms)
  function postup(b, now) {
    if (b.tm == null) b.tm = now;
    if (now - b.tm > 5000) { b.sd = Math.max(b.sd, b.tgt); b.v = b.vg; }   // dlouhá pauza (skrytý panel): nedojíždět zpětně, skočit na poslední cíl
    let t = Math.min(now - b.tm, 5000) / 1000; b.tm = now;
    while (t > 1e-6) {
      const h = Math.min(t, 0.05); t -= h;
      const age = (now - b.tt) / 1000, vg = age < AGE_EXTRA ? b.vg : 0; let tx = b.tgt + b.vg * Math.min(age, AGE_EXTRA), cp = false;
      if (b.cap != null && age < CAP_S && tx > b.cap) { tx = b.cap; cp = true; }       // extrapolace nesmí přejet zastávku: vůz k ní dojede a počká na další záznam
      const gap = tx - b.sd;
      let vcmd = Math.max(0, Math.min(vg + gap / TAU, Math.max(vg * 1.6, 3) + (gap > 100 ? 6 : 0), VMAX));
      if (cp) vcmd = Math.min(vcmd, Math.sqrt(1.6 * BRK * Math.max(0, gap)));      // plynulé zastavení přesně na zastávce
      b.v += Math.max(-BRK * h, Math.min(ACC * h, vcmd - b.v)); b.sd += b.v * h;
    }
    return b.sd;
  }

  // metry na trase, kde spoj stojí na zastávkách (podle jízdního řádu: čas příjezdu → metr v profilu); cache podle spoje
  const zastS = new WeakMap();
  function zastavkyS(trip) {
    let z = zastS.get(trip); if (z) return z;
    const q = trip[4], tim = new Map(); z = [];
    for (let k = 0; k < q.length; k += 2) if (!tim.has(q[k])) tim.set(q[k], q[k + 1]);
    for (let k = 0; k < trip[6].length; k += 2) { const s = tim.get(trip[6][k + 1]); if (s !== undefined && s > 0 && (!z.length || s > z[z.length - 1] + 5)) z.push(s); }
    zastS.set(trip, z); return z;
  }
  // cíl a strop extrapolace podle zastávek: stojící vůz u zastávky se k ní přichytí, jedoucí se zastaví nejpozději na nejbližší zastávce před ním
  function cilZastavka(zs, ps, vg, tgt) {
    let cap = null;
    if (vg < 0.8) { for (const z of zs) if (Math.abs(z - ps) < SNAP_M) return { tgt: z, cap: null }; return { tgt, cap }; }
    for (const z of zs) if (z > ps + 3) { if (tgt > z - 1) { cap = z - 1; tgt = Math.min(tgt, cap); } break; }
    return { tgt, cap };
  }

  // ---------- pixelový špendlík ----------
  const spriteCache = new Map();
  function sprite(label, k, doc) {
    const key = label + k; if (spriteCache.has(key)) return spriteCache.get(key);
    const W = 13, H = 17, c = doc.createElement('canvas'); c.width = W; c.height = H;
    const g = c.getContext('2d'), [base, light, dark, txt] = PAL[k];
    const inside = (x, y) => x >= 0 && y >= 0 && x < W && y < H && (((x - 6) ** 2 + (y - 6) ** 2 <= 33) || (y >= 10 && y <= 15 && Math.abs(x - 6) <= Math.max(0, 3.4 - (y - 10) * 0.65)));
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      if (!inside(x, y)) continue;
      const edge = !inside(x - 1, y) || !inside(x + 1, y) || !inside(x, y - 1) || !inside(x, y + 1);
      g.fillStyle = edge ? OUT : (x + y < 8 && y < 8 ? light : x + y > 14 ? dark : base);
      g.fillRect(x, y, 1, 1);
    }
    const t = String(label).toUpperCase().slice(0, 3), w = t.length * 4 - 1, x0 = Math.round(6.5 - w / 2) - (t.length === 3 ? 0 : 0), y0 = 3;
    g.fillStyle = txt;
    [...t].forEach((ch, n) => { const f = FONT[ch]; if (!f) return; for (let p = 0; p < 15; p++) if (f[p] === '1') g.fillRect(x0 + n * 4 + (p % 3), y0 + Math.floor(p / 3), 1, 1); });
    spriteCache.set(key, c); return c;
  }

  function create(api, doc = document, fetchFn = (...a) => fetch(...a)) {
    const cfg = { api: 'api/mhd_live', poll_s: 15, ...(api.getPluginData(ID) || {}) };
    const S = { jam: new Map(), ch: new Map(), live: [], match: new Map(), free: [], cur: new Map(), byId: new Map(), hit: [], ok: false, t: 0, timers: [] };
    let box = null, off = [];
    const on = () => !!(box && box.querySelector('input').checked);

    function blizko(pts, x, y, r) { for (const q of pts) if (Math.abs(q[0] - x) < r && Math.abs(q[1] - y) < r && Math.hypot(q[0] - x, q[1] - y) < r) return true; return false; }
    function krizovatky(now) {                              // body, kde se v datech silnic stýkají aspoň 3 konce kusů (křižovatky, kruháče); obnovuje se po 2 min
      if (S.junc && now - S.junc.t < 120e3) return S.junc.pts;
      const cnt = new Map(), pts = [];
      for (const r of (api.getRoads ? api.getRoads() : [])) { const w = r.w; if (!w || w.length < 2) continue; for (const q of [w[0], w[w.length - 1]]) { const k = Math.round(q[0] / 6) + ',' + Math.round(q[1] / 6), c = cnt.get(k) || { n: 0, x: q[0], y: q[1] }; c.n++; cnt.set(k, c); } }
      for (const c of cnt.values()) if (c.n >= 3) pts.push([c.x, c.y]);
      S.junc = { t: now, pts }; return pts;
    }
    function jamUpdate(i, v, x, y, now, M) {                // sleduje, jak dlouho vůz stojí na jednom místě
      let j = S.jam.get(i);
      if ((v.sp || 0) > JAM_KMH || !j || Math.hypot(j.x - x, j.y - y) > JAM_MOVE_M) { S.jam.set(i, { x, y, since: now - (v.ag || 0) * 1000, stuck: false }); return; }
      if (j.stuck || now - j.since < JAM_S * 1000) return;
      const stops = (M.stops || []).map((s) => [s[1], s[2]]), sig = api.getSignals ? api.getSignals().map((s) => [s[0], s[1]]) : [], xs = api.getXings ? api.getXings().map((c) => [c.x, c.y]) : [];
      j.stuck = !blizko(stops, x, y, JAM_STOP_M) && !blizko(sig, x, y, JAM_SIG_M) && !blizko(xs, x, y, JAM_SIG_M) && !blizko(krizovatky(now), x, y, JAM_JUNC_M);
    }
    const zacpa = (i, now = Date.now()) => { const j = S.jam.get(i), m = S.match.get(i); return j && j.stuck && m && now - m.last < 90e3 ? Math.max(1, Math.round((now - j.since) / 60e3)) : 0; };
    function cardNote(i, now) { const min = zacpa(i, now); return min ? `Stojím v zácpě :( už ${min} min` : null; }
    function jamLabels(ctx, view) {                         // při velkém přiblížení červený popisek za číslem linky nad stojícím vozem
      const M = api.getMhd(); if (!M || view.sx < 0.3) return;
      ctx.save(); ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'center'; ctx.lineJoin = 'round'; ctx.lineWidth = 4;
      for (const [i, el, ceka] of api.getMhdActive()) {
        if (ceka || !zacpa(i)) continue;
        const trip = M.trips[i], o = api.mhdPos(trip, elHook(i, el, view.now / 1000 - Math.floor(view.now / 1000))), [X, Y] = view.toScreen(o.ix, o.iy);
        if (X < -80 || Y < -60 || X > view.cw + 80 || Y > view.ch + 40) continue;
        const t = `${M.routes[trip[0]][0]} · zácpa :(`;
        ctx.strokeStyle = '#14161d'; ctx.strokeText(t, X, Y - 30); ctx.fillStyle = '#ff4d42'; ctx.fillText(t, X, Y - 30);
      }
      ctx.restore();
    }
    const platny = (b, now) => !!b && now - b.tt < VALID_MS;
    const elNow = (m, now) => m.el0 + (now - m.last) / 1000;     // čas od odjezdu podle jízdního řádu (bez zpoždění) právě teď
    function hook(i) {                                   // zpoždění pro mhdActive (1× za s): odvozené z doháněcího modelu, aby sedělo s polohou
      const M = api.getMhd(), m = S.match.get(i), b = S.ch.get(i), now = Date.now();
      if (M && m && m.el0 != null && platny(b, now)) {
        const e = elFor(M.trips[i], postup(b, now), M); let d = elNow(m, now) - e;
        if (e < 1) d = Math.max(0, d);                    // vůz je na začátku trasy: před odjezdem stojí (nepředjíždí)
        S.cur.set(i, d); return d;
      }
      return S.cur.get(i) || 0;
    }
    function elHook(i, el, f) {                          // poloha spoje v každém snímku
      const M = api.getMhd(), b = S.ch.get(i), now = Date.now();
      if (M && platny(b, now)) return elFor(M.trips[i], postup(b, now), M);
      const m = S.match.get(i); if (m && m.el0 != null && S.cur.has(i)) return elNow(m, now) - S.cur.get(i);   // záloha: plynule každý snímek
      return el + f;
    }

    function zpracuj(d) {
      const M = api.getMhd(); if (!M || !d || !Array.isArray(d.v)) return;
      const nej = new Map(); for (const v of d.v) { const o = nej.get(v.id); if (!o || (v.ag ?? 0) < (o.ag ?? 0)) nej.set(v.id, v); }   // zdroj občas vrací i starý „záznam-ducha“ téhož vozu: platí nejčerstvější
      const veh = [...nej.values()], r = parovani(veh, api.getMhdRaw(), M, api, S.byId), now = Date.now(), vid = new Map(veh.map((v) => [v.id, v]));
      S.live = veh; S.free = r.free; S.ok = true; S.t = now;
      for (const [i, m] of r.match) {
        const pi0 = S.byId.get(m.id); if (pi0 != null && pi0 !== i) S.ch.delete(pi0);     // vůz přepárován na jiný spoj: starý spoj nedojíždí dál
        S.match.set(i, { ...m, last: now }); S.byId.set(m.id, i);
        const v = vid.get(m.id), trip = M.trips[i], sh = M.shapes[trip[1]]; if (!v || !sh) continue;
        const b0 = S.ch.get(i), [x, y] = api.latLonToWorld(v.la, v.lo), vg = (v.sp || 0) / 3.6, sj = schedS(trip, m.el0 - m.d, M);
        const hx = Math.sin(v.az * Math.PI / 180), hy = Math.cos(v.az * Math.PI / 180);
        let p = projekce(sh, x, y, b0 ? b0.sd : sj, 700, hx, hy);
        if (!p || p.off > 80) p = projekce(sh, x, y, sj, 700, hx, hy);
        if (!p || p.off > 80) continue;                                   // GPS mimo trasu: model dojíždí dál podle posledních dat
        jamUpdate(i, v, x, y, now, M);
        const cz = cilZastavka(zastavkyS(trip), p.s, vg, p.s + vg * (v.ag || 0)), tgt = cz.tgt;
        if (!b0 || !platny(b0, now) || Math.abs(tgt - b0.sd) > 600) S.ch.set(i, { sd: tgt, v: vg, tgt, tt: now, vg, tm: now, cap: cz.cap });
        else { b0.tgt = tgt; b0.tt = now; b0.vg = vg; b0.cap = cz.cap; }
      }
      for (const [i, m] of [...S.match]) if (!r.match.has(i) && now - m.last > 600e3) { S.match.delete(i); S.ch.delete(i); S.jam.delete(i); if (S.byId.get(m.id) === i) S.byId.delete(m.id); }
      if (box) box.title = `Všechny spoje MHD: špendlíky s číslem linky na odzoomované mapě (zelený včas, žlutý 1 min, oranžový 2 min, červený 3 min a víc, šedý bez živých dat). Živě ${d.v.length} vozidel, ${r.match.size} spojeno s jízdním řádem (zdroj ${d.z === 'fcen' ? 'mapa.fcen.cz' : 'DPmHK'})`;
    }
    async function nacti() {
      if (doc.hidden || !api.getMhd()) return;
      try {
        const r = await fetchFn(cfg.api); if (!r.ok) throw new Error(r.status);
        zpracuj(await r.json());
      } catch (e) { if (Date.now() - S.t > 300e3) { S.ok = false; S.match.clear(); S.ch.clear(); S.byId.clear(); S.jam.clear(); } }    // bez dat 5 min: zpět na jízdní řád
    }
    function plyn(dt) {                                    // záloha bez GPS průmětu: použité zpoždění se blíží hlášenému nejvýš 3 s za sekundu
      const h = Math.min(dt || 0.016, 0.1), up = 0.9 * h, dn = 3 * h, now = Date.now();   // zpoždění roste pomaleji než čas: vůz zpomalí, ale necouvne
      for (const [i, m] of S.match) {
        if (platny(S.ch.get(i), now)) continue;
        const c = S.cur.get(i);
        if (c == null) S.cur.set(i, m.d); else S.cur.set(i, c + Math.max(-dn, Math.min(up, m.d - c)));
      }
      for (const [i, c] of S.cur) if (!S.match.has(i)) { const n = c + Math.max(-dn, Math.min(up, -c)); if (Math.abs(n) < 0.5) S.cur.delete(i); else S.cur.set(i, n); }
    }

    // ---------- špendlíky ----------
    const frontaPinu = [];
    function pins(ctx, view) {
      const M = api.getMhd(); if (!M) return;
      const a = Math.max(0, Math.min(1, (0.24 - view.sx) / 0.08)); if (a <= 0) return;
      const frac = view.now / 1000 - Math.floor(view.now / 1000), t = view.now / 1000, out = frontaPinu; out.length = 0;
      for (const [i, el, ceka, , d] of api.getMhdActive()) {
        if (ceka) continue;
        const trip = M.trips[i];
        if (M.routes[trip[0]][1] === 2) continue;         // vlaky bez špendlíku
        const o = api.mhdPos(trip, elHook(i, el, frac)), m = S.match.get(i);
        out.push({ ix: o.ix, iy: o.iy, line: M.routes[trip[0]][0], k: m ? kat(m.rep) : 'n', ph: i, i });
      }
      out.sort((p, q) => p.iy - q.iy);
      const U = 2, bob = [0, 1, 2, 1];
      ctx.save(); ctx.globalAlpha = a; ctx.imageSmoothingEnabled = false;
      S.hit.length = 0;
      for (const p of out) {
        const [X, Y] = view.toScreen(p.ix, p.iy);
        if (X < -30 || Y < -50 || X > view.cw + 30 || Y > view.ch + 30) continue;
        const b = bob[Math.floor(t * 3 + p.ph * 0.7) & 3], x = Math.round(X), y = Math.round(Y);
        ctx.fillStyle = 'rgba(10,14,24,0.30)'; ctx.fillRect(x - (3 - (b >> 1)) * U, y - U, (6 - (b >> 1) * 2) * U, U); ctx.fillRect(x - (2 - (b >> 1)) * U, y, (4 - (b >> 1) * 2) * U, U >> 1 || 1);
        ctx.drawImage(sprite(p.line, p.k, doc), x - 6 * U - (U >> 1), y - 16 * U - b * U, 13 * U, 17 * U);
        if (a > 0.5) S.hit.push([x, y - 9 * U - b * U, p.i]);
      }
      ctx.restore();
    }

    function ui() {                                        // přepínač ve Vrstvách (za Dopravou)
      const slot = api.getUiSlot('vrstvy'); if (!slot) return;
      box = doc.createElement('label');
      box.title = 'Všechny spoje MHD: na odzoomované mapě špendlíky s číslem linky (zelený včas, žlutý 1 min, oranžový 2 min, červený 3 min a víc zpoždění, šedý bez živých dat)';
      box.innerHTML = '<input type="checkbox" id="l-mhdpins"><span>Spoje MHD</span>';
      const sv = (() => { try { return localStorage.getItem('izo-mhdpins') === '1'; } catch { return false; } })();
      box.querySelector('input').checked = sv;
      box.querySelector('input').addEventListener('change', (e) => { try { localStorage.setItem('izo-mhdpins', e.target.checked ? '1' : '0'); } catch {} });
      const t = doc.getElementById('l-traffic'), row = t && t.closest ? t.closest('label') : null;
      if (row && row.parentNode === slot) row.after(box); else slot.appendChild(box);
    }
    function start() {
      ui();
      api.setMhdDelayHook(hook); if (api.setMhdElHook) api.setMhdElHook(elHook); if (api.setMhdCardNote) api.setMhdCardNote(cardNote);
      off.push(api.onFrame((ctx, view) => { plyn(view.dt); jamLabels(ctx, view); if (on()) pins(ctx, view); else S.hit.length = 0; }, { layer: 'top' }));
      off.push(api.onMapClick((e) => {                     // klik na špendlík otevře kartu spoje (malý jízdní řád, další zastávka se zpožděním)
        let best = null, bd = 17;
        for (const [x, y, i] of S.hit) { const d = Math.hypot(x - e.screenX, y - e.screenY); if (d < bd) { bd = d; best = i; } }
        return best != null && api.mhdTripCard(best) === true;
      }, { priority: 10 }));
      const vis = () => { if (!doc.hidden) nacti(); }; if (doc.addEventListener) { doc.addEventListener('visibilitychange', vis); off.push(() => doc.removeEventListener('visibilitychange', vis)); }
      const t0 = setInterval(() => { if (api.getMhd()) { clearInterval(t0); nacti(); } }, 1000);   // jízdní řády se načítají až po startu
      S.timers.push(t0, setInterval(nacti, cfg.poll_s * 1000));
    }
    function stop() {
      api.setMhdDelayHook(null); if (api.setMhdElHook) api.setMhdElHook(null); if (api.setMhdCardNote) api.setMhdCardNote(null); off.forEach((f) => f()); off = []; S.timers.forEach(clearInterval); S.timers = [];
      if (box) box.remove(); box = null;
    }
    return { start, stop, hook, elHook, zacpa, cardNote, jamUpdate, state: S, cfg, zpracuj, plyn, nacti, pins };
  }

  if (typeof window !== 'undefined' && window.Izomapa) {
    let inst = null;
    window.Izomapa.registerPlugin(ID, {
      onInit(api) { inst = create(api); inst.start(); },
      onDestroy() { if (inst) inst.stop(); inst = null; },
    });
    window.IzomapaMhdLive = { create, parovani, kat, elFor, schedS, projekce, postup, zastavkyS, cilZastavka };       // jen pro testy
  }
})();
