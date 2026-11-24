  window.Izomapa = {
    libs: pluginLibs,
    registerLib(id, api) { if (id) pluginLibs[id] = api; },
    getLib: (id) => pluginLibs[id] ?? null,
    getPluginData: (id) => OV.doplnky?.[id]?.data ?? null,
    getPluginConfig: (id) => OV.doplnky?.[id]?.config ?? {},
    registerPlugin(id, inst) {
      if (pluginRegistry[id]?.onDestroy) try { pluginRegistry[id].onDestroy(); } catch {}
      pluginRegistry[id] = inst || {};
      if (inst?.onInit) { if (ready) inst.onInit(window.Izomapa); else layersReady.then(() => inst.onInit(window.Izomapa)); }
    },
    onMapClick(fn, options = { priority: 0 }) {
      const entry = { fn, priority: options?.priority ?? 0 };
      pluginClicks.push(entry); pluginClicks.sort((a, b) => b.priority - a.priority);
      return () => { const i = pluginClicks.indexOf(entry); if (i >= 0) pluginClicks.splice(i, 1); };
    },
    onFrame(fn, options = {}) {
      if (typeof fn !== 'function') return () => {};
      const layer = ['ground', 'world', 'top'].includes(options?.layer) ? options.layer : 'sky';
      const entry = { fn, layer, priority: options?.priority ?? 0 };
      pluginFrames.push(entry); pluginFrames.sort((a, b) => b.priority - a.priority);
      return () => { const i = pluginFrames.indexOf(entry); if (i >= 0) pluginFrames.splice(i, 1); };
    },
    setClickCapture(en) { pluginCapture = Boolean(en); },
    setCursor(cur) { pluginCursor = cur || ''; $('osd').style.cursor = pluginCursor; },
    setPinsVisible(vis) { document.body.classList.toggle('plugins-hide-pins', !vis); },
    getPluginLayer(id) {
      let el = $('pluginLayers').querySelector(`[data-plugin="${id}"]`);
      if (!el) { el = document.createElement('div'); el.dataset.plugin = id; el.style.cssText = 'position:absolute;left:0;top:0;pointer-events:none;'; $('pluginLayers').appendChild(el); }
      return el;
    },
    getView() { const c = viewer.viewport.getCenter(true); return { x: c.x * W, y: c.y * W, zoom: viewer.viewport.getZoom(true) }; },
    getCam: () => ({ ...cam, w: W, h: Hh }),
    toImg: (x, y, h = 0) => toImg(x, y, h),
    imgToWorld: (ix, iy) => imgToWorld(ix, iy),
    gz: (x, y) => gz(x, y),
    depth: (x, y, h = 0) => depth(x, y, h),                // hloubka bodu světa ve směru pohledu (větší = dál od diváka): co kreslit dřív, odvrácená strana
    isOccluded: (x, y, h = 0) => { const [ix, iy] = toImg(x, y, h); return occluded(ix, iy, depth(x, y, h)); },   // bod světa je za budovou
    latLonToWorld: (lat, lon) => [(lon - cam.lon0) * cam.kx, (lat - cam.lat0) * cam.ky],
    worldToLatLon: (x, y) => { const [lon, lat] = lonlat(x, y); return [lat, lon]; },
    latLonToImg: (lat, lon, hOffset = 0) => { const x = (lon - cam.lon0) * cam.kx, y = (lat - cam.lat0) * cam.ky; return toImg(x, y, gz(x, y) + hOffset); },
    panTo(x, y, zoom, animated = true) {
      if (Number.isFinite(x) && Number.isFinite(y)) viewer.viewport.panTo(new OpenSeadragon.Point(x / W, y / W), !animated);
      if (Number.isFinite(zoom)) viewer.viewport.zoomTo(zoom, null, !animated);
    },
    getEnvironment: () => ({ night: state.night, rain: state.weather === 'rain', weather: state.weather, season: state.season, realTime: $('realTime').checked, realWeather: $('realWeather').checked }),
    setEnvironment(env = {}) {
      if (env.season) setSeason(env.season);
      if (env.realWeather !== undefined) { $('realWeather').checked = Boolean(env.realWeather); if (env.realWeather) applyRealWeather(); }
      else if (env.weather !== undefined || env.rain !== undefined) $('realWeather').checked = false;
      const w = env.weather !== undefined ? env.weather : (env.rain !== undefined ? (env.rain ? 'rain' : 'clear') : undefined);
      if (w !== undefined) setWeather(w);
      if (env.realTime !== undefined) { $('realTime').checked = Boolean(env.realTime); if (env.realTime) tickReal(); }
      else if (typeof env.night === 'number') $('realTime').checked = false;
      if (typeof env.night === 'number') { state.night = Math.max(0, Math.min(1, env.night)); $('night').value = Math.round(state.night * 100); applyTime(); }
    },
    // sloty: 'sidebar-tabs' záložky u panelu, 'karta' prostor v kartě pod údaji (vyprázdní se při každém otevření karty, plnit z onCard),
    // 'vrstvy' seznam přepínačů Vrstvy v menu (doplněk si sem přidá vlastní <label><input type="checkbox"> …</label>)
    getUiSlot(slotName = 'sidebar-tabs') { return ({ 'sidebar-tabs': $('pluginTabsSlot'), karta: $('cardExtra'), vrstvy: document.querySelector('.layers') })[slotName] ?? null; },
    // ---------- rozšíření (návrh pro upstream) ----------
    // karta: fn({ title, text, lon, lat, k, building, el }) po každém otevření karty (budova, místo, zastávka); el = slot 'karta'
    onCard(fn) { cardHooks.push(fn); return () => { const i = cardHooks.indexOf(fn); if (i >= 0) cardHooks.splice(i, 1); }; },
    // klik na budovu (i z hledání): fn(b) dostane záznam budovy (id, oid, name, cls, addr, lon, lat, hull, k); vrať true = karta se neotevře
    onBuildingClick(fn, options = {}) {
      const entry = { fn, priority: options?.priority ?? 0 };
      buildingClicks.push(entry); buildingClicks.sort((a, b) => b.priority - a.priority);
      return () => { const i = buildingClicks.indexOf(entry); if (i >= 0) buildingClicks.splice(i, 1); };
    },
    // cíl hlášení nepřesnosti pro otevřenou kartu ({ target: 'b:<oid>' | 'pt:lat,lon', title, lon, lat }), pro vlastní formulář doplňku
    getReportTarget: () => (repTarget ? { ...repTarget } : null),
    // přídavná vrstva dlaždic nad čtverci (vyrábí ji dzi.py jako další variantu v tiles.json, např. plachta_summer):
    // variant(season, l) vrátí název varianty pro období a čtverec, nebo null (vypnuto); light: true = noční světla. refresh() po změně stavu.
    addTileLayer(id, { variant, light = false } = {}) {
      tileExtras.set(id, { variant: variant || (() => null), light }); applyExtras();
      return { refresh: () => applyExtras(), remove: () => { tileExtras.delete(id); applyExtras(); } };
    },
    hasTileVariant: (v) => LAYERS.some((l) => l.src(v)),
    // hustota a rychlost aut: { share(r, dir) -> násobek podílu jedoucích aut (0–1, víc aut než bez doplňku nepřibude), speed(r, dir) -> násobek rychlosti }
    // r = kus silnice z getRoads(), dir 1 / -1 = po / proti směru kusu; volá se pro každé auto v každém snímku (mít to rychlé, kešovat). null = vypnout.
    setTrafficHook(h) { trafficHook = h || null; },
    getRoads: () => roads,                                 // kusy silnic načtených čtverců (w svět m, p obrázek, c třída, o jednosměrka, ln pruhy, k čtverec, L délka a data z overlay)
    // zpoždění spojů: fn(index spoje v MHD.trips) -> zpoždění v s (kladné = spoj je pozadu, vykreslí se na trase „zpět“); volá se jednou za sekundu pro každý spoj, mít to rychlé. null = vypnout.
    setMhdDelayHook(fn) { MHD.delayOf = typeof fn === 'function' ? fn : null; MHD.t = -1; },
    // poloha spoje v každém snímku: fn(i, el, frac) -> čas na jízdním řádu (s od odjezdu), podle něhož se spoj nakreslí (el = hodnota z posledního sekundového kroku, frac = zlomek sekundy od něj); bez háčku el + frac. null = vypnout.
    setMhdElHook(fn) { MHD.elFix = typeof fn === 'function' ? fn : null; },
    // poznámka na kartě spoje: fn(i) -> text (zobrazí se červeně pod údaji o zpoždění) nebo null; volá se při každém otevření/obnovení karty
    setMhdCardNote(fn) { MHD.cardNote = typeof fn === 'function' ? fn : null; },
    getSignals: () => OV.signals || [],                     // semafory [[x, y, křižovatka], …] ve světových metrech
    getXings: () => [...XC.values()].map((c) => ({ x: c.x, y: c.y })),   // železniční přejezdy {x, y} ve světových metrech
    getMhdActive: () => (MHD.on ? MHD.act : []),            // [[i, s od odjezdu (se zpožděním), s do odjezdu na konečné, pořadí ve frontě, zpoždění s], …]
    getMhdRaw: () => (MHD.on ? mhdRaw(true) : []),          // [[i, s od odjezdu podle jízdního řádu], …] i pro spoje s možným zpožděním, kvůli párování živých vozidel
    mhdTripCard: (i) => mhdTripCard(i),                      // karta spoje s malým jízdním řádem (další zastávka a příjezdy se zpožděním), nakreslí i trasu
    mhdPos: (trip, el) => mhdPos(trip, el),                 // poloha spoje el s po odjezdu: {x, y, z, ix, iy, dx, dy}
    getMhd: () => (MHD.on ? MHD : null),                   // jízdní řády z mhd.json (routes, trips, names, stops…), null bez MHD nebo před načtením
    // odjezdy: [[s do odjezdu, spoj z mhd.json trips], …] seřazené; stops = index zastávky (MHD.names) nebo Set indexů
    departures: (stops, { trains = false, horizon = 3600 } = {}) => (MHD.on ? stopDepartures(stops, trains, horizon) : []),
  };
  if (OV.doplnky && Object.keys(OV.doplnky).length) {
    const loadedStyles = new Set(), loadedScripts = new Map();
    const loadStyle = (href) => {
      if (!href || loadedStyles.has(href)) return;
      loadedStyles.add(href);
      const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = href; document.head.appendChild(l);
    };
    const loadScript = (src) => {
      if (!src) return Promise.resolve();
      if (loadedScripts.has(src)) return loadedScripts.get(src);
      const p = new Promise((resolve) => {
        const s = document.createElement('script'); s.src = src; s.async = false;
        s.onload = () => resolve(true);
        s.onerror = () => { console.warn('Nepodařilo se načíst skript doplňku:', src); resolve(false); };
        document.body.appendChild(s);
      });
      loadedScripts.set(src, p);
      return p;
    };
    layersReady.then(async () => {
      const list = Object.values(OV.doplnky);
      const libUrls = [];
      for (const p of list) {
        for (const href of p.lib_styles || []) loadStyle(href);
        for (const src of p.lib_scripts || []) if (!libUrls.includes(src)) libUrls.push(src);
      }
      if (libUrls.length) await Promise.all(libUrls.map(loadScript));
      for (const p of list) {
        for (const href of p.styles || []) loadStyle(href);
        for (const src of p.scripts || []) loadScript(src);
      }
    });
  }
})();
