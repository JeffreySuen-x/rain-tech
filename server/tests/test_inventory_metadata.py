import json
from pathlib import Path
import unittest
from server import agriculture_live_demo as live

_CATALOG = Path(__file__).resolve().parent / 'fixtures/device-catalog.json'


class InventoryMetadataTests(unittest.TestCase):
    def test_verified_sources_and_device_purposes(self):
        catalog=json.loads(_CATALOG.read_text(encoding='utf-8'))
        expected={d['id']:d['sources'] for d in catalog['devices']}
        state={'plotIds':['p'],'samples':[dict(plotId='p',observedAt=123,temperature=25.4,humidity=68,soil_moisture=42)],'sampleSequence':1}
        result=live.inventory(state,{'status':'paused'},{'p'})
        self.assertEqual(len(result),8);self.assertEqual(len({d['summary'] for d in result}),8)
        for item in result:
            key={'frost-fan':'frost','multispectral-drone':'drone'}.get(item['kind'],item['kind'])
            self.assertEqual(item['sources'],expected[key])
            self.assertEqual(item['status'],'paused');self.assertEqual(item['observedAt'],123)
            self.assertEqual(item['origin'],'demo');self.assertNotIn('确定性模拟',item['summary'])
