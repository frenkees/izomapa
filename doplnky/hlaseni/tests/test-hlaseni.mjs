// Test klientského doplňku hlaseni bez prohlížeče: registrace, čisté pomocné funkce, chybějící formulář (spuštění: node doplnky/hlaseni/tests/test-hlaseni.mjs)
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const plugins = {};
const warns = [];
const apiMock = {
  getPluginConfig: () => ({ api: 'api/report' }),
  registerPlugin(id, inst) { plugins[id] = inst; },
  onCard() { throw new Error('bez formuláře se onCard nesmí volat'); },
  getReportTarget: () => null,
};
const ctx = vm.createContext({
  window: { Izomapa: apiMock },
  document: { getElementById: () => null },
  console: { warn: (m) => warns.push(m) },
});
vm.runInContext(fs.readFileSync(path.join(ROOT, 'doplnky/hlaseni/hlaseni.js'), 'utf8'), ctx);
assert.ok(plugins.hlaseni, 'doplněk se registruje jako "hlaseni"');
const t = plugins.hlaseni._test;

assert.equal(t.poznamkaOk('ab'), false);
assert.equal(t.poznamkaOk('  ab  '), false);
assert.equal(t.poznamkaOk('abc'), true);
assert.equal(t.poznamkaOk(null), false);

const cil = { target: 'b:w1', title: 'Bílá věž', lon: 15.83, lat: 50.2 };
assert.deepEqual({ ...t.telo(cil, '  špatná výška ', 'bot', 'http://x/#a', 'data:image/jpeg;base64,AA') },
  { target: 'b:w1', title: 'Bílá věž', lon: 15.83, lat: 50.2, note: 'špatná výška', hp: 'bot', url: 'http://x/#a', foto: 'data:image/jpeg;base64,AA' });
const b = t.telo(cil, 'text', '', 'u', null);
assert.equal(b.hp, ''); assert.equal(b.foto, null);

assert.deepEqual({ ...t.teloDoplneni({ cislo: 12, podpis: 'abc' }, null, 'a@b.cz') }, { doplnit: 12, podpis: 'abc', foto: null, email: 'a@b.cz' });
assert.equal(t.zpravaDoplneni({ foto: true, email: true }), 'Díky! Fotku máme, e-mail jsme si poznamenali.');
assert.equal(t.zpravaDoplneni({ foto: true }), 'Díky! Fotku máme.');

// bez formuláře v kartě se doplněk jen ohlásí a nespadne
plugins.hlaseni.onInit(apiMock);
assert.equal(warns.length, 1);
console.log('test-hlaseni OK');
