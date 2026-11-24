// Doplněk lampy_svetla: v noci záře pouličních lamp přímo v prohlížeči (bez přerenderu dlaždic).
// Vedlejší ulice: starší oranžové sodíkové světlo, hlavní tahy: modernější bílé LED (širší, studenější světelný kruh).
// Data (site/doplnky/lampy_svetla/lampy.json, vyrábí overlay_hook.py): { l: [[x, y, z, typ], …] }, typ 0 = sodík, 1 = LED. Jen window.Izomapa.
(() => {
  const ID = 'lampy_svetla';
  const TYPY = [
    { head: [255, 168, 64], pool: [255, 140, 40], r: 7, a: 0.5 },     // sodík: oranžové světlo, menší kruh
    { head: [255, 244, 226], pool: [255, 238, 210], r: 10, a: 0.42 }, // LED: teplá bílá, vzdálenější záře
  ];
  const VYSKA = 4.6;                                               // výška svítidla nad terénem (m)
  const cfg = { data: 'doplnky/lampy_svetla/lampy.json' };
  let api = null, off = [], L = null, mrtvy = false, nacitam = false, spr = null, ext = null;

  function sprity() {                                              // předkreslené měkké záře (jeden sprite na typ a druh)
    const mk = (w, h, rgb, tvrd) => {
      const c = document.createElement('canvas'); c.width = w; c.height = h;
      const g = c.getContext('2d'), gr = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
      gr.addColorStop(0, `rgba(${rgb},${tvrd ? 1 : 0.85})`); gr.addColorStop(tvrd ? 0.3 : 0.25, `rgba(${rgb},${tvrd ? 0.5 : 0.4})`); gr.addColorStop(1, `rgba(${rgb},0)`);
      g.setTransform(1, 0, 0, h / w, 0, 0); g.fillStyle = gr; g.fillRect(0, 0, w, w); return c;
    };
    return TYPY.map((t) => ({ head: mk(32, 32, t.head.join(','), true), pool: mk(96, 96, t.pool.join(','), false) }));
  }
  async function nacti() {
    if (L || mrtvy || nacitam) return; nacitam = true;
    try {
      const r = await fetch(cfg.data, { signal: AbortSignal.timeout(15000) });
      if (!r.ok) { mrtvy = true; return; }
      const d = await r.json();
      const n = d.l.length; L = { n, ix: new Float32Array(n), iy: new Float32Array(n), igy: new Float32Array(n), x: new Float32Array(n), y: new Float32Array(n), z: new Float32Array(n), t: new Uint8Array(n) };
      d.l.forEach(([x, y, z, t], i) => {
        const h = api.toImg(x, y, z + VYSKA), g = api.toImg(x, y, z);
        L.ix[i] = h[0]; L.iy[i] = h[1]; L.igy[i] = g[1]; L.x[i] = x; L.y[i] = y; L.z[i] = z; L.t[i] = t;
      });
      spr = sprity();
      const o = api.toImg(0, 0, 0);                                // průmět kruhu na zem (v izometrii elipsa): půlosy na 1 m poloměru
      const a = api.toImg(1, 0, 0), b = api.toImg(0, 1, 0);
      ext = { w: Math.hypot(a[0] - o[0], b[0] - o[0]), h: Math.hypot(a[1] - o[1], b[1] - o[1]) };
    } catch { mrtvy = true; } finally { nacitam = false; }
  }
  function kresli(ctx, view) {
    const night = view.night ?? 0;
    if (night < 0.12 || mrtvy) return;
    if (!L) { nacti(); return; }
    const { sx, ox, oy, cw, ch } = view;
    if (sx < 0.1) return;                                          // při oddálení se lampy nekreslí
    const k = Math.min(1, (night - 0.12) / 0.5), m = 120 * sx;
    const okluze = sx > 0.2;
    let kres = 0;
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    for (let i = 0; i < L.n; i++) {
      const X = ox + L.ix[i] * sx, Y = oy + L.iy[i] * sx, Yg = oy + L.igy[i] * sx;
      if (X < -m || X > cw + m || Yg < -m || Y > ch + m) continue;
      if (okluze && kres < 700 && api.isOccluded(L.x[i], L.y[i], L.z[i] + 1.5)) continue;   // lampa za budovou nesvítí přes dům
      kres++;
      const t = L.t[i], T = TYPY[t], S = spr[t];
      const pw = T.r * ext.w * 2 * sx, ph = T.r * ext.h * 2 * sx;
      ctx.globalAlpha = T.a * k; ctx.drawImage(S.pool, X - pw / 2, Yg - ph / 2, pw, ph);         // světelný kruh na zemi
      const hr = Math.max(3, 1.1 * ext.w * sx * 2);
      ctx.globalAlpha = Math.min(1, 0.9 * k); ctx.drawImage(S.head, X - hr, Y - hr, hr * 2, hr * 2);   // svítidlo
    }
    ctx.restore();
  }
  window.Izomapa.registerPlugin(ID, {
    onInit(a) { api = a; Object.assign(cfg, a.getPluginData(ID) || {}); off.push(api.onFrame(kresli, { layer: 'world' })); },
    onDestroy() { for (const f of off) try { f(); } catch {} off = []; },
  });
})();
