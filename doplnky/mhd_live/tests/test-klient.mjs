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

// doháněcí model: elFor je inverze profilu, postup nikdy necouvá a dojede cíl
const { elFor, postup } = win.IzomapaMhdLive;
const M2 = { shapes: [{ L: 1000 }] }, trip = [0, 0, 's', 0, [0, 0, 100, 500, 160, 500, 260, 1000]];   // 5 m/s, 60 s stojí na 500 m, pak 5 m/s
assert.equal(elFor(trip, 250, M2), 50); assert.equal(elFor(trip, 500, M2), 100); assert.ok(elFor(trip, 999, M2) > 259 || elFor(trip, 999, M2) > 250);
assert.equal(elFor(trip, 1000, M2), 261);
const b = { sd: 300, v: 10, tgt: 250, tt: 0, vg: 0, tm: 0 };   // před cílem: zpomalí a počká, nikdy necouvne
let prev = b.sd; for (let t = 1000; t <= 20000; t += 50) { const s2 = postup(b, t); assert.ok(s2 >= prev - 1e-9); prev = s2; }
assert.ok(prev >= 300 && prev < 330);
const c = { sd: 0, v: 0, tgt: 400, tt: 0, vg: 10, tm: 0 };       // pozadu: zrychlí, dojede cíl
for (let t = 100; t <= 40000; t += 100) postup(c, t);
assert.ok(c.sd > 400);
console.log('mhd_live dohánění: OK');


// zastávky: extrapolace nepřejede zastávku, stojící vůz se k ní přichytí
{
  const { zastavkyS, cilZastavka } = win.IzomapaMhdLive;
  const tr = [0, 0, 's', 0, [0, 0, 100, 500, 130, 500, 230, 1000], [], [7, 0, 8, 100, 9, 230]];
  const zs = zastavkyS(tr); assert.deepEqual([...zs], [500, 1000]);
  const c1 = cilZastavka(zs, 300, 10, 550); assert.equal(c1.cap, 499); assert.equal(c1.tgt, 499);
  const c2 = cilZastavka(zs, 300, 10, 400); assert.equal(c2.cap, null); assert.equal(c2.tgt, 400);
  const c3 = cilZastavka(zs, 488, 0, 488); assert.equal(c3.tgt, 500); assert.equal(c3.cap, null);   // stojí 12 m před zastávkou: přichytit
  const c4 = cilZastavka(zs, 440, 0, 440); assert.equal(c4.tgt, 440);                              // stojí 60 m před: třeba semafor
  const bz = { sd: 300, v: 8, tgt: c1.tgt, tt: 0, vg: 8, tm: 0, cap: c1.cap };
  let vmax = 0; for (let t = 100; t <= 20000; t += 50) { postup(bz, t); }
  assert.ok(bz.sd <= 500 && bz.sd > 480, 'dojede na zastávku a zastaví: ' + bz.sd); assert.ok(bz.v < 0.3);
  const bp = { sd: 300, v: 8, tgt: 300, tt: 0, vg: 8, tm: 0, cap: 499 };   // po 22 s bez záznamu se strop uvolní
  for (let t = 100; t <= 40000; t += 50) postup(bp, t); assert.ok(bp.sd > 500 || bp.v === 0);
}
console.log('mhd_live zastávky: OK');

// zácpa: stojí ≥ 60 s mimo zastávku/semafor/přejezd; u zastávky ani při jízdě ne
{
  const Ms = { stops: [['Zastávka', 500, 0, 0]], routes: [['15', 3]], trips: [[0]] };
  const apiS = { getPluginData: () => ({}), getMhd: () => Ms, getSignals: () => [[900, 0, 1]], getXings: () => [{ x: 1300, y: 0 }], getRoads: () => [{ w: [[1600, 0], [1700, 0]] }, { w: [[1600, 0], [1600, 90]] }, { w: [[1500, 0], [1600, 0]] }], latLonToWorld: (a, b) => [b, a] };
  const inst = win.IzomapaMhdLive.create(apiS, {});
  const S = inst.state, t0 = 1e6;
  const stojim = (x, sp, t, ag = 0) => inst.jamUpdate(0, { sp, ag }, x, 0, t, Ms);
  S.match.set(0, { last: t0 + 100e3 }); S.junc = null;
  for (const [x, nazev, ocekavano] of [[100, 'zácpa', true], [510, 'u zastávky', false], [880, 'u semaforu', false], [1290, 'u přejezdu', false], [1610, 'u křižovatky', false]]) {
    S.jam.clear(); stojim(x, 0, t0); stojim(x, 0, t0 + 60e3); assert.ok(!inst.zacpa(0, t0 + 61e3), nazev + ': po 60 s ještě ne');
    stojim(x, 0, t0 + 100e3); assert.equal(!!inst.zacpa(0, t0 + 101e3), ocekavano, nazev);
  }
  S.jam.clear(); stojim(100, 0, t0); stojim(100, 0, t0 + 100e3); assert.ok(inst.zacpa(0, t0 + 101e3));
  stojim(100, 20, t0 + 110e3); assert.ok(!inst.zacpa(0, t0 + 111e3), 'rozjel se: zácpa končí');
  assert.equal(inst.cardNote(0, t0 + 111e3), null);   // po rozjetí bez poznámky
  S.jam.clear(); stojim(100, 0, t0); stojim(100, 0, t0 + 100e3); assert.match(inst.cardNote(0, t0 + 101e3), /zácpě :\(/);
  console.log('mhd_live zácpa: OK');
}
