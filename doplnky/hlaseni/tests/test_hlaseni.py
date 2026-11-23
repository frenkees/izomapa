import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
ROOT = PLUGIN_DIR.parents[1]
sys.path.insert(0, str(ROOT))

import plugins  # noqa: E402


class TestHlaseni(unittest.TestCase):
    def _spust(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            assets = tmp / 'assets'
            (assets / 'doplnky').mkdir(parents=True)
            if data is not None:
                (assets / 'doplnky' / 'hlaseni.json').write_text(json.dumps(data), encoding='utf-8')
            site = tmp / 'site'
            site.mkdir()
            res = plugins.load_and_run_plugins(
                {}, {}, lambda lat, lon, is_world=False: [0, 0],
                assets_dir=assets, site_dir=site, build_dir=tmp / 'build',
                plugins_dir=ROOT / 'doplnky', libs_dir=ROOT / 'knihovny',
            )
            return res, (site / 'doplnky/hlaseni/hlaseni.js').is_file()

    def test_manifest(self):
        m = json.loads((PLUGIN_DIR / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(m['id'], 'hlaseni')
        self.assertEqual(m['defaults']['api'], 'api/report')
        for f in m['scripts'] + m['styles']:
            self.assertTrue((PLUGIN_DIR / f).is_file(), f)

    def test_vychozi_konfigurace_v_repu(self):
        cfg = json.loads((ROOT / 'assets/doplnky/hlaseni.json').read_text(encoding='utf-8'))
        self.assertEqual(cfg['api'], 'api/report')

    def test_zapnuty_doplnek(self):
        res, zkopirovano = self._spust({'enabled': True, 'api': 'api/report'})
        self.assertIn('hlaseni', res)
        e = res['hlaseni']
        self.assertEqual(e['config']['api'], 'api/report')
        self.assertEqual(e['scripts'], ['doplnky/hlaseni/hlaseni.js'])
        self.assertEqual(e['styles'], ['doplnky/hlaseni/hlaseni.css'])
        self.assertTrue(zkopirovano)

    def test_bez_dat_nebo_vypnuto(self):
        self.assertNotIn('hlaseni', self._spust(None)[0])
        self.assertNotIn('hlaseni', self._spust({'enabled': False})[0])


if __name__ == '__main__':
    unittest.main()
