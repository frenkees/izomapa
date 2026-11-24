// Doplněk udrzba_khk: zimní údržba silnic Královéhradeckého kraje. Úseky, kudy projel sypač nebo pluh (nebo kontrolní vůz), se kreslí na silnici
// barevně podle stáří: zelená do 30 min, oranžová 30–60 min, červená 1–3 h, modrá 3–12 h; starší nebo neošetřené úseky se nekreslí.
// Zdroj: veřejná mapa SÚS KHK (uskhk.eu/suhhkap) přes api/udrzba_khk (společná cache 5 min). Jen window.Izomapa.
(() => {
  const ID = 'udrzba_khk';
  const BARVY = ['148,183,36', '220,140,0', '195,84,57', '41,108,175'];
  const POPIS = ['do 30 minut', '30 až 60 minut', '1 až 3 hodiny', '3 až 12 hodin'];
  const doc = typeof document !== 'undefined' ? document : null;
  let api = null, cfg = {}, off = [], box = null, leg = null, timer = null, mrtvy = false;
  const S = { pasma: [[], [], [], []], t: 0, n: 0, last: 0 };

  const ztlum = () => { try { return localStorage.getItem('izo-udrzba-ztlum') !== '0'; } catch { return true; } };
  const on = () => !!(box && box.querySelector('input').checked);
  function prevedLinie(z) {                                 // [[lo, la, lo, la, …], …] -> světové souřadnice
    return (z || []).map((c) => { const w = []; for (let i = 0; i + 1 < c.length; i += 2) w.push(api.latLonToWorld(c[i + 1], c[i])); return w; });
  }
  async function nacti() {
    if (mrtvy || !on() || (doc && doc.hidden)) return;
    S.last = Date.now();
    try {
      const r = await fetch(cfg.api, { signal: AbortSignal.timeout(10000) });
      if (r.status === 404) { mrtvy = true; if (box) box.hidden = true; legenda(); return; }
      if (!r.ok) return;
      const d = await r.json();
      S.pasma = [0, 1, 2, 3].map((i) => prevedLinie(d.z && d.z[i]));
      S.n = S.pasma.reduce((s, p) => s + p.length, 0); S.t = d.t || Date.now();
      popisek();
    } catch {}
  }
  function popisek() {
    const n = box && box.querySelector('.udrzba-n'); if (!n) return;
    n.textContent = S.n ? `(${S.n})` : '';
    legenda();
    box.title = 'Zimní údržba silnic Královéhradeckého kraje: úseky, kudy v poslední době projel sypač nebo pluh, barevně podle stáří '
      + '(' + POPIS.map((p, i) => ['zelená', 'oranžová', 'červená', 'modrá'][i] + ' ' + p).join(', ') + '). '
      + (S.n ? '' : 'Teď žádná nedávná údržba (mimo zimní sezónu bývá vrstva prázdná).');
  }
  function legenda() {                                      // plovoucí legenda barev, viditelná jen při zapnuté vrstvě
    if (!doc) return;
    if (!leg) {
      leg = doc.createElement('div'); leg.className = 'udrzba-legenda'; leg.hidden = true;
      leg.innerHTML = '<b>Zimní údržba silnic</b>' + POPIS.map((p, i) => `<div><i class="a${i}"></i>${p}</div>`).join('')
        + '<small class="udrzba-st"></small><label><input type="checkbox" class="udrzba-zt"> Ztlumit mapu</label>';
      const zt = leg.querySelector('.udrzba-zt'); zt.checked = ztlum();
      zt.addEventListener('change', () => { try { localStorage.setItem('izo-udrzba-ztlum', zt.checked ? '1' : '0'); } catch {} });
      doc.body.appendChild(leg);
    }
    leg.hidden = !on() || mrtvy;
    const st = leg.querySelector('.udrzba-st');
    st.textContent = !S.t ? 'načítám…' : S.n ? `data před ${Math.max(0, Math.round((Date.now() - S.t) / 60000))} min, ${S.n} úseků` : 'teď žádná nedávná údržba';
  }
  function kresli(ctx, view) {
    if (!on() || !S.n) return;
    const { sx, ox, oy } = view;
    ctx.save(); ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    if (ztlum()) { ctx.fillStyle = 'rgba(16,20,28,0.5)'; ctx.fillRect(0, 0, view.cw, view.ch); }   // schematický režim: mapa i budovy ztlumené, úseky vyniknou
    for (const okraj of [true, false]) for (let i = 3; i >= 0; i--) {   // nejdřív tmavý okraj, pak barva; nejstarší dospod, nejčerstvější navrch
      if (!S.pasma[i].length) continue;
      ctx.strokeStyle = okraj ? 'rgba(10,12,18,0.85)' : `rgba(${BARVY[i]},0.95)`;
      ctx.lineWidth = Math.max(2, sx * (okraj ? 7 : 5));
      ctx.beginPath();
      for (const c of S.pasma[i]) {
        for (let k = 0; k < c.length; k++) {
          const [x, y] = c[k], p = api.toImg(x, y, api.gz(x, y) + 0.3), X = ox + p[0] * sx, Y = oy + p[1] * sx;
          if (k) ctx.lineTo(X, Y); else ctx.moveTo(X, Y);
        }
      }
      ctx.stroke();
    }
    ctx.restore();
  }
  function ui() {                                           // přepínač ve Vrstvách (za Dopravou)
    const slot = api.getUiSlot('vrstvy'); if (!slot) return;
    box = doc.createElement('label');
    box.innerHTML = '<input type="checkbox" id="l-udrzba"><span>Údržba silnic <span class="udrzba-n"></span></span><span class="udrzba-leg"><i class="a0"></i><i class="a1"></i><i class="a2"></i><i class="a3"></i></span>';
    const sv = (() => { try { const v = localStorage.getItem('izo-udrzba'); return v === null ? true : v === '1'; } catch { return true; } })();
    const inp = box.querySelector('input'); inp.checked = sv;
    inp.addEventListener('change', (e) => { try { localStorage.setItem('izo-udrzba', e.target.checked ? '1' : '0'); } catch {} legenda(); if (e.target.checked) nacti(); });
    popisek();
    const t = doc.getElementById('l-traffic'), row = t && t.closest ? t.closest('label') : null;
    if (row && row.parentNode === slot) row.after(box); else slot.appendChild(box);
  }
  function start() {
    ui(); legenda(); nacti();
    off.push(api.onFrame(kresli, { layer: 'ground' }));
    const vis = () => { if (doc && !doc.hidden && Date.now() - S.last > cfg.poll_s * 1000 * 0.8) nacti(); };
    if (doc && doc.addEventListener) { doc.addEventListener('visibilitychange', vis); off.push(() => doc.removeEventListener('visibilitychange', vis)); }
    timer = setInterval(nacti, cfg.poll_s * 1000);
  }
  window.Izomapa.registerPlugin(ID, {
    onInit(a) { api = a; cfg = { api: 'api/udrzba_khk', poll_s: 300, ...(a.getPluginData(ID) || {}) }; start(); },
    onDestroy() { if (timer) clearInterval(timer); for (const f of off) try { f(); } catch {} off = []; if (box && box.remove) box.remove(); if (leg && leg.remove) leg.remove(); },
  });
})();
