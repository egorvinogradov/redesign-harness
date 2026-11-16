#!/usr/bin/env python3
"""Render an owned local design mockup at 1×; never browse external/account pages."""
import argparse
import struct
import subprocess
import tempfile
from pathlib import Path

from store import DEFAULT_HOME


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('html', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--height', type=int, default=1080)
    parser.add_argument('--home', type=Path, default=DEFAULT_HOME)
    args = parser.parse_args()
    home, source, output = args.home.resolve(), args.html.resolve(), args.output.resolve()
    if not source.is_relative_to(home / 'runs') or source.suffix != '.html' or not source.is_file():
        parser.error('Input must be an owned HTML mockup under the director runs directory')
    if not output.is_relative_to(home) or output.suffix != '.png':
        parser.error('Output must be a PNG inside the director data directory')
    if not 100 <= args.width <= 3840 or not 100 <= args.height <= 2160:
        parser.error('Invalid mockup dimensions')
    output.parent.mkdir(parents=True, exist_ok=True)
    scratch = home / 'render-cache'
    scratch.mkdir(parents=True, exist_ok=True)
    chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    with tempfile.TemporaryDirectory(prefix='render-', dir=scratch) as profile:
        command = [chrome, '--headless=new', '--disable-gpu', '--hide-scrollbars',
                   '--no-first-run', '--no-default-browser-check', '--force-device-scale-factor=1',
                   '--user-data-dir=' + profile, f'--window-size={args.width},{args.height}',
                   '--virtual-time-budget=5000', '--screenshot=' + str(output), source.as_uri()]
        subprocess.run(command, capture_output=True, timeout=45, check=True)
    raw = output.read_bytes()
    if raw[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', raw[16:24]) != (args.width, args.height):
        raise ValueError('Renderer returned unexpected pixel dimensions')
    print(output)


if __name__ == '__main__':
    main()
