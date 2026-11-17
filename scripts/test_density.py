"""Density imports, downloads, source rendering, and same-page display switching."""
import json
import shutil
import struct
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zlib
from http.server import ThreadingHTTPServer
from pathlib import Path

from render import ChromePipe, png_dimensions, render
from server import make_handler
from store import Store


def png(path, width, height, color=(60, 100, 70)):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    row = b'\0' + bytes(color) * width
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(row * height)) + chunk(b'IEND', b''))
    return str(path)


class DensityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.store = Store(self.home)
        self.data = {'title': 'Density example', 'style': 'test', 'page': 'overview', 'component': 'table',
                     'node': 'test:table', 'caption': 'Same layout at both densities.',
                     'image': png(self.home / 'assets/one.png', 640, 360),
                     'steps': [png(self.home / 'assets/step.png', 480, 240)],
                     'image2x': png(self.home / 'assets/one2.png', 1280, 720, (80, 110, 150)),
                     'steps2x': [png(self.home / 'assets/step2.png', 960, 480, (80, 110, 150))],
                     'sources': [{'kind': 'html', 'html': 'private-source.html'}, None]}

    def tearDown(self):
        self.temp.cleanup()

    def test_attach_preserves_review_and_standard_exports(self):
        old = self.store.import_artifact({key: value for key, value in self.data.items() if key not in ['image2x', 'steps2x', 'sources']})
        self.store.add_feedback({'ids': [old['id']], 'reaction': 1, 'text': 'Keep this direction'})
        result = self.store.attach_density(old['id'], self.data['image2x'], self.data['steps2x'], self.data['sources'])
        self.assertEqual(result['image'], old['image'])
        self.assertEqual(result['steps'], old['steps'])
        self.assertEqual(result['dimensions'], [640, 360])
        self.assertEqual(result['stepDimensions'], [[480, 240]])
        self.assertEqual(result['reaction'], 1)
        self.assertTrue(result['reviewed'])
        self.assertEqual(self.store.import_artifact(self.data)['id'], old['id'])
        self.assertEqual(len(self.store.all('artifacts')), 1)
        self.assertEqual(len(self.store.all('feedback')), 1)

    def test_wrong_density_or_frame_alignment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'twice'):
            self.store.import_artifact(dict(self.data, image2x=self.data['image']))
        with self.assertRaisesRegex(ValueError, 'align'):
            self.store.import_artifact(dict(self.data, steps2x=[]))
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.store.import_artifact(dict(self.data, sources=[]))
        self.assertEqual(self.store.all('artifacts'), [])

    def test_partial_density_falls_back_without_inventing_exports(self):
        data = dict(self.data, image2x=None, steps2x=[None])
        item = self.store.import_artifact(data)
        self.assertIsNone(item['image2x'])
        self.assertEqual(item['steps2x'], [None])
        self.store.attach_density(item['id'], image2x=self.data['image2x'])
        result = self.store.attach_density(item['id'], steps2x=self.data['steps2x'])
        self.assertIsNotNone(result['image2x'])
        self.assertIsNotNone(result['steps2x'][0])

    def start_server(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store, 'density-test-token'))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_port}'

    def test_downloads_are_unscaled_named_original_pngs(self):
        item = self.store.import_artifact(self.data)
        base = self.start_server()
        for step, scale, key in [(0, 1, 'image'), (0, 2, 'image2x'), (1, 2, 'steps2x')]:
            filename = item[key][0] if isinstance(item[key], list) else item[key]
            with urllib.request.urlopen(f'{base}/download/{item["id"]}/{step}/{scale}') as response:
                self.assertEqual(response.read(), (self.home / 'assets' / filename).read_bytes())
                self.assertIn('attachment;', response.headers['Content-Disposition'])
                self.assertIn(f'@{scale}x.png', response.headers['Content-Disposition'])
        for suffix in ['-1/1', '0/3', '99/1']:
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(f'{base}/download/{item["id"]}/{suffix}')
            self.assertEqual(error.exception.code, 404)

    @unittest.skipUnless(Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome').exists(), 'Native renderer requires Chrome on macOS')
    def test_native_render_has_exact_css_viewport_at_both_densities(self):
        source = self.home / 'runs/native.html'
        source.write_text('<!doctype html><style>html,body{margin:0}</style><script>document.documentElement.style.background=innerWidth===1000&&innerHeight===600?"#00ff00":"#ff0000"</script>')
        for density in (1, 2):
            # render() checks innerWidth/innerHeight/devicePixelRatio before capture.
            output = render(source, self.home / f'native-{density}.png', 1000, 600, density, self.home)
            self.assertEqual(png_dimensions(output), (1000 * density, 600 * density))
        output = render(source, self.home / 'crop.png', 1000, 600, 2, self.home, (20, 30, 250, 120))
        self.assertEqual(png_dimensions(output), (500, 240))

    @unittest.skipUnless(Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome').exists(), 'Browser integration requires Chrome on macOS')
    def test_same_page_switches_1x_2x_1x_without_changing_layout_or_drafts(self):
        item = self.store.import_artifact(self.data)
        second = self.store.import_artifact(dict(self.data, title='Second design', node='test:second'))
        base = self.start_server()
        browser = ChromePipe(self.home / 'browser-profile')
        self.addCleanup(browser.close)
        target = browser.call('Target.createTarget', {'url': 'about:blank'})['targetId']
        session = browser.call('Target.attachToTarget', {'targetId': target, 'flatten': True})['sessionId']
        browser.call('Page.enable', session=session)

        def js(expression):
            response = browser.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True}, session)
            if response.get('exceptionDetails'):
                self.fail(str(response['exceptionDetails']))
            return response.get('result', {}).get('value')

        def wait_for(expression):
            return js('new Promise((resolve,reject)=>{let attempts=0;const check=()=>{if(' + expression + ')resolve(true);else if(++attempts>150)reject(new Error("UI condition timed out"));else setTimeout(check,20)};check()})')

        def density(value):
            browser.call('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1000, 'deviceScaleFactor': value, 'mobile': False}, session)
            try:
                wait_for(f'[...document.querySelectorAll("img[data-image-standard]")].every(image=>image.complete && image.dataset.renderDensity==="{value}")')
            except AssertionError:
                self.fail(str(js('({ratio:devicePixelRatio,images:[...document.querySelectorAll("img[data-image-standard]")].map(i=>({src:i.getAttribute("src"),scale:i.dataset.renderDensity,complete:i.complete,w:i.naturalWidth}))})')))

        browser.call('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False}, session)
        browser.call('Page.navigate', {'url': base}, session)
        browser.wait_event('Page.loadEventFired', session)
        wait_for('document.querySelectorAll(".thumb img").length===2')
        for value in (1, 2, 1):
            density(value)
            widths = js('[...document.querySelectorAll(".thumb img")].map(image=>[image.naturalWidth,image.getBoundingClientRect().width])')
            self.assertEqual(widths, [[640 * value, 640], [640 * value, 640]])

        js('document.querySelector(".thumb").click()')
        wait_for('document.querySelector("#viewer").open && document.querySelector("#full-image").complete')
        js('document.querySelector("#comment").value="Unsent note";document.querySelector("#comment").dispatchEvent(new Event("input"))')
        for value in (2, 1):
            density(value)
            self.assertEqual(js('document.querySelector("#full-image").getBoundingClientRect().width'), 640)
            self.assertEqual(js('document.querySelector("#comment").value'), 'Unsent note')
        js('document.querySelector("#step").value=1;document.querySelector("#step").dispatchEvent(new Event("input"))')
        wait_for('document.querySelector("#full-image").complete && document.querySelector("#full-image").naturalWidth===480')
        for value in (2, 1):
            density(value)
            self.assertEqual(js('document.querySelector("#full-image").getBoundingClientRect().width'), 480)
            self.assertIn(f'/1/2', js('document.querySelector("#download-2").getAttribute("href")'))

        js('document.querySelector("#viewer-close").click();document.querySelector("[data-filter=all]").click();document.querySelector("#select-mode").click()')
        # Each click rerenders the board, so resolve the checkbox again.
        js('document.querySelectorAll(".select-box")[0].click();document.querySelectorAll(".select-box")[1].click();document.querySelector("#compare").click()')
        wait_for('document.querySelector("#group-dialog").open')
        for value in (2, 1):
            density(value)
            self.assertEqual(js('[...document.querySelectorAll("#compare-grid img")].map(image=>image.getBoundingClientRect().width)'), [640, 640])


if __name__ == '__main__':
    unittest.main()
