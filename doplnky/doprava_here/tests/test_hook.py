"""Testy build hooku doplňku doprava_here (syntetické registry úseků, žádná síť ani klíče)."""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
ROOT = PLUGIN_DIR.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'nastroje'))
import here_doprava as H  # noqa: E402
import tomtom_doprava as T  # noqa: E402
import plugins  # noqa: E402


def _hook():
    spec = importlib.util.spec_from_file_location('_dh_hook', PLUGIN_DIR / 'overlay_hook.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


class TestHook(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / 'site/overlay').mkdir(parents=True)
        (self.tmp / 'assets/doplnky').mkdir(parents=True)
        # úsek HERE rovnoběžný s osou x, jede po směru (od x=0 do x=100); TomTom úsek proti směru
        (self.tmp / 'here.json').write_text(json.dumps({'seg': [{'k': 'a,b,100', 'n': '', 'w': [[0, 0], [100, 0]]}]}))
        (self.tmp / 'tt.json').write_text(json.dumps({'seg': [{'k': 'c,d,100', 'n': '', 'w': [[100, 1], [0, 1]]}]}))
        self.old = (H.REG, T.REG); H.REG = str(self.tmp / 'here.json'); T.REG = str(self.tmp / 'tt.json')
        roads = [{'w': [[0, 0], [100, 0]], 'c': 'primary'}, {'w': [[0, 500], [100, 500]], 'c': 'primary'},
                 {'w': [[0, 0], [100, 0]], 'c': 'footway'}]
        (self.tmp / 'site/overlay/c0_0.json').write_text(json.dumps({'roads': roads, 'buildings': []}))

    def tearDown(self):
        H.REG, T.REG = self.old; shutil.rmtree(self.tmp, ignore_errors=True)

    def ctx(self):
        return {'plugin_dir': PLUGIN_DIR, 'data_file': self.tmp / 'assets/doplnky/doprava_here.json', 'site_dir': self.tmp / 'site'}

    def test_bez_konfigurace_se_preskoci(self):
        self.assertIs(_hook().build_overlay(self.ctx()), False)

    def test_vypnuto(self):
        self.ctx()['data_file'].write_text('{"enabled": false}')
        self.assertIs(_hook().build_overlay(self.ctx()), False)

    def test_prirazeni_useku_a_ids(self):
        self.ctx()['data_file'].write_text('{"zive_s": 120}')
        out = _hook().build_overlay(self.ctx())
        self.assertEqual(out['zive_s'], 120); self.assertEqual(out['min_podil'], 0.35)
        d = json.loads((self.tmp / 'site/overlay/c0_0.json').read_text())
        r = d['roads']
        self.assertEqual(r[0]['h'], [0, (T.ID_POSUN + 0) * 2 + 1])      # HERE po směru, TomTom proti směru kusu
        self.assertNotIn('h', r[1]); self.assertNotIn('h', r[2])         # daleko od úseků; chodník se nepřiřazuje
        ids = json.loads((self.tmp / 'site' / out['ids']).read_text())
        self.assertEqual(ids, {'a,b,100': 0, 'c,d,100': T.ID_POSUN})
        self.assertEqual(len(out['ids_v']), 8)

    def test_opakovany_beh_je_idempotentni(self):
        self.ctx()['data_file'].write_text('{}')
        _hook().build_overlay(self.ctx()); a = (self.tmp / 'site/overlay/c0_0.json').read_text()
        _hook().build_overlay(self.ctx()); self.assertEqual(a, (self.tmp / 'site/overlay/c0_0.json').read_text())

    def test_zavadec_doplnku(self):
        """přes plugins.load_and_run_plugins: manifest, kopie skriptu, data v sekci doplnky"""
        self.ctx()['data_file'].write_text('{}')
        res = plugins.load_and_run_plugins({}, {}, lambda *a: [0, 0], assets_dir=self.tmp / 'assets', site_dir=self.tmp / 'site',
                                           build_dir=self.tmp / 'build', plugins_dir=PLUGIN_DIR.parent, libs_dir=ROOT / 'knihovny')
        e = res['doprava_here']
        self.assertEqual(e['scripts'], ['doplnky/doprava_here/doprava_here.js'])
        self.assertTrue((self.tmp / 'site/doplnky/doprava_here/doprava_here.js').is_file())
        self.assertEqual(e['data']['ids'], 'doplnky/doprava_here/doprava_id.json')


if __name__ == '__main__':
    unittest.main()
