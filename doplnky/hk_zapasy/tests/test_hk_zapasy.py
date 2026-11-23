import json
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
ROOT = PLUGIN_DIR.parents[1]
sys.path.insert(0, str(ROOT))

import plugins  # noqa: E402


def _spust(tmp, plugin_cfg):
    tmp = Path(tmp)
    (tmp / 'assets/doplnky').mkdir(parents=True)
    (tmp / 'assets/doplnky/hk_zapasy.json').write_text(json.dumps(plugin_cfg), encoding='utf-8')
    return plugins.load_and_run_plugins({}, {}, lambda a, b, is_world=False: [0, 0], assets_dir=tmp / 'assets', site_dir=tmp / 'site',
                                        build_dir=tmp / 'build', plugins_dir=ROOT / 'doplnky', libs_dir=ROOT / 'knihovny')


class TestHkZapasy(unittest.TestCase):
    def test_manifest_a_klient_pouziva_jen_verejne_api(self):
        m = json.loads((PLUGIN_DIR / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(m['id'], 'hk_zapasy')
        self.assertEqual(m['scripts'], ['hk_zapasy.js'])
        js = (PLUGIN_DIR / 'hk_zapasy.js').read_text(encoding='utf-8')
        for token in ('Izomapa.registerPlugin', "layer: 'world'", 'api.onCard', 'latLonToWorld', 'api.depth', 'getEnvironment', 'onDestroy', 'getPluginData'):
            self.assertIn(token, js)
        for zakazano in ('IZOMAPA_PLUGINS', 'api.state', 'api.local('):
            self.assertNotIn(zakazano, js)

    def test_konfigurace_mesta_projde_hookem_do_overlay(self):
        cfg = json.loads((ROOT / 'assets/doplnky/hk_zapasy.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as tmp:
            e = _spust(tmp, cfg)['hk_zapasy']
            self.assertEqual(e['data']['arena']['azimut'], 110.4)
            self.assertEqual(len(e['data']['arena']['stozary']), 4)
            self.assertIn('api/zapasy', e['data']['zdroje'])
            self.assertTrue((Path(tmp) / 'site/doplnky/hk_zapasy/hk_zapasy.js').is_file())

    def test_vypnuty_doplnek_se_preskoci(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertNotIn('hk_zapasy', _spust(tmp, {'enabled': False, 'arena': {'lat': 1, 'lon': 2}}))


if __name__ == '__main__':
    unittest.main()
