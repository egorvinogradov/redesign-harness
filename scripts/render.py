#!/usr/bin/env python3
"""Render owned HTML at native 1×/2× density, preserving its CSS viewport."""
import argparse
import base64
import json
import os
import select
import time
import struct
import subprocess
import tempfile
from pathlib import Path

from store import DEFAULT_HOME


def png_dimensions(path):
    header = Path(path).read_bytes()[:24]
    if header[:8] != b'\x89PNG\r\n\x1a\n' or len(header) < 24:
        raise ValueError('Renderer did not return a PNG')
    return struct.unpack('>II', header[16:24])


class ChromePipe:
    """Small sequential CDP client over anonymous pipes; no debug port or dependencies."""
    def __init__(self, profile):
        chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        self.process = subprocess.Popen(
            ['/bin/sh', '-c', 'exec "$@" 3<&0 4>&1', 'render-browser', chrome,
             '--headless=new', '--remote-debugging-pipe', '--disable-gpu', '--hide-scrollbars',
             '--no-first-run', '--no-default-browser-check', '--user-data-dir=' + str(profile)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.buffer = b''
        self.serial = 0
        self.events = []

    def receive(self, deadline):
        while b'\0' not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise TimeoutError('Local design renderer timed out')
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError('Local renderer closed its control pipe')
            self.buffer += chunk
        raw, self.buffer = self.buffer.split(b'\0', 1)
        return json.loads(raw)

    def call(self, method, params=None, session=None):
        self.serial += 1
        message = {'id': self.serial, 'method': method, 'params': params or {}}
        if session:
            message['sessionId'] = session
        self.process.stdin.write(json.dumps(message).encode() + b'\0')
        self.process.stdin.flush()
        deadline = time.monotonic() + 45
        while True:
            response = self.receive(deadline)
            if response.get('id') == self.serial:
                if 'error' in response:
                    raise RuntimeError(response['error']['message'])
                return response.get('result', {})
            self.events.append(response)

    def wait_event(self, method, session):
        deadline = time.monotonic() + 45
        while True:
            for index, event in enumerate(self.events):
                if event.get('method') == method and event.get('sessionId') == session:
                    return self.events.pop(index)
            self.events.append(self.receive(deadline))

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
        self.process.stdin.close()
        self.process.stdout.close()


def render(html, output, width=1920, height=1080, scale=1, home=DEFAULT_HOME, clip=None):
    """Render an owned file; clip is (x, y, width, height) in CSS pixels."""
    home, source, output = Path(home).resolve(), Path(html).resolve(), Path(output).resolve()
    if not source.is_relative_to(home / 'runs') or source.suffix != '.html' or not source.is_file():
        raise ValueError('Input must be an owned HTML mockup under the director runs directory')
    if not output.is_relative_to(home) or output.suffix != '.png':
        raise ValueError('Output must be a PNG inside the director data directory')
    if scale not in (1, 2) or not 100 <= width <= 5120 or not 100 <= height <= 2160:
        raise ValueError('Use scale 1 or 2 and a viewport from 100–5120 × 100–2160 CSS pixels')
    crop = clip if clip is not None else (0, 0, width, height)
    if len(crop) != 4 or any(type(value) is not int for value in crop):
        raise ValueError('Clip requires integer CSS-pixel x, y, width and height')
    x, y, crop_width, crop_height = crop
    if min(x, y) < 0 or min(crop_width, crop_height) <= 0 or x + crop_width > width or y + crop_height > height:
        raise ValueError('Clip must fit inside the CSS viewport')
    output.parent.mkdir(parents=True, exist_ok=True)
    scratch = home / 'render-cache'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='render-', dir=scratch) as temporary:
        browser = ChromePipe(Path(temporary) / 'profile')
        try:
            target = browser.call('Target.createTarget', {'url': 'about:blank'})['targetId']
            session = browser.call('Target.attachToTarget', {'targetId': target, 'flatten': True})['sessionId']
            browser.call('Page.enable', session=session)
            browser.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
                         'deviceScaleFactor': scale, 'mobile': False}, session)
            browser.call('Page.navigate', {'url': source.as_uri()}, session)
            browser.wait_event('Page.loadEventFired', session)
            ready = browser.call('Runtime.evaluate', {'expression': "document.fonts.ready.then(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))).then(() => ({width: innerWidth, height: innerHeight, scale: devicePixelRatio}))",
                                 'awaitPromise': True, 'returnByValue': True}, session)
            actual = ready.get('result', {}).get('value')
            if actual != {'width': width, 'height': height, 'scale': scale}:
                raise ValueError('Renderer did not preserve the requested CSS viewport and density')
            captured = browser.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True,
                                   'clip': {'x': x, 'y': y, 'width': crop_width, 'height': crop_height, 'scale': 1}}, session)
            output.write_bytes(base64.b64decode(captured['data']))
        finally:
            browser.close()
    if png_dimensions(output) != (crop_width * scale, crop_height * scale):
        raise ValueError('Renderer returned unexpected pixel dimensions')
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('html', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--width', type=int, default=1920, help='CSS viewport width')
    parser.add_argument('--height', type=int, default=1080, help='CSS viewport height')
    density = parser.add_mutually_exclusive_group()
    density.add_argument('--scale', type=int, choices=[1, 2], default=1)
    density.add_argument('--both', action='store_true', help='Render output.png and output@2x.png separately from source')
    parser.add_argument('--clip', type=int, nargs=4, metavar=('X', 'Y', 'WIDTH', 'HEIGHT'))
    parser.add_argument('--home', type=Path, default=DEFAULT_HOME)
    args = parser.parse_args()
    try:
        for scale in ([1, 2] if args.both else [args.scale]):
            output = args.output.with_stem(args.output.stem + '@2x') if args.both and scale == 2 else args.output
            print(render(args.html, output, args.width, args.height, scale, args.home, args.clip))
    except ValueError as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
