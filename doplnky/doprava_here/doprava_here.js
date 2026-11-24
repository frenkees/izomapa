// Doplněk doprava_here: zácpy podle HERE / TomTom Traffic (barevné čáry ulic) a hustota a rychlost aut podle jamFactoru.
// Silnice mají r.h = čísla úseků (číslo * 2 + 1 = úsek jede proti směru kusu; overlay_hook.py). Živá data api/doprava (cache 10 min),
// typický průběh podle hodiny api/doprava_typicka. Auta: share(r, dir) = min_podil (volno) až 1 (J >= j_plny), nic navíc nepřibude;
// bez dat nebo bez r.h se nic nemění. Jen window.Izomapa, žádné vnitřní proměnné stránky.
(() => {
  const ID = 'doprava_here';
  const JAM_COL = (J) => J < 2 ? '#4cb86a' : J < 4 ? '#e8c53a' : J < 6 ? '#f08a2c' : '#d8392b';

  function create(api, doc = document, fetchFn = (...a) => fetch(...a)) {
    const cfg = { min_podil: 0.35, j_plny: 6, zive_s: 300, api: 'api/doprava', api_typicka: 'api/doprava_typicka', rezimy: [{ v: 'live', t: 'živě' }], ...(api.getPluginData(ID) || {}) };
    const S = { v: 0, live: null, typ: null, ids: null, mode: 'live', timers: [] };
    let slotT = 0, slotV = 0, jamBox = null, selEl = null, off = [];

    const praha = () => {                                  // hodina v pražském čase (+24 o víkendu), přepočet nejvýš jednou za 30 s
      if (Date.now() - slotT < 30e3) return slotV; slotT = Date.now();
      const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Prague', hour: 'numeric', hourCycle: 'h23', weekday: 'short' }).formatToParts(new Date()).map((q) => [q.type, q.value]));
      return (slotV = +p.hour + (p.weekday === 'Sat' || p.weekday === 'Sun' ? 24 : 0));
    };
    const val = (id, slot) => {                            // [J 0-10, rychlost 0-1]: slot 'cur' = živě, jinak typicky; číslo = hodina (0-23 pracovní den, 24-47 víkend)
      if (slot === 'cur') { const l = S.live && S.live.get(id); if (l) return [l[0] / 10, l[1] / 100]; slot = praha(); }
      const a = S.typ && S.typ[id], j = a ? a[slot] : null;
      return j == null ? null : [j / 10, Math.max(0.3, 1 - j / 120)];
    };
    const roadVal = (r, dir, slot) => {
      let n = 0, j = 0, v = 0;
      for (const h of r.h) { if (((h & 1) ? -1 : 1) !== dir) continue; const q = val(h >> 1, slot); if (q) { n++; j += q[0]; v += q[1]; } }
      return n ? [j / n, v / n] : null;
    };
    const roadState = (r) => {                             // podíl aut a rychlost [po směru, proti], přepočítá se při změně dat (S.v)
      if (r._dhv === S.v) return r;
      r._dhv = S.v; r._dhg = [1, 1]; r._dhs = [1, 1];
      if (!r.h) return r;
      for (const d of [0, 1]) {
        const q = roadVal(r, d ? -1 : 1, 'cur');
        if (q) { r._dhg[d] = cfg.min_podil + (1 - cfg.min_podil) * Math.min(1, q[0] / cfg.j_plny); r._dhs[d] = q[1]; }
      }
      return r;
    };
    const hook = {
      share: (r, dir) => (r.h ? roadState(r)._dhg[dir > 0 ? 0 : 1] : 1),
      speed: (r, dir) => (r.h ? roadState(r)._dhs[dir > 0 ? 0 : 1] : 1),
    };

    function drawJam(ctx, view) {                          // barevné čáry vytížení vpravo od směru jízdy; mimo obrazovku se nekreslí
      const { ox, oy, cw, ch, sx } = view;
      ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.lineWidth = Math.max(2, Math.min(6, 3.5 * sx + 1)); ctx.globalAlpha = 0.9;
      const slot = S.mode === 'live' ? 'cur' : +S.mode, o = ctx.lineWidth * 0.8;
      for (const r of api.getRoads()) {
        if (!r.h) continue;
        const a = r.p[0], b = r.p[r.p.length - 1], mx = ox + (a[0] + b[0]) / 2 * sx, my = oy + (a[1] + b[1]) / 2 * sx;
        if (mx < -300 || my < -300 || mx > cw + 300 || my > ch + 300) continue;
        for (const dir of r.o ? [r.o] : [1, -1]) {
          const q = roadVal(r, dir, slot); if (!q) continue;
          ctx.strokeStyle = JAM_COL(q[0]); ctx.beginPath();
          r.p.forEach((pt, i) => {
            const q0 = r.p[Math.max(0, i - 1)], q1 = r.p[Math.min(r.p.length - 1, i + 1)];
            const dx = (q1[0] - q0[0]) * dir, dy = (q1[1] - q0[1]) * dir, l = Math.hypot(dx, dy) || 1, k = r.o ? 0 : 1;   // jednosměrka uprostřed
            const X = ox + pt[0] * sx - (dy / l) * o * k, Y = oy + pt[1] * sx + (dx / l) * o * k;
            i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y);
          });
          ctx.stroke();
        }
      }
    }

    let idsP = null;
    const nactiIds = async () => S.ids || (S.ids = await (idsP = idsP || fetchFn(cfg.ids + (cfg.ids_v ? '?v=' + cfg.ids_v : '')).then((r) => r.json())));   // jedno stažení i při souběžném volání
    const nactiTyp = async () => {                         // typický průběh podle hodiny (sběr snímků na serveru)
      let ok = false;
      try {
        const [ids, d] = await Promise.all([nactiIds(), fetchFn(cfg.api_typicka).then((r) => r.ok ? r.json() : null)]);
        if (d && d.s) { const t = {}; for (const [k, v] of Object.entries(d.s)) if (ids[k] !== undefined) t[ids[k]] = v; S.typ = t; S.v++; ok = Object.keys(t).length > 0; }
      } catch (e) { /* bez historie zůstává jen živý stav */ }
      if (selEl) for (const o of selEl.options) if (o.value !== 'live') o.disabled = !ok;
    };
    const nactiZive = async () => {
      try {
        await nactiIds();
        const r = await fetchFn(cfg.api); if (!r.ok) throw new Error(r.status);
        const d = await r.json(), m = new Map();
        for (const [k, v] of Object.entries(d.s || {})) if (S.ids[k] !== undefined) m.set(S.ids[k], v);
        if (m.size) { S.live = m; S.v++; }
      } catch (e) { /* bez živých dat zůstává typický průběh nebo původní hustota */ }
    };

    function ui() {                                        // přepínač Zácpy ve Vrstvách (za Dopravou)
      const slot = api.getUiSlot('vrstvy'); if (!slot) return;
      jamBox = doc.createElement('label'); jamBox.title = 'Barva ulic podle zácp (HERE a TomTom Traffic): živě, nebo typicky v dané hodině';
      jamBox.innerHTML = '<input type="checkbox" id="l-jam"><span>Zácpy</span><select id="jam-mode" aria-label="Zobrazit zácpy"></select>';
      selEl = jamBox.querySelector('select');
      for (const m of cfg.rezimy) { const o = doc.createElement('option'); o.value = m.v; o.textContent = m.t; selEl.appendChild(o); }
      selEl.onchange = (e) => { S.mode = e.target.value; };
      const t = doc.getElementById('l-traffic'), row = t && t.closest ? t.closest('label') : null;
      if (row && row.parentNode === slot) row.after(jamBox); else slot.appendChild(jamBox);
    }
    function start() {
      if (!cfg.ids) return;                                // bez dat z overlay_hook.py (bez ids) není co zobrazit
      ui();
      api.setTrafficHook(hook);
      off.push(api.onFrame((ctx, view) => { if (jamBox && jamBox.querySelector('input').checked && view.sx > 0.1) drawJam(ctx, view); }, { layer: 'ground' }));
      nactiTyp(); nactiZive();
      S.timers.push(setInterval(nactiZive, cfg.zive_s * 1000), setInterval(() => { S.v++; }, 10 * 60e3));   // hodina se mění i bez nových dat
    }
    function stop() {
      api.setTrafficHook(null); off.forEach((f) => f()); off = []; S.timers.forEach(clearInterval); S.timers = [];
      if (jamBox) jamBox.remove(); jamBox = null; selEl = null;
    }
    return { start, stop, hook, state: S, cfg, drawJam, nactiZive, nactiTyp, roadState };
  }

  if (typeof window !== 'undefined' && window.Izomapa) {
    let inst = null;
    window.Izomapa.registerPlugin(ID, {
      onInit(api) { inst = create(api); inst.start(); },
      onDestroy() { if (inst) inst.stop(); inst = null; },
    });
    window.IzomapaDopravaHere = { create };               // jen pro testy
  }
})();
