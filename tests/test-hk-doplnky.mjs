// Doplňky hk_zapasy a odjezdova_tabule: načtení do mock window.Izomapa, registrace hooků a základní chování (bez prohlížeče).
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cfg = (id) => JSON.parse(fs.readFileSync(path.join(ROOT, `assets/doplnky/${id}.json`), 'utf8'));

function el(tag) {
  const e = { tagName: tag, children: [], style: {}, dataset: {}, className: '', textContent: '', _l: {}, hidden: false,
    append(...c) { this.children.push(...c); }, appendChild(c) { this.children.push(c); return c; }, replaceChildren(...c) { this.children = c; },
    addEventListener(t, f) { (this._l[t] ||= []).push(f); }, setAttribute() {}, getAnimations() { return []; }, remove() { this.removed = true; }, click() { for (const f of this._l.click || []) f({}); },
    set innerHTML(v) { this.children = [el('i'), el('i'), el('i'), el('i')].map((c) => { c.firstChild = el('b'); return c; }); } };
  return e;
}

function nacti(id, extra = {}) {
  const reg = {}, hooks = { frame: [], card: [], bclick: [] }, body = el('body'), doc = { body, createElement: el, getElementById: () => null, hidden: false };
  const api = {
    getPluginData: () => cfg(id), latLonToWorld: (la, lo) => [lo * 100, la * 100], latLonToImg: () => [0, 0], toImg: (x, y) => [x, y], gz: () => 0, depth: () => 0,
    getEnvironment: () => ({ weather: 'clear', night: 0 }), getView: () => ({ x: 0, y: 0, zoom: 1 }), getMhd: () => null, departures: () => [],
    onFrame(fn, o) { hooks.frame.push({ fn, o }); return () => {}; }, onCard(fn) { hooks.card.push(fn); return () => {}; },
    onBuildingClick(fn, o) { hooks.bclick.push({ fn, o }); return () => {}; }, ...extra,
  };
  const zapasy = { zapasy: [{ doma: true, t: new Date(Date.now() + 864e5).toISOString(), datum: '2030-01-01', domaci: 'FC Hradec Králové', hoste: 'SK Slavia Praha', soutez: 'Liga', kolo: '1. kolo' }] };
  const ctx = vm.createContext({ window: { Izomapa: { registerPlugin(i, inst) { reg[i] = inst; } } }, document: doc, console, Date, Math, Intl, JSON, Promise, Set, Object, Array, RegExp, String, Number,
    setTimeout, setInterval, clearInterval, matchMedia: () => ({ matches: true }), addEventListener() {}, removeEventListener() {},
    fetch: async () => ({ ok: true, json: async () => zapasy }) });
  vm.runInContext(fs.readFileSync(path.join(ROOT, `doplnky/${id}/${id}.js`), 'utf8'), ctx, { filename: `${id}.js` });
  assert.ok(reg[id], `${id}: registerPlugin`);
  reg[id].onInit(api);
  return { reg: reg[id], hooks, body };
}

// hk_zapasy: vrstva world + karta jen u arény
{
  const { reg, hooks } = nacti('hk_zapasy');
  assert.equal(hooks.frame.length, 1);
  assert.equal(hooks.frame[0].o.layer, 'world');
  assert.equal(hooks.card.length, 1);
  const cizi = el('div'); hooks.card[0]({ title: 'Bílá věž', el: cizi });
  assert.equal(cizi.children.length, 0, 'cizí karta se nemění');
  const ar = el('div'); hooks.card[0]({ title: 'Malšovická aréna', el: ar });
  assert.equal(ar.children.length, 1, 'karta arény dostane rozpis');
  await new Promise((r) => setTimeout(r, 50));
  assert.ok(ar.children[0].children.length > 1, 'po načtení dat se rozpis vykreslí');
  reg.onDestroy();
}

// odjezdova_tabule: tabule v DOM, klik na jinou budovu ani nádraží bez jízdních řádů kartu nepotlačí
{
  const { reg, hooks, body } = nacti('odjezdova_tabule');
  assert.equal(body.children.length, 1);
  assert.equal(body.children[0].id, 'board');
  assert.equal(body.children[0].hidden, true);
  assert.equal(hooks.bclick.length, 1);
  assert.equal(hooks.bclick[0].fn({ name: 'Bílá věž' }), false);
  assert.equal(hooks.bclick[0].fn({ name: 'Hradec Králové hlavní nádraží' }), false, 'bez MHD se karta otevře jako dřív');
  assert.equal(hooks.frame.length, 1);
  reg.onDestroy();
  assert.ok(body.children[0].removed);
}

// s jízdními řády: klik na nádraží otevře tabuli a potlačí kartu
{
  const mhd = { names: ['Hradec Králové hlavní nádraží (kolej 1)', 'Praha hl.n.'], routes: [['R 10', 2]], trips: [[0, 0, 0, 0, [], 1, [0, 0, 1, 60]]] };
  const { reg, hooks, body } = nacti('odjezdova_tabule', { getMhd: () => mhd, departures: () => [[600, mhd.trips[0]]] });
  assert.equal(hooks.bclick[0].fn({ name: 'Hradec Králové hlavní nádraží' }), true);
  assert.equal(body.children[0].hidden, false);
  assert.equal(hooks.bclick[0].fn({ name: 'Bílá věž' }), false);
  reg.onDestroy();
}
console.log('test-hk-doplnky OK');
process.exit(0);
