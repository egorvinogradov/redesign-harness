#!/usr/bin/env python3
"""Configure and operate a local Redesign Harness workspace."""
import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from store import DEFAULT_HOME, Store
from supervisor import SKILL

LABEL = 'app.redesign-harness'
def service_identity(instance=None):
    if instance is not None and not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,47}', instance):
        raise ValueError('Service name must contain 1–48 lowercase letters, digits or hyphens')
    label = LABEL + ('.' + instance if instance else '')
    return label, Path.home() / 'Library/LaunchAgents' / (label + '.plist')


def check_service_workspace(plist, home):
    if not plist.exists():
        return
    arguments = plistlib.loads(plist.read_bytes()).get('ProgramArguments', [])
    if '--home' not in arguments or Path(arguments[arguments.index('--home') + 1]).resolve() != home.resolve():
        raise ValueError('That service belongs to another workspace. Use a unique --service name.')


def seed(store):
    for key, title, priority, kind, brief in [
        ('workflow-map', 'Understand the product', 40, 'research',
         'Read the configured project source and instructions. Map the existing pages, main tasks, '
         'complex workflows, and shared components. Record evidence and inferred priorities. '
         'Do not invent usage statistics. Save a concise evidence file.'),
        ('primary-workspace', 'The main workspace', 30, 'design',
         'Use the workflow map to choose the most important existing screen. Preserve its capabilities. '
         'Create two meaningfully different layouts with one recommendation. Use the configured target size. '
         'Show a focused sequence for any changed interaction.'),
        ('shared-controls', 'A coherent visual language', 20, 'design',
         'Inspect the main workspace designs and stakeholder feedback. Refine typography, spacing, '
         'navigation and existing repeated controls. Publish representative component crops.'),
        ('next-workflow', 'The next important workflow', 15, 'design',
         'Choose the next uncovered workflow from the evidence. Preserve existing capabilities and '
         'apply the current visual direction. Publish a screen and a focused interaction sequence.'),
        ('coverage-audit', 'Find the remaining design gaps', 10, 'research',
         'Compare completed designs with existing pages and meaningful states. Record concrete gaps '
         'and proposed next briefs in an evidence file. Do not produce cosmetic variants just to fill time.')
    ]:
        store.job(title, brief, priority, kind, key)


def install(store, port=4317, instance=None):
    if sys.platform != 'darwin':
        raise ValueError('Login service installation supports macOS. Run scripts/server.py directly elsewhere.')
    label, plist = service_identity(instance)
    check_service_workspace(plist, store.home)
    if not 1024 <= port <= 65535:
        raise ValueError('Choose a port from 1024–65535')
    plist.parent.mkdir(parents=True, exist_ok=True)
    service = {'Label': label,
               'ProgramArguments': [sys.executable, str(SKILL / 'scripts/server.py'), '--home', str(store.home), '--port', str(port)],
               'WorkingDirectory': str(SKILL), 'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 10,
               'StandardOutPath': str(store.home / 'service.log'), 'StandardErrorPath': str(store.home / 'service.log'),
               'EnvironmentVariables': {'PATH': os.environ.get('PATH', '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin'),
                                        'PYTHONUNBUFFERED': '1'}}
    target = f'gui/{os.getuid()}'
    subprocess.run(['launchctl', 'bootout', target + '/' + label], capture_output=True)
    for _ in range(30):
        if subprocess.run(['launchctl', 'print', target + '/' + label], capture_output=True).returncode:
            break
        time.sleep(.2)
    plist.write_bytes(plistlib.dumps(service))
    subprocess.run(['launchctl', 'bootstrap', target, str(plist)], check=True)
    print(f'Redesign Harness: http://127.0.0.1:{port}')
    print('Login service installed. No work time added.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', type=Path, default=DEFAULT_HOME)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ['status', 'pause', 'seed']:
        commands.add_parser(name)
    installer = commands.add_parser('install')
    installer.add_argument('--port', type=int, default=4317)
    installer.add_argument('--service', help='Unique name for an additional project login service')
    uninstaller = commands.add_parser('uninstall')
    uninstaller.add_argument('--service')
    initializer = commands.add_parser('init')
    initializer.add_argument('--project', type=Path, required=True)
    initializer.add_argument('--name', required=True)
    initializer.add_argument('--instructions', type=Path)
    initializer.add_argument('--timezone', default='UTC')
    initializer.add_argument('--model', default='')
    initializer.add_argument('--canvas', type=Path)
    initializer.add_argument('--width', type=int, default=1920)
    initializer.add_argument('--height', type=int, default=1080)
    add = commands.add_parser('add-job')
    add.add_argument('title')
    add.add_argument('--brief', required=True)
    add.add_argument('--priority', type=int, default=10)
    add.add_argument('--kind', choices=['design', 'research'], default='design')
    run = commands.add_parser('run')
    run.add_argument('--hours', type=float, required=True)
    importer = commands.add_parser('import')
    importer.add_argument('manifest', type=Path)
    args = parser.parse_args()
    store = Store(args.home)
    if args.command == 'init':
        if not args.project.resolve().is_dir():
            parser.error('Project must be an existing directory')
        if args.instructions and not args.instructions.resolve().is_file():
            parser.error('Instructions must be an existing local file')
        if not 100 <= args.width <= 5120 or not 100 <= args.height <= 2160:
            parser.error('Target dimensions must fit the renderer: 100–5120 × 100–2160')
        ZoneInfo(args.timezone)
        store.update_settings({'projectName': args.name, 'projectPath': str(args.project.resolve()),
                               'projectInstructions': str(args.instructions.resolve()) if args.instructions else '',
                               'timezone': args.timezone, 'claudeModel': args.model,
                               'canvas': str(args.canvas.resolve()) if args.canvas else '',
                               'targetSize': [args.width, args.height]})
        print('Project configured locally. Use seed or add-job to prepare work, then run --hours to begin.')
    elif args.command == 'install':
        install(store, args.port, args.service)
    elif args.command == 'uninstall':
        label, plist = service_identity(args.service)
        check_service_workspace(plist, store.home)
        store.control({'action': 'pause'})
        subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/{label}'], capture_output=True)
        plist.unlink(missing_ok=True)
        print('Service removed. Designs, feedback, and jobs retained.')
    elif args.command == 'seed':
        seed(store)
        print('Starter jobs added. No work time added.')
    elif args.command == 'add-job':
        print(store.job(args.title, args.brief, args.priority, args.kind)['id'])
    elif args.command == 'status':
        snapshot = store.snapshot()
        print(json.dumps({'settings': snapshot['settings'], 'deadline': snapshot['deadline'],
                          'artifacts': len(snapshot['artifacts']), 'feedback': len(snapshot['feedback']),
                          'jobs': [{k: j.get(k) for k in ['id', 'title', 'status', 'attempts', 'error']} for j in snapshot['jobs']]}, indent=2))
    elif args.command == 'pause':
        store.control({'action': 'pause'})
        print('Paused. The active worker stops within a few seconds.')
    elif args.command == 'run':
        store.control({'action': 'run', 'hours': args.hours})
        print(f'Granted {args.hours:g} hours.')
    elif args.command == 'import':
        data = json.loads(args.manifest.read_text())
        for artifact in data if isinstance(data, list) else [data]:
            result = store.import_artifact(artifact)
            print(result['id'], result['title'])


if __name__ == '__main__':
    main()
