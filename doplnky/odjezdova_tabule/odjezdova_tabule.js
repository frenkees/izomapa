// Doplněk „Odjezdová tabule vlaků“ (dříve vestavěná v app.html): mechanická tabule s klapkami (Solari) na hlavním nádraží.
// Řádky = nejbližší odjezdy vlaků podle jízdního řádu (Izomapa.getMhd + Izomapa.departures), první odjíždějící je nahoře. Jakmile odjede, tabule se
// přepisuje řádek po řádku: každé písmeno je klapka ze dvou půlek, která se opravdu překlápí a prochází abecedu až na cílový znak.
// Otevře ji klik na budovu nádraží (onBuildingClick) nebo přiblížení k nádraží (kontrola v onFrame). Nastavení: assets/doplnky/odjezdova_tabule.json.
(() => {
  const ID = 'odjezdova_tabule';
  const Izomapa = window.Izomapa;
  if (!Izomapa) return;
  let unsubClick = null, unsubFrame = null, boardEl = null, onKey = null;

  Izomapa.registerPlugin(ID, {
    onInit(api) {
      const C = api.getPluginData(ID);
      if (!C || !C.stanice) return;
      const ST = C.stanice, TITULEK = C.titulek || 'ODJEZDY';
      const RE_BUD = ST.budova_re ? new RegExp(ST.budova_re, 'i') : null, RE_ZAST = new RegExp(ST.zastavka_re, 'i');
      const BD = { n: C.radku || 7, w: C.sirky || [5, 8, 15, 2], shown: null, busy: false, timer: 0, ids: null, auto: true, open: false, built: false, run: 0 };
      const HORIZONT = (C.horizont_h || 12) * 3600;
      const BD_STEP = 120, BD_MAX = 14, BD_ROW_PAUSE = 450;       // ms na jedno překlopení znaku, nejvýš kroků na znak, pauza mezi řádky
      const BD_CH = ' ABCDEFGHIJKLMNOPQRSTUVWXYZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ0123456789.-/:';
      const bdRed = matchMedia('(prefers-reduced-motion: reduce)');
      const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const ZK = [...(C.zkratky || []).map(([a, b]) => [new RegExp(esc(a), 'i'), b]), [/,\s*/g, ' ']];
      const mhd = () => api.getMhd();
      const prahaS = () => {                                      // sekundy od půlnoci v Praze
        const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Prague', hourCycle: 'h23', hour: '2-digit', minute: '2-digit', second: '2-digit' })
          .formatToParts(new Date()).map((x) => [x.type, x.value]));
        return (+p.hour) * 3600 + (+p.minute) * 60 + (+p.second);
      };
      const hm = (dt) => { const v = Math.round((prahaS() + dt) / 60) % 1440; return `${Math.floor(v / 60)}:${String(v % 60).padStart(2, '0')}`; };

      // ---------- DOM ----------
      const board = document.createElement('section');
      board.className = 'board'; board.id = 'board'; board.hidden = true; board.setAttribute('aria-label', `Odjezdy vlaků: ${ST.nazev || ''}`);
      const head = document.createElement('div'); head.className = 'bd-head';
      const title = document.createElement('span'); title.className = 'bd-title'; title.textContent = TITULEK;
      const clock = document.createElement('span'); clock.className = 'bd-clock'; clock.id = 'bdClock';
      const closeBtn = document.createElement('button'); closeBtn.className = 'px-btn close'; closeBtn.id = 'bdClose'; closeBtn.type = 'button'; closeBtn.setAttribute('aria-label', 'Zavřít tabuli'); closeBtn.textContent = '×';
      head.append(title, clock, closeBtn);
      const rowsEl = document.createElement('div'); rowsEl.className = 'bd-rows'; rowsEl.id = 'bdRows'; rowsEl.setAttribute('role', 'table');
      const foot = document.createElement('div'); foot.className = 'bd-foot'; foot.textContent = 'Podle jízdního řádu, bez zpoždění · číslo koleje je odhad';
      board.append(head, rowsEl, foot);
      document.body.appendChild(board); boardEl = board;

      // ---------- data ----------
      function bdSkrat(s, w) {                                    // dlouhý název se zkracuje (Rychnov nad Kněžnou -> Rychnov n.K.), ať se vejde do w znaků
        s = s.replace(/^Hradec Králové,? /, '');
        for (const [re, to] of ZK) s = s.replace(re, to);
        if (s.length <= w) return s;
        let p = s.split(/\s+/).filter((x) => !/^(nad|pod|u|na|v|ve|při)$/i.test(x));
        s = p.join(' '); if (s.length <= w) return s;
        p = p.map((x, i) => (i > 0 && i < p.length - 1 && x.length > 4 ? x.slice(0, 3) + '.' : x)); s = p.join(' '); if (s.length <= w) return s;
        return p.map((x, i) => (i < p.length - 1 && x.length > 3 ? x.slice(0, 3) + '.' : x)).join(' ').slice(0, w);
      }
      const bdStr = (s, w) => { s = String(s).toUpperCase().replace(/[^ A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ0-9.\-/:]/g, ''); return (s.length > w ? s.slice(0, w) : s).padEnd(w, ' '); };
      function bdIds() {
        if (!BD.ids) { BD.ids = new Set(); mhd().names.forEach((n, i) => { if (RE_ZAST.test(n)) BD.ids.add(i); }); }
        return BD.ids;
      }
      function bdData() {                                         // [[čas, vlak, směr, kolej] jako řetězce pevné šířky]
        const M = mhd(), ids = bdIds(), out = [];
        for (const [dt, t] of api.departures(ids, { trains: true, horizon: HORIZONT })) {
          if (dt <= 0) continue;                                  // už odjel
          const z = t[6]; let kol = '';
          for (let k = 0; k < z.length - 2; k += 2) if (ids.has(z[k])) { const m = /kolej (\w+)/.exec(M.names[z[k]]); if (m) kol = m[1]; break; }
          const pr = M.routes[t[0]][0].split(' ');
          out.push([bdStr(hm(dt), BD.w[0]), bdStr(`${pr[0]} ${pr[pr.length - 1]}`, BD.w[1]), bdStr(bdSkrat(M.names[t[5]], BD.w[2]), BD.w[2]), bdStr(kol, BD.w[3])]);
          if (out.length >= BD.n) break;
        }
        while (out.length < BD.n) out.push(BD.w.map((w) => ' '.repeat(w)));
        return out;
      }

      // ---------- klapky ----------
      const bdSet = (h, ch) => { h.firstChild.textContent = ch; };
      function bdBuild() {
        rowsEl.replaceChildren();
        for (let r = 0; r < BD.n; r++) {
          const row = document.createElement('div'); row.className = 'bd-row'; row.setAttribute('role', 'row');
          BD.w.forEach((w) => {
            const grp = document.createElement('div'); grp.className = 'bd-grp';
            for (let c = 0; c < w; c++) {
              const f = document.createElement('span'); f.className = 'fl'; f.dataset.c = ' ';
              f.innerHTML = '<i class="h t"><b> </b></i><i class="h bt"><b> </b></i><i class="h ft"><b> </b></i><i class="h fb"><b> </b></i>';
              grp.append(f);
            }
            row.append(grp);
          });
          rowsEl.append(row);
        }
        BD.built = true; BD.shown = Array.from({ length: BD.n }, () => BD.w.map((w) => ' '.repeat(w)));
      }
      const bdWait = (ms) => new Promise((r) => setTimeout(r, ms));
      function bdSync() {                                         // BD.shown = to, co klapky opravdu ukazují; rozpracované překlopení se zahodí
        if (!BD.built) return;
        BD.shown = Array.from(rowsEl.children, (row) => Array.from(row.children, (grp) => Array.from(grp.children, (cell) => {
          for (const a of cell.getAnimations({ subtree: true })) a.cancel();
          const c = cell.dataset.c || ' ';
          for (const h of cell.children) bdSet(h, c);
          cell.children[2].style.visibility = cell.children[3].style.visibility = 'hidden';
          return c;
        }).join('')));
      }
      async function bdStep(cell, ch, run) {                      // jedno překlopení: horní půlka s dosavadním znakem padá dolů, spodní s novým znakem se za ní zaklapne
        if (run !== BD.run) return false;
        const [t, bt, ft, fb] = cell.children, cur = cell.dataset.c;
        const play = async (el, keys, o) => { try { await el.animate(keys, { ...o, fill: 'forwards' }).finished; return true; } catch { return false; } };   // zrušená animace (zavření tabule) = konec kroku
        bdSet(t, ch); bdSet(ft, cur); bdSet(fb, ch);
        ft.style.visibility = 'visible';
        if (!(await play(ft, [{ transform: 'rotateX(0deg)' }, { transform: 'rotateX(-90deg)' }], { duration: BD_STEP * 0.45, easing: 'ease-in' })) || run !== BD.run) return false;
        ft.style.visibility = 'hidden'; fb.style.visibility = 'visible';
        if (!(await play(fb, [{ transform: 'rotateX(90deg)' }, { transform: 'rotateX(0deg)' }], { duration: BD_STEP * 0.55, easing: 'ease-out' })) || run !== BD.run) return false;
        bdSet(bt, ch); fb.style.visibility = 'hidden'; cell.dataset.c = ch;
        return true;
      }
      async function bdFlip(cell, to, run) {                      // klapka prochází znaky po pořadí abecedy až na cílový (dlouhá cesta se zkrátí)
        const cur = cell.dataset.c;
        if (cur === to) return;
        if (bdRed.matches) { for (const h of cell.children) bdSet(h, to); cell.dataset.c = to; return; }
        let a = Math.max(0, BD_CH.indexOf(cur)); const b = Math.max(0, BD_CH.indexOf(to));
        const steps = ((b - a + BD_CH.length) % BD_CH.length) || BD_CH.length, k = Math.max(0, steps - BD_MAX);
        a = (a + k) % BD_CH.length;
        if (k) for (const h of [cell.children[0], cell.children[1]]) bdSet(h, BD_CH[a]), cell.dataset.c = BD_CH[a];
        for (let n = k; n < steps; n++) { a = (a + 1) % BD_CH.length; if (!(await bdStep(cell, BD_CH[a], run))) return; }
      }
      async function bdApply(data, pauza) {                       // přepisuje změněné řádky po jednom; v řádku se klapky překlápí zleva doprava s malým zpožděním
        const run = ++BD.run; BD.busy = true;
        const rows = rowsEl.children, cur = BD.shown.map((r) => r.slice());
        BD.shown = data.map((r) => r.slice());
        for (let r = 0; r < data.length; r++) {
          if (data[r].join('|') === cur[r].join('|')) continue;
          const jobs = []; let ci = 0;
          data[r].forEach((s, g) => { const cells = rows[r].children[g].children; for (let c = 0; c < s.length; c++, ci++) jobs.push(bdWait(ci * 22).then(() => bdFlip(cells[c], s[c], run))); });
          await Promise.all(jobs);
          if (run !== BD.run || !BD.open) break;
          await bdWait(pauza);
        }
        if (run === BD.run) BD.busy = false;
      }
      function bdTick() {
        if (!BD.open || document.hidden) return;
        const s = prahaS(); clock.textContent = `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, '0')}`;
        if (BD.busy) return;
        const data = bdData();
        if (data.some((r, i) => r.join('|') !== BD.shown[i].join('|'))) bdApply(data, BD_ROW_PAUSE);   // první řádek odjel: tabule se přepisuje řádek po řádku
      }
      function bdOpen() {
        const M = mhd();
        if (!M || !M.names || !M.trips || BD.open) return;
        if (!BD.built) bdBuild();
        const card = document.getElementById('card'), cardClose = document.getElementById('cardClose');
        if (card && !card.hidden && cardClose) cardClose.click();
        BD.run++; bdSync(); BD.open = true; board.hidden = false;   // srovnat s tím, co klapky skutečně ukazují (zavření během animace)
        BD.busy = false; bdApply(bdData(), 220);                  // otevření: řádky naskakují jeden po druhém
        clearInterval(BD.timer); BD.timer = setInterval(bdTick, 1000); bdTick();
      }
      function bdClose(user) { BD.open = false; BD.run++; BD.busy = false; board.hidden = true; clearInterval(BD.timer); bdSync(); if (user) BD.auto = false; }
      closeBtn.addEventListener('click', () => bdClose(true));
      onKey = (e) => { if (e.key === 'Escape' && BD.open) bdClose(true); };
      addEventListener('keydown', onKey);

      // ---------- otevření: klik na budovu a přiblížení ----------
      unsubClick = api.onBuildingClick((b) => {
        const nm = b && b.name;
        if (!nm || !(RE_BUD?.test(nm) || nm === ST.nazev) || !mhd()?.trips) return false;
        BD.auto = true; bdOpen(); return true;                    // karta budovy se neotevře
      }, { priority: 10 });
      let posledni = 0;
      unsubFrame = api.onFrame((ctx, view) => {                   // přiblížení k nádraží otevře tabuli; po zavření se znovu otevře až po odjezdu od nádraží a návratu
        if (view.now - posledni < 400) return;
        posledni = view.now;
        if (!mhd()) return;
        const [ix, iy] = api.latLonToImg(ST.lat, ST.lon), v = api.getView(), d = Math.hypot(v.x - ix, v.y - iy), scr = view.sx;
        const blizko = scr >= 0.3 && d < 520;
        if (blizko && !BD.open && BD.auto) bdOpen();
        else if (!blizko && (scr < 0.18 || d > 1400)) { if (BD.open) bdClose(false); BD.auto = true; }
      }, { layer: 'top' });
    },
    onDestroy() {
      if (unsubClick) unsubClick(); if (unsubFrame) unsubFrame();
      if (onKey) removeEventListener('keydown', onKey);
      if (boardEl) boardEl.remove();
      unsubClick = unsubFrame = boardEl = onKey = null;
    },
  });
})();
