// Test doplňku mhd_live: kategorie zpoždění a párování živých vozidel na spoje (mock window.Izomapa)
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const src = fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'mhd_live.js'), 'utf8');
const win = { Izomapa: { registerPlugin() {} } };
vm.runInNewContext(src, { window: win, document: {}, console, Math, Date, Object, Map, Set, String, Number, Array, setInterval() {}, clearInterval() {}, localStorage: {} });
const { parovani, kat } = win.IzomapaMhdLive;

assert.equal(kat(0), 'g'); assert.equal(kat(59), 'g'); assert.equal(kat(60), 'y'); assert.equal(kat(119), 'y');
assert.equal(kat(120), 'o'); assert.equal(kat(179), 'o'); assert.equal(kat(180), 'r'); assert.equal(kat(900), 'r'); assert.equal(kat(null), 'n'); assert.equal(kat(-30), 'g');

// jedna linka "1", trasa přímo na východ 10 m/s, dva spoje po 600 s; vozidlo je o 120 s pozadu
const M = { routes: [['1', 11]], trips: [[0], [0]], dur: [1000, 1000] };
const api = {
  latLonToWorld: (la, lo) => [lo, la],
  mhdPos: (trip, el) => ({ x: el * 10, y: 0, dx: 1, dy: 0 }),
};
// spoj 0 vyjel před 500 s (podle JŘ je na x = 5000), spoj 1 před 100 s (x = 1000); vozidlo hlásí zpoždění 120 s a je na x = 3800
const raw = [[0, 500], [1, -500 + 600]];
const v = { id: '065', ln: '1', la: 0, lo: 3800, az: 90, d: 120 };
const r = parovani([v], [[0, 500], [1, 100]], M, api);
assert.equal(r.match.size, 1); assert.ok(r.match.has(0)); assert.equal(r.match.get(0).id, '065');
assert.ok(Math.abs(r.match.get(0).d - 120) <= 90); assert.equal(r.free.length, 0);
// opačný směr: neodpovídá, vozidlo zůstane volné
const r2 = parovani([{ ...v, az: 270 }], [[0, 500]], M, api);
assert.equal(r2.match.size, 0); assert.equal(r2.free.length, 1);
// jiná linka se nepáruje
assert.equal(parovani([{ ...v, ln: '9' }], [[0, 500]], M, api).match.size, 0);
console.log('mhd_live: OK');
