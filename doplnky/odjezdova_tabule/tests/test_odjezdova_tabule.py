import json
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
ROOT = PLUGIN_DIR.parents[1]
sys.path.insert(0, str(ROOT))

import plugins  # noqa: E402


class TestOdjezdovaTabule(unittest.TestCase):
    def test_soubory_a_klient(self):
        m = json.loads((PLUGIN_DIR / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(m['scripts'], ['odjezdova_tabule.js'])
        self.assertEqual(m['styles'], ['odjezdova_tabule.css'])
        js = (PLUGIN_DIR / 'odjezdova_tabule.js').read_text(encoding='utf-8')
        for token in ('Izomapa.registerPlugin', 'api.onBuildingClick', 'api.departures', 'trains: true', 'api.getMhd', 'api.onFrame', 'latLonToImg', 'onDestroy'):
            self.assertIn(token, js)
        css = (PLUGIN_DIR / 'odjezdova_tabule.css').read_text(encoding='utf-8')
        for sel in ('.board', '.fl', '.bd-head', '.bd-row'):
            self.assertIn(sel, css)

    def test_hook_preda_stanici_a_zkopiruje_assety(self):
        cfg = json.loads((ROOT / 'assets/doplnky/odjezdova_tabule.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'assets/doplnky').mkdir(parents=True)
            (tmp / 'assets/doplnky/odjezdova_tabule.json').write_text(json.dumps(cfg), encoding='utf-8')
            out = plugins.load_and_run_plugins({}, {}, lambda a, b, is_world=False: [0, 0], assets_dir=tmp / 'assets', site_dir=tmp / 'site',
                                                build_dir=tmp / 'build', plugins_dir=ROOT / 'doplnky', libs_dir=ROOT / 'knihovny')
            e = out['odjezdova_tabule']
            self.assertAlmostEqual(e['data']['stanice']['lat'], 50.214528)
            self.assertEqual(e['data']['sirky'], [5, 8, 15, 2])
            self.assertEqual(e['styles'], ['doplnky/odjezdova_tabule/odjezdova_tabule.css'])
            self.assertTrue((tmp / 'site/doplnky/odjezdova_tabule/odjezdova_tabule.js').is_file())


if __name__ == '__main__':
    unittest.main()
