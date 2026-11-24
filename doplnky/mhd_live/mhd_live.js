// Doplněk mhd_live: živé zpoždění a poloha vozidel MHD (api/mhd_live, zdroj DPmHK) a špendlíky „Všechny spoje MHD“.
// 1) Každé živé vozidlo se spáruje se spojem jízdního řádu (stejná linka, poloha a směr při zpoždění, které vozidlo hlásí).
//    Spoj se pak vykreslí na trase o zpoždění „zpět“ (setMhdDelayHook): vozidlo 3 min po jízdním řádu stojí tam, kde mělo být před 3 min.
//    Změna zpoždění se doplňuje plynule (max. 15 s zpoždění za sekundu), ať vozidlo neskáče.
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
        if (best < 350) cands.push({ v, i, d: bd, s: best - (prev.get(v.id) === i ? 100 : 0) });
      }
    }
    cands.sort((a, b) => a.s - b.s);
    const usedV = new Set(), usedI = new Set(), match = new Map();
    for (const c of cands) {
      if (usedV.has(c.v.id) || usedI.has(c.i)) continue;
      usedV.add(c.v.id); usedI.add(c.i); match.set(c.i, { id: c.v.id, d: c.d, rep: c.v.d });
    }
    return { match, free: vehicles.filter((v) => !usedV.has(v.id)) };
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
    const cfg = { api: 'api/mhd_live', poll_s: 30, ...(api.getPluginData(ID) || {}) };
    const S = { live: [], match: new Map(), free: [], freePos: new Map(), cur: new Map(), byId: new Map(), ok: false, t: 0, timers: [] };
    let box = null, off = [];
    const on = () => !!(box && box.querySelector('input').checked);

    const hook = (i) => S.cur.get(i) || 0;

    function zpracuj(d) {
      const M = api.getMhd(); if (!M || !d || !Array.isArray(d.v)) return;
      const r = parovani(d.v, api.getMhdRaw(), M, api, S.byId), now = Date.now();
      S.live = d.v; S.free = r.free; S.ok = true; S.t = now;
      for (const [i, m] of r.match) { S.match.set(i, { ...m, last: now }); S.byId.set(m.id, i); }
      for (const [i, m] of [...S.match]) if (!r.match.has(i) && now - m.last > 600e3) { S.match.delete(i); if (S.byId.get(m.id) === i) S.byId.delete(m.id); }
      if (box) box.title = `Všechny spoje MHD: špendlíky s číslem linky na odzoomované mapě (zelený včas, žlutý 1 min, oranžový 2 min, červený 3 min a víc, šedý bez živých dat). Živě ${d.v.length} vozidel, ${r.match.size} spojeno s jízdním řádem (zdroj ${d.z === 'fcen' ? 'mapa.fcen.cz' : 'DPmHK'})`;
    }
    async function nacti() {
      if (doc.hidden || !api.getMhd()) return;
      try {
        const r = await fetchFn(cfg.api); if (!r.ok) throw new Error(r.status);
        zpracuj(await r.json());
      } catch (e) { if (Date.now() - S.t > 300e3) { S.ok = false; S.match.clear(); } }    // bez dat 5 min: zpět na jízdní řád
    }
    function plyn(dt) {                                    // použité zpoždění se blíží cílovému nejvýš 15 s za sekundu
      const step = 15 * Math.min(dt || 0.016, 0.1);
      for (const [i, m] of S.match) {
        const c = S.cur.get(i);
        if (c == null) S.cur.set(i, m.d); else S.cur.set(i, c + Math.max(-step, Math.min(step, m.d - c)));
      }
      for (const [i, c] of S.cur) if (!S.match.has(i)) { const n = c + Math.max(-step, Math.min(step, -c)); if (Math.abs(n) < 0.5) S.cur.delete(i); else S.cur.set(i, n); }
    }

    // ---------- špendlíky ----------
    const frontaPinu = [];
    function pins(ctx, view) {
      const M = api.getMhd(); if (!M) return;
      const a = Math.max(0, Math.min(1, (0.24 - view.sx) / 0.08)); if (a <= 0) return;
      const frac = view.now / 1000 - Math.floor(view.now / 1000), t = view.now / 1000, out = frontaPinu; out.length = 0;
      const volne = S.free.map((v) => ({ v, w: S.freePos.get(v.id) }));
      for (const [i, el, ceka, , d] of api.getMhdActive()) {
        if (ceka) continue;
        const trip = M.trips[i], line = M.routes[trip[0]][0];
        const o = api.mhdPos(trip, el + frac), m = S.match.get(i);
        if (!m && volne.some((f) => f.w && f.v.ln === line && Math.hypot(f.w[0] - o.x, f.w[1] - o.y) < 250)) continue;   // totéž vozidlo je už vidět na skutečné poloze
        out.push({ ix: o.ix, iy: o.iy, line, k: m ? kat(m.rep) : 'n', ph: i });
      }
      for (const f of volne) {                             // živá vozidla bez spoje v jízdním řádu: na skutečné poloze, plynule
        const [x, y] = api.latLonToWorld(f.v.la, f.v.lo);
        let w = S.freePos.get(f.v.id); if (!w) S.freePos.set(f.v.id, w = [x, y]);
        w[0] += (x - w[0]) * 0.06; w[1] += (y - w[1]) * 0.06;
        const [ix, iy] = api.toImg(w[0], w[1], api.gz(w[0], w[1]));
        out.push({ ix, iy, line: f.v.ln, k: kat(f.v.d), ph: f.v.id.length ? f.v.id.charCodeAt(f.v.id.length - 1) : 0 });
      }
      for (const id of S.freePos.keys()) if (!S.free.some((v) => v.id === id)) S.freePos.delete(id);
      out.sort((p, q) => p.iy - q.iy);
      const U = 2, bob = [0, 1, 2, 1];
      ctx.save(); ctx.globalAlpha = a; ctx.imageSmoothingEnabled = false;
      for (const p of out) {
        const [X, Y] = view.toScreen(p.ix, p.iy);
        if (X < -30 || Y < -50 || X > view.cw + 30 || Y > view.ch + 30) continue;
        const b = bob[Math.floor(t * 3 + p.ph * 0.7) & 3], x = Math.round(X), y = Math.round(Y);
        ctx.fillStyle = 'rgba(10,14,24,0.30)'; ctx.fillRect(x - (3 - (b >> 1)) * U, y - U, (6 - (b >> 1) * 2) * U, U); ctx.fillRect(x - (2 - (b >> 1)) * U, y, (4 - (b >> 1) * 2) * U, U >> 1 || 1);
        ctx.drawImage(sprite(p.line, p.k, doc), x - 6 * U - (U >> 1), y - 16 * U - b * U, 13 * U, 17 * U);
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
      api.setMhdDelayHook(hook);
      off.push(api.onFrame((ctx, view) => { plyn(view.dt); if (on()) pins(ctx, view); }, { layer: 'top' }));
      const t0 = setInterval(() => { if (api.getMhd()) { clearInterval(t0); nacti(); } }, 1000);   // jízdní řády se načítají až po startu
      S.timers.push(t0, setInterval(nacti, cfg.poll_s * 1000));
    }
    function stop() {
      api.setMhdDelayHook(null); off.forEach((f) => f()); off = []; S.timers.forEach(clearInterval); S.timers = [];
      if (box) box.remove(); box = null;
    }
    return { start, stop, hook, state: S, cfg, zpracuj, plyn, nacti, pins };
  }

  if (typeof window !== 'undefined' && window.Izomapa) {
    let inst = null;
    window.Izomapa.registerPlugin(ID, {
      onInit(api) { inst = create(api); inst.start(); },
      onDestroy() { if (inst) inst.stop(); inst = null; },
    });
    window.IzomapaMhdLive = { create, parovani, kat };       // jen pro testy
  }
})();
