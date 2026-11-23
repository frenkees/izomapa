# Vzorový doplněk (`vzor_doplnku`)

Minimální klientská šablona doplňku pro systém doplňků a knihoven v Izomapě.

## Jak vyzkoušet

1. Zkopíruj složku vzoru do `doplnky/vzor_doplnku/`.
2. Zkopíruj `vzor_doplnku.sample.json` do `assets/doplnky/vzor_doplnku.json` (tím se doplněk automaticky zapne; případně ho nastav v `assets/doplnky.json` podle `priklady/doplnky.sample.json`).
3. Spusť `python overlay.py` a otevři náhled mapy (`npm run nahled`).

## Soubory doplňku (`doplnky/<id>/`)

- `manifest.json`: definice ID, `hook` (výchozí `overlay_hook.py`), `libs` (seznam knihoven z `knihovny/`), `scripts`, `styles` a volitelných `defaults`.
- `overlay_hook.py`: volitelný build-time hook `build_overlay(ctx)`:
  - `ctx` obsahuje: `plugin_id`, `plugin_config`, `mesto`, `cam`, `project_xy(lat, lon)`, `assets_dir`, `data_file` (`assets/doplnky/<id>.json`), `plugin_dir`, `site_dir`, `build_dir`.
  - Vrací `dict` (uloží se do `site/overlay.json` pod `doplnky.<id>.data`) nebo `False`/`None` (doplněk se přeskočí a jeho assety ani knihovny se na web nekopírují).
- `vzor.js` + `vzor.css`: klientská část registrovaná přes `window.Izomapa.registerPlugin(id, { onInit(api), onDestroy() })`.

## Sdílené knihovny (`knihovny/<lib>/`)

- Každá knihovna leží v `knihovny/<lib>/<lib>.js` (volitelně i `<lib>.css`), bez vlastního manifestu.
- Registruje se přes `Izomapa.registerLib('<lib>', api)` a doplněk ji získá přes `api.getLib('<lib>')`.
- Zavaděč knihovnu zkopíruje do `site/doplnky/_libs/<lib>/` a načte ji do prohlížeče **nejvýš 1× a vždy před skripty doplňků** (pouze pokud ji alespoň jeden aktivní doplněk uvede v `"libs"`).

## Přehled `window.Izomapa`

- **Data a konfigurace:** `getPluginData(id)`, `getPluginConfig(id)`, `getLib(id)`, `registerLib(id, api)`
- **Vstupy a UI:** `onMapClick(fn, { priority })` *(vrať `true` pro zachycení kliknutí)*, `setClickCapture(en)`, `setCursor(cur)`, `setPinsVisible(vis)`, `getUiSlot('sidebar-tabs')`, `getPluginLayer(id)`
- **Pohled a prostředí:** `getView()`, `panTo(x, y, zoom, animated)`, `getEnvironment()`, `setEnvironment({ season, weather, rain, night, realTime, realWeather })`
- **Animační plátno:** `onFrame((ctx, view, t) => ..., { layer = 'sky', priority = 0 })` *(vrstvy `'ground'` na zemi pod vozidly, `'world'` před mraky/počasím, `'sky'` nad mraky před popisky/počasím, `'top'` navrch; `view` obsahuje `sx, ox, oy, cw, ch, dpr, dt, now, moving, night, season, weather, snowy, wind, eco, toScreen(ix, iy), vis(ix, iy, m)`)*
- **Převody souřadnic:** `getCam()`, `toImg(x, y, h)`, `imgToWorld(ix, iy)`, `gz(x, y)`, `latLonToWorld(lat, lon)`, `worldToLatLon(x, y)`, `latLonToImg(lat, lon, hOffset)`, `depth(x, y, h)` *(větší = dál od diváka)*, `isOccluded(x, y, h)` *(bod je za budovou)*
- **Karta a budovy:** `getUiSlot('karta')` *(prostor v kartě, vyprázdní se při každém otevření)*, `onCard(fn)` *(`fn({ title, text, lon, lat, k, building, el })` po otevření karty)*, `onBuildingClick(fn, { priority })` *(vrať `true` a karta se neotevře)*, `getReportTarget()` *(cíl hlášení otevřené karty pro vlastní formulář)*, `getUiSlot('vrstvy')` *(přepínače Vrstvy v menu)*
- **Vrstvy dlaždic:** `addTileLayer(id, { variant(season, l), light })` *(přídavná varianta z `tiles.json` nad čtverci, jako vánoční výzdoba; vrací `{ refresh(), remove() }`)*, `hasTileVariant(name)`
- **Doprava a MHD:** `setTrafficHook({ share(r, dir), speed(r, dir) })` *(násobek podílu jedoucích aut a jejich rychlosti na kusu silnice, volá se pro každé auto v každém snímku)*, `getRoads()`, `getMhd()`, `departures(stops, { trains, horizon })`
