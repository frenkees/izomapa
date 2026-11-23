(() => {
  const PLUGIN_ID = 'hlaseni';
  const Izomapa = window.Izomapa;
  if (!Izomapa) return;

  // Čisté pomocné funkce (testují se bez prohlížeče)
  const MIN_ZNAKU = 3;
  const telo = (cil, note, hp, url, foto) => ({ ...cil, note: String(note || '').trim(), hp: hp || '', url: url || '', foto: foto || null });
  const teloDoplneni = (potvrzeni, foto, email) => ({ doplnit: potvrzeni.cislo, podpis: potvrzeni.podpis, foto, email });
  const poznamkaOk = (note) => String(note || '').trim().length >= MIN_ZNAKU;
  const zpravaDoplneni = (d) => 'Díky! ' + [d.foto && 'Fotku máme', d.email && 'e-mail jsme si poznamenali'].filter(Boolean).join(', ') + '.';

  const HTML_FORM = `
      <input id="repWeb" name="web" type="text" tabindex="-1" autocomplete="off" aria-hidden="true">
      <input id="repFoto" type="file" accept="image/*" aria-label="Fotka (nepovinná)" hidden>
      <button class="px-btn" type="button" id="repFotoBtn">📷 Přidat fotku</button>
      <span id="repFotoNazev" hidden></span>`;
  const HTML_AFTER = `
      <b id="repAfterH">Chcete k hlášení přidat fotku?</b>
      <div id="repAfterFoto"><input id="repFoto2" type="file" accept="image/*" aria-label="Fotka"></div>
      <b>A chcete dostat poděkování a zprávu, až to vyřešíme?</b>
      <input id="repEmail" type="email" autocomplete="email" maxlength="254" placeholder="váš e-mail (nepovinné)">
      <small>Fotka i e-mail se ukládají soukromě, nikde se nezveřejňují. E-mail použijeme jen k poděkování a zprávě o stavu tohoto hlášení.</small>
      <div class="row"><button class="px-btn" type="button" id="repAfterOk">Odeslat doplnění</button><button class="px-btn" type="button" id="repAfterNo">Ne, děkuji</button></div>`;

  let offCard = null, cleanup = [];

  Izomapa.registerPlugin(PLUGIN_ID, {
    _test: { telo, teloDoplneni, poznamkaOk, zpravaDoplneni },
    onInit(api) {
      const cfg = api.getPluginConfig(PLUGIN_ID) || {};
      const API = cfg.api || 'api/report';
      const MAX = Number(cfg.max_strana) || 1600;
      const $ = (id) => document.getElementById(id);
      const wrap = $('report'), form = $('reportForm');
      if (!wrap || !form || !$('repNote') || !$('repMsg')) { console.warn('hlaseni: chybí formulář hlášení v kartě'); return; }
      if ($('repWeb')) return;   // už nainstalováno

      // DOM: honeypot a fotka před tlačítko Odeslat, panel doplnění za formulář
      const submitBtn = form.querySelector('button[type=submit]');
      const tmp = document.createElement('div'); tmp.innerHTML = HTML_FORM;
      while (tmp.firstChild) form.insertBefore(tmp.firstChild, submitBtn);
      const after = document.createElement('div');
      after.className = 'rep-after'; after.id = 'repAfter'; after.hidden = true; after.innerHTML = HTML_AFTER;
      form.after(after);

      const msg = (t, cls) => { $('repMsg').textContent = t; $('repMsg').className = cls ? 'rep-' + cls : ''; };
      let repFoto = null, potvrzeni = null;
      const on = (el, ev, fn, opt) => { el.addEventListener(ev, fn, opt); cleanup.push(() => el.removeEventListener(ev, fn, opt)); };

      // fotka: zmenšit v prohlížeči (delší strana max 1600 px, JPEG), aby se vešla do limitu požadavku
      async function zmensiFotku(file) {
        if (!file || !/^image\//.test(file.type)) return null;
        const bmp = await createImageBitmap(file).catch(() => null); if (!bmp) return null;
        const k = Math.min(1, MAX / Math.max(bmp.width, bmp.height)), c = document.createElement('canvas');
        c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
        c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
        let q = .85, u = c.toDataURL('image/jpeg', q);
        while (u.length > 3.8e6 && q > .4) { q -= .15; u = c.toDataURL('image/jpeg', q); }   // base64 ≈ 4/3 velikosti, server bere do ~3,5 MB souboru
        return u.length > 4.6e6 ? null : u;
      }
      const post = async (body) => {
        const r = await fetch(API, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
        return r.json().catch(() => ({}));
      };
      const reset = () => {
        msg('', ''); $('repNote').value = ''; $('repWeb').value = ''; after.hidden = true; form.hidden = false;
        repFoto = null; potvrzeni = null; $('repFoto').value = ''; $('repFotoNazev').hidden = true; $('repFotoNazev').textContent = '';
        if (submitBtn) submitBtn.disabled = false;
      };

      on($('repFotoBtn'), 'click', () => $('repFoto').click());
      on($('repFoto'), 'change', async () => {
        const f = $('repFoto').files[0]; repFoto = f ? await zmensiFotku(f) : null;
        $('repFotoNazev').hidden = !f; $('repFotoNazev').textContent = f ? (repFoto ? '✓ ' + f.name : 'Tuto fotku se nepodařilo načíst') : '';
      });

      on($('repAfterNo'), 'click', () => { after.hidden = true; wrap.open = false; });
      on($('repAfterOk'), 'click', async () => {
        const f = $('repFoto2').files[0], email = $('repEmail').value.trim();
        const foto = f ? await zmensiFotku(f) : null;
        if (f && !foto) { msg('Fotku se nepodařilo načíst, zkuste jinou.', 'err'); return; }
        if (!foto && !email) { after.hidden = true; return; }
        if (!potvrzeni) return;
        $('repAfterOk').disabled = true; msg('Odesílám…', '');
        try {
          const d = await post(teloDoplneni(potvrzeni, foto, email));
          if (d.ok) { after.hidden = true; msg(zpravaDoplneni(d), 'ok'); }
          else msg(d.msg || 'Doplnění se nepovedlo.', 'err');
        } catch { msg('Doplnění teď nejde odeslat. Zkuste to prosím později.', 'err'); }
        $('repAfterOk').disabled = false;
      });

      // odeslání hlášení: zachytíme na kartě dřív než jádro (fáze capture na předku formuláře) a jádro nepustíme
      on(wrap, 'submit', async (e) => {
        if (e.target !== form) return;
        e.preventDefault(); e.stopImmediatePropagation();
        const cil = api.getReportTarget();
        if (!cil) return;
        if (!poznamkaOk($('repNote').value)) { msg('Napište prosím, co tu nesedí (aspoň pár slov).', 'err'); return; }
        if (submitBtn) submitBtn.disabled = true;
        msg('Odesílám…', '');
        try {
          const d = await post(telo(cil, $('repNote').value, $('repWeb').value, location.href, repFoto));
          if (d.ok) {
            $('repNote').value = ''; repFoto = null; $('repFoto').value = ''; $('repFotoNazev').hidden = true;
            msg('Díky! Hlášení je odeslané' + (d.cislo ? ` (č. ${d.cislo}).` : '.'), 'ok');
            if (d.soukrome && d.cislo) {                      // po potvrzení vybídnout k fotce a e-mailu (soukromé úložiště je zapnuté)
              potvrzeni = { cislo: d.cislo, podpis: d.podpis };
              $('repAfterFoto').hidden = !!d.foto; $('repAfterH').hidden = !!d.foto; $('repFoto2').value = ''; $('repEmail').value = '';
              after.hidden = false;
            }
          } else msg(d.msg || 'Hlášení se nepovedlo odeslat. Zkuste to prosím za chvíli.', 'err');
        } catch { msg('Hlášení teď nejde odeslat (bez připojení?). Zkuste to prosím později.', 'err'); }
        if (submitBtn) submitBtn.disabled = false;
      }, true);

      offCard = api.onCard(reset);   // nová karta = nový cíl hlášení, čistý formulář
    },
    onDestroy() {
      if (offCard) offCard(); offCard = null;
      for (const f of cleanup) f(); cleanup = [];
      for (const id of ['repWeb', 'repFoto', 'repFotoBtn', 'repFotoNazev', 'repAfter']) document.getElementById(id)?.remove();
    },
  });
})();
