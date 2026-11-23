// Test klienta doplňku doprava_here: hustota a rychlost aut (setTrafficHook), načtení dat, přepínač Zácpy (mock window.Izomapa)
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const src = fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'doprava_here.js'), 'utf8');
const el = () => { const e = { children: [], options: [], style: {}, checked: false, parentNode: null,
  appendChild(c) { this.children.push(c); if (this.options) this.options.push(c); c.parentNode = this; return c; },
  querySelector(s) { return s === 'select' ? sel : inp; }, remove() { this.removed = true; }, after(n) { this.after_ = n; n.parentNode = this.parentNode; } }; return e; };
const sel = el(), inp = el();
function setup(data, fetchMap) {
  const frames = []; let hook = 'nic', plugin = null; const slot = el(), traffic = el(); traffic.closest = () => ({ parentNode: slot, after(n) { slot.children.push(n); } });
  const roads = [];
  const api = { getPluginData: () => data, getUiSlot: (n) => (n === 'vrstvy' ? slot : null), setTrafficHook: (h) => { hook = h; }, getRoads: () => roads,
    onFrame: (fn, o) => { frames.push({ fn, o }); return () => frames.splice(0); } };
  const doc = { createElement: () => { const e = el(); e.innerHTML = ''; return e; }, getElementById: () => traffic };
  const win = { Izomapa: { registerPlugin: (id, p) => { plugin = p; } } };
  vm.runInNewContext(src, { window: win, document: doc, console, Intl, Date, Math, Object, setInterval: () => 1, clearInterval() {} });
  const mk = win.IzomapaDopravaHere.create(api, doc, async (u) => { const r = fetchMap[u.split('?')[0]]; return { ok: !!r, json: async () => r }; });
  return { mk, frames, roads, get hook() { return hook; }, plugin, api, slot };
}
const cfg = { ids: 'doplnky/doprava_here/doprava_id.json', ids_v: 'abc', rezimy: [{ v: 'live', t: 'živě' }, { v: '7', t: '7 h' }], min_podil: 0.35, j_plny: 6 };
const data = { ids: { 'a,b,1': 5 }, };
const maps = { 'doplnky/doprava_here/doprava_id.json': { 'a,b,1': 5 }, 'api/doprava': { s: { 'a,b,1': [60, 40] } }, 'api/doprava_typicka': { s: { 'a,b,1': Array(48).fill(30) } } };

{ // bez dat: nic se nemění
  const t = setup(cfg, maps), h = t.mk.hook;
  assert.equal(h.share({}, 1), 1); assert.equal(h.speed({}, 1), 1);
  assert.equal(h.share({ h: [10] }, 1), 1, 'úsek bez dat = beze změny');
}
{ // živá data: J 6 = všechna auta (max jako bez doplňku), J 0 = min_podil, J 3 mezi; rychlost podle HERE
  const t = setup(cfg, maps); await t.mk.nactiZive();
  const r = { h: [10] };                                   // úsek 5 po směru (10 = 5*2)
  assert.equal(t.mk.hook.share(r, 1), 1); assert.equal(t.mk.hook.speed(r, 1), 0.4);
  assert.equal(t.mk.hook.share(r, -1), 1, 'opačný směr nemá data');
  t.mk.state.live = new Map([[5, [0, 100]]]); t.mk.state.v++;
  assert.equal(t.mk.hook.share(r, 1), 0.35);
  t.mk.state.live = new Map([[5, [30, 70]]]); t.mk.state.v++;
  assert.ok(Math.abs(t.mk.hook.share(r, 1) - (0.35 + 0.65 * 0.5)) < 1e-9);
  t.mk.state.live = new Map([[5, [100, 10]]]); t.mk.state.v++;
  assert.equal(t.mk.hook.share(r, 1), 1, 'nikdy víc než 1: aut nepřibude');
  const rp = { h: [11] }; t.mk.state.live = new Map([[5, [0, 100]]]); t.mk.state.v++;
  assert.equal(t.mk.hook.share(rp, -1), 0.35, 'lichá čísla = proti směru kusu');
}
{ // start: UI přepínač, hook, vrstva ground; stop vše uklidí
  const t = setup(cfg, maps); t.mk.start();
  assert.equal(t.frames[0].o.layer, 'ground'); assert.equal(typeof t.hook.share, 'function');
  assert.equal(t.slot.children.length, 1, 'přepínač Zácpy ve slotu vrstvy');
  t.mk.stop(); assert.equal(t.hook, null);
}
{ // bez ids (hook nevrátil data): nic se nenastaví
  const t = setup({ ...cfg, ids: undefined }, maps); t.mk.start(); assert.equal(t.hook, 'nic'); assert.equal(t.frames.length, 0);
}
{ // kreslení: čáry jen pro silnice s h a daty
  const t = setup(cfg, maps); await t.mk.nactiZive(); t.mk.state.v++;
  t.roads.push({ h: [10], p: [[0, 0], [100, 0]] }, { p: [[0, 0], [1, 1]] });
  let strokes = 0; const cols = [];
  const ctx = { beginPath() {}, moveTo() {}, lineTo() {}, stroke() { strokes++; cols.push(this.strokeStyle); } };
  t.mk.drawJam(ctx, { ox: 0, oy: 0, cw: 800, ch: 600, sx: 1 });
  assert.equal(strokes, 1); assert.equal(cols[0], '#d8392b');
}
console.log('doprava_here klient: OK');
