// Doplněk „Zápasy FC Hradec Králové a LED aréna“ (dříve assets/custom_web.js): Malšovická aréna (FINEP Arena).
// Rozpis a průběžné skóre: /api/zapasy (Vercel funkce, skripty/vercel_api/zapasy.js), záloha statický zapasy.json (zdroje v assets/doplnky/hk_zapasy.json).
// Při domácím zápase svítí lízátka (od hodiny před výkopem do konce), na obrazovce je skóre, nad arénou popisek s dalším zápasem.
// V noci fasádu obíhá barevné LED světlo. Rozměry arény (azimut, stožáry, obvod, budova) jsou v konfiguraci a odpovídají modelu malsovicka_arena v custom_models.js.
// Používá jen veřejné window.Izomapa: onFrame (vrstva 'world'), onCard, latLonToWorld, toImg, gz, depth, getEnvironment.
(() => {
  const ID = 'hk_zapasy';
  const Izomapa = window.Izomapa;
  if (!Izomapa) return;
  let unsubFrame = null, unsubCard = null;

  Izomapa.registerPlugin(ID, {
    onInit(api) {
      const C = api.getPluginData(ID);
      if (!C || !C.arena) return;
      const AR = C.arena, ZDROJE = C.zdroje || ['api/zapasy', 'zapasy.json'], ODKAZ = C.odkaz || 'https://www.fchk.cz/matches/MUZ', KR = C.zkratky || {};
      const KARTA_RE = new RegExp(AR.karta_re || 'Malšovick|FINEP', 'i');
      const A = AR.azimut * Math.PI / 180;
      const [cx, cy] = api.latLonToWorld(AR.lat, AR.lon), g = api.gz(cx, cy);
      const W = (s, t) => [cx + Math.cos(A) * s - Math.sin(A) * t, cy + Math.sin(A) * s + Math.cos(A) * t];   // osy arény -> svět
      const MASTS = AR.stozary || [];
      // obvod fasády pro LED: zaoblený obdélník 140 × 100 m (r 15) bez úseku za budovou hlavní tribuny + tři strany budovy
      const ring = (hs, ht, r, K = 10, m = 5) => {
        const C4 = [[hs - r, ht - r], [-hs + r, ht - r], [-hs + r, -ht + r], [hs - r, -ht + r]], pts = [];
        for (let q = 0; q < 4; q++) {
          const [cs, ct] = C4[q];
          for (let i = 0; i <= m; i++) { const a = (q + i / m) * Math.PI / 2; pts.push([cs + r * Math.cos(a), ct + r * Math.sin(a)]); }
          const a1 = ((q + 1) % 4) * Math.PI / 2, [ns, nt] = C4[(q + 1) % 4], e = [ns + r * Math.cos(a1), nt + r * Math.sin(a1)], s0 = pts[pts.length - 1];
          for (let k = 1; k < K; k++) pts.push([s0[0] + (e[0] - s0[0]) * k / K, s0[1] + (e[1] - s0[1]) * k / K]);
        }
        return pts;
      };
      const OB = AR.obvod || { pul_s: 70, pul_t: 50, polomer: 15 }, OUT = ring(OB.pul_s, OB.pul_t, OB.polomer), segs = [];
      for (let i = 0; i < OUT.length; i++) {
        const a = OUT[i], b = OUT[(i + 1) % OUT.length];
        if ((a[1] + b[1]) / 2 > 46 && Math.abs((a[0] + b[0]) / 2) < 36) continue;
        segs.push([a, b, 17.0]);
      }
      const BW = AR.budova || [];
      for (let i = 0; i < BW.length - 1; i++) segs.push([BW[i], BW[i + 1], 17.5]);
      let per = 0; for (const s of segs) { s.push(per); per += Math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]); }

      // ---------- data ----------
      let D = null, nextLoad = 0;
      const load = async () => {
        for (const u of ZDROJE) {
          try { const r = await fetch(u, { cache: 'no-cache' }); if (r.ok) { const d = await r.json(); if (d.zapasy) { D = d; return; } } } catch { /* další zdroj */ }
        }
      };
      const tick = () => {
        const now = Date.now();
        if (now < nextLoad) return;
        const m = cur(now);
        nextLoad = now + (m && m.phase !== 'next' ? 45e3 : 10 * 60e3);
        load();
      };
      // aktuální domácí zápas: phase 'live' (od 15 min před výkopem do konce), 'soon' (dnes), 'next' (další domácí)
      const cur = (now = Date.now()) => {
        if (!D) return null;
        const home = D.zapasy.filter((z) => z.doma);
        const live = D.live && D.live.doma ? D.live : null;
        if (live && !(live.konec && now > Date.parse(live.t) + 140 * 60e3)) return { z: live, phase: 'live' };
        for (const z of home) {
          if (!z.t) continue;
          const k = Date.parse(z.t);
          if (now >= k - 15 * 60e3 && now <= k + 125 * 60e3) return { z, phase: 'live' };
          if (k > now && k - now < 14 * 3600e3) return { z, phase: 'soon' };
        }
        const nx = home.find((z) => (z.t ? Date.parse(z.t) : Date.parse(z.datum + 'T23:59:00')) > now);
        return nx ? { z: nx, phase: 'next' } : null;
      };
      const lightsOn = (m, now = Date.now()) => m && m.z.t && now >= Date.parse(m.z.t) - 75 * 60e3 && now <= Date.parse(m.z.t) + 140 * 60e3 && !(m.z.konec && m.z.faze === 'konec' && now > Date.parse(m.z.t) + 120 * 60e3);
      const kr = (n) => KR[n] || (n || '').replace(/^(FC|FK|SK|AC|MFK|1\.\s*FC|1\.FC|FC\s)\s*/, '').slice(0, 3).toUpperCase();
      const soup = (z) => (z.hoste || '').replace(/^(FC|FK|SK|AC|MFK)\s+/, '');
      const DNY = ['ne', 'po', 'út', 'st', 'čt', 'pá', 'so'];
      const kdy = (z) => {
        const d = new Date(z.t || z.datum + 'T12:00:00');
        const dd = `${DNY[d.getDay()]} ${d.getDate()}. ${d.getMonth() + 1}.`;
        return z.t ? `${dd} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}` : dd + ' (čas bude upřesněn)';
      };

      // ---------- kreslení ----------
      const P = (x, y, h, d) => { const [ix, iy] = api.toImg(x, y, h); return [d.ox + ix * d.sx, d.oy + iy * d.sx]; };
      const PA = (s, t, h, d) => P(...W(s, t), g + h, d);
      function glow(ctx, x, y, r, col, a) {
        const gr = ctx.createRadialGradient(x, y, 0, x, y, r);
        gr.addColorStop(0, `rgba(${col},${a})`); gr.addColorStop(0.35, `rgba(${col},${a * 0.45})`); gr.addColorStop(1, `rgba(${col},0)`);
        ctx.fillStyle = gr; ctx.fillRect(x - r, y - r, 2 * r, 2 * r);
      }
      function drawLED(d, k) {                                 // barevný pás nahoře a dole na fasádě + slabý nádech lamel
        const { ctx, t } = d;
        ctx.save(); ctx.globalCompositeOperation = 'lighter';
        for (const [a, b, top, p0] of segs) {
          const [x0, y0] = W(...a), [x1, y1] = W(...b), mx = (x0 + x1) / 2, my = (y0 + y1) / 2;
          const nx = (y1 - y0), ny = -(x1 - x0), nl = Math.hypot(nx, ny);
          if (api.depth(mx + nx / nl, my + ny / nl, g + 8) > api.depth(mx, my, g + 8)) continue;   // odvrácená strana
          const L = Math.hypot(x1 - x0, y1 - y0), n = Math.max(1, Math.ceil(L / 4));
          for (let i = 0; i < n; i++) {
            const u0 = i / n, u1 = (i + 1) / n, hue = ((p0 + L * (u0 + u1) / 2) / per * 360 - t * 40) % 360;
            const xa = x0 + (x1 - x0) * u0, ya = y0 + (y1 - y0) * u0, xb = x0 + (x1 - x0) * u1, yb = y0 + (y1 - y0) * u1;
            const q = (h0, h1) => { const p = [P(xa, ya, g + h0, d), P(xb, yb, g + h0, d), P(xb, yb, g + h1, d), P(xa, ya, g + h1, d)];
              ctx.beginPath(); p.forEach(([x, y], j) => (j ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); ctx.fill(); };
            ctx.fillStyle = `hsla(${hue},100%,55%,${0.14 * k})`; q(3.6, top - 0.3);                     // nádech lamel
            ctx.fillStyle = `hsla(${hue},100%,62%,${0.95 * k})`; q(top - 0.75, top - 0.3); q(3.65, 4.0);  // LED pásy
          }
        }
        ctx.restore();
      }
      function drawLights(d, k) {                              // rozsvícená lízátka: terč, kužel světla a záře nad hřištěm
        const { ctx } = d, [p0x, p0y] = P(cx, cy, g, d), [p1x, p1y] = P(cx + 1, cy, g, d), mpx = Math.hypot(p1x - p0x, p1y - p0y) * 1.15;   // px na metr
        ctx.save(); ctx.globalCompositeOperation = 'lighter';
        const [pcx, pcy] = P(cx, cy, g + 6, d);
        glow(ctx, pcx, pcy, 75 * mpx, '255,250,225', 0.22 * k);
        for (const [dx, dy] of MASTS) {
          const dd = Math.hypot(dx, dy), ux = -dx / dd, uy = -dy / dd, fx = cx + dx + ux * 10, fy = cy + dy + uy * 10;
          const [X, Y] = P(fx, fy, g + 53, d);
          ctx.fillStyle = `rgba(255,252,235,${0.07 * k})`;                                    // kužel ke hřišti
          const [ax, ay] = P(cx + dx * 0.25 - uy * 25, cy + dy * 0.25 + ux * 25, g, d), [bx, by] = P(cx + dx * 0.25 + uy * 25, cy + dy * 0.25 - ux * 25, g, d);
          ctx.beginPath(); ctx.moveTo(X, Y); ctx.lineTo(ax, ay); ctx.lineTo(bx, by); ctx.closePath(); ctx.fill();
          glow(ctx, X, Y, 16 * mpx, '255,253,240', 0.9 * k);
          glow(ctx, X, Y, 5.5 * mpx, '255,255,255', 1.0 * k);
        }
        ctx.restore();
      }
      function drawScreen(d, m) {                              // obsah obrazovky (stínítko s = 59,85, t −6,9…6,9, výška 19,7…26,5)
        const { ctx, now } = d;
        const o = PA(59.84, 6.9, 26.5, d), u = PA(59.84, 5.9, 26.5, d), v = PA(59.84, 6.9, 25.5, d);
        const ux = u[0] - o[0], uy = u[1] - o[1], vx = v[0] - o[0], vy = v[1] - o[1];
        if (Math.hypot(ux, uy) < 2.2) return;                  // moc malé
        // stínítko je vidět jen z přivrácené strany
        if (api.depth(...W(58.8, 0), g + 23) > api.depth(...W(59.84, 0), g + 23)) return;
        ctx.save();
        ctx.transform(ux, uy, vx, vy, o[0], o[1]);             // 1 jednotka = 1 m, x doprava po stínítku, y dolů
        const z = m.z, live = m.phase === 'live';
        ctx.fillStyle = '#05070c'; ctx.fillRect(0, 0, 13.8, 6.8);
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        const F = (w, px) => `${w} ${px}px "Atkinson Hyperlegible", system-ui, sans-serif`;
        if (live) {
          const sc = z.skore ? `${z.skore[0]} : ${z.skore[1]}` : '– : –';
          ctx.fillStyle = '#ffffff'; ctx.font = F(700, 1.5); ctx.fillText(kr(z.domaci), 2.6, 2.4); ctx.fillText(kr(z.hoste), 11.2, 2.4);
          ctx.fillStyle = '#ffd34d'; ctx.font = F(700, 2.3); ctx.fillText(sc, 6.9, 2.5);
          ctx.fillStyle = '#9fd0ff'; ctx.font = F(400, 0.95);
          const f = z.faze || (now >= Date.parse(z.t) ? 'hraje se' : 'výkop ' + kdy(z).split(' ').pop());
          ctx.fillText(f.toUpperCase(), 6.9, 5.0);
        } else {
          ctx.fillStyle = '#9fd0ff'; ctx.font = F(400, 0.95); ctx.fillText(m.phase === 'soon' ? 'DNES HRAJEME' : 'PŘÍŠTÍ ZÁPAS', 6.9, 1.2);
          ctx.fillStyle = '#ffffff'; ctx.font = F(700, 1.45); ctx.fillText(`${kr(z.domaci)} – ${kr(z.hoste)}`, 6.9, 3.0);
          ctx.fillStyle = '#ffd34d'; ctx.font = F(700, 1.1); ctx.fillText(kdy(z).replace(' (čas bude upřesněn)', '').toUpperCase(), 6.9, 5.1);
        }
        // rastr LED stínítka
        ctx.fillStyle = 'rgba(0,0,0,0.25)'; for (let y = 0.15; y < 6.8; y += 0.3) ctx.fillRect(0, y, 13.8, 0.08);
        ctx.restore();
      }
      function drawLabel(d, m) {                               // popisek nad arénou
        const { ctx, sx } = d;
        if (sx < 0.1 || sx > 1.6) return;
        const [X, Y] = P(cx, cy, g + 70, d), z = m.z;
        const txt = m.phase === 'live' ? `● ŽIVĚ ${kr(z.domaci)} ${z.skore ? z.skore.join(':') : '–:–'} ${kr(z.hoste)}${z.faze ? ' · ' + z.faze : ''}`
          : `⚽ ${m.phase === 'soon' ? 'Dnes' : 'Další zápas'}: ${kdy(z).replace(' (čas bude upřesněn)', '')} · ${soup(z)}`;
        ctx.save(); ctx.font = '700 12px "Atkinson Hyperlegible", system-ui, sans-serif';
        const w = Math.ceil(ctx.measureText(txt).width) + 14;
        ctx.fillStyle = m.phase === 'live' ? '#b3261e' : '#16191f'; ctx.fillRect(Math.round(X - w / 2), Math.round(Y - 10), w, 20);
        ctx.strokeStyle = '#f2c66d'; ctx.lineWidth = 1; ctx.strokeRect(Math.round(X - w / 2) + 0.5, Math.round(Y - 10) + 0.5, w - 1, 19);
        ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(txt, Math.round(X), Math.round(Y) + 1);
        ctx.restore();
      }


      const karta = ({ title, el }) => {
        if (!/Malšovick|FINEP/i.test(title)) return;
        const h = (tag, txt, cls) => { const e = document.createElement(tag); if (txt) e.textContent = txt; if (cls) e.className = cls; return e; };
        const box = h('div'); box.style.cssText = 'margin-top:8px;display:grid;gap:4px;font-size:.86rem';
        el.append(box);
        const render = () => {
          box.replaceChildren();
          if (!D) { box.append(h('p', 'Rozpis zápasů se načítá…')); return; }
          const now = Date.now(), m = cur(now);
          if (m && m.phase === 'live') {
            const z = m.z, p = h('p'); p.style.cssText = 'font-weight:700;color:#ff8a7a';
            p.textContent = `Právě se hraje: ${z.domaci} ${z.skore ? z.skore.join(':') : ''} ${z.hoste}${z.faze ? ' (' + z.faze + ')' : ''}`;
            box.append(p);
          }
          box.append(h('strong', 'Domácí zápasy FC Hradec Králové'));
          const dl = h('dl'); dl.style.cssText = 'display:grid;grid-template-columns:auto 1fr;gap:2px 10px;margin:0';
          const next = D.zapasy.filter((z) => z.doma && (z.t ? Date.parse(z.t) + 125 * 60e3 : Date.parse(z.datum + 'T23:59:00')) > now).slice(0, 6);
          for (const z of next) { dl.append(h('dt', kdy(z).replace(' (čas bude upřesněn)', ''))); dl.append(h('dd', `${soup(z)} · ${z.soutez}${z.kolo ? ', ' + z.kolo : ''}`)); }
          if (!next.length) dl.append(h('dd', 'Další domácí zápas zatím není v rozpisu.'));
          box.append(dl);
          const last = D.zapasy.filter((z) => z.doma && z.skore).slice(-3).reverse();
          if (last.length) {
            box.append(h('strong', 'Poslední výsledky doma'));
            const dl2 = h('dl'); dl2.style.cssText = dl.style.cssText;
            for (const z of last) { dl2.append(h('dt', z.datum.split('-').reverse().map(Number).join('. ').replace(/\. (\d{4})$/, '. $1'))); dl2.append(h('dd', `${z.skore.join(':')} ${soup(z)}`)); }
            box.append(dl2);
          }
          const a = h('a', 'Celý rozpis na fchk.cz ↗'); a.href = ODKAZ; a.target = '_blank'; a.rel = 'noopener';
          box.append(a);
        };
        render();
        if (!D) load().then(render);
      };

      load(); nextLoad = Date.now() + 10 * 60e3;
      unsubFrame = api.onFrame((ctx, view) => {
        tick();
        const d = { ...view, ctx, t: view.now / 1000 };
        const [ix, iy] = api.toImg(cx, cy, g); if (!d.vis(ix, iy, 900 * d.sx + 200)) return;
        const m = cur(), night = d.night, dusk = Math.max(night, api.getEnvironment().weather === 'clear' ? 0 : 0.35);
        if (night > 0.3) drawLED(d, Math.min(1, (night - 0.3) * 2.5));
        if (m && lightsOn(m) && m.phase !== 'next') drawLights(d, Math.max(0.25, dusk));
        if (m && d.sx > 0.35) drawScreen(d, m);
        if (m) drawLabel(d, m);
      }, { layer: 'world' });
      unsubCard = api.onCard(karta);
    },
    onDestroy() { if (unsubFrame) unsubFrame(); if (unsubCard) unsubCard(); unsubFrame = unsubCard = null; },
  });
})();
