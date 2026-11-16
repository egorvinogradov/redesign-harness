import json
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path

from server import make_handler
from store import ET, Store, work_window
from supervisor import MAX_ATTEMPTS, REPO, Supervisor


class DirectorTests(unittest.TestCase):
    def setUp(self):
        scratch = REPO / 'tmp' / datetime.now(ET).date().isoformat() / 'design-director'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def artifact(self, name='one', style='same-style'):
        path = self.store.home / 'assets' / (name + '.png')
        # Header-only fixture tests import validation, not image rendering.
        path.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\0' * 8 + struct.pack('>II', 1920, 1080) + name.encode())
        return self.store.import_artifact({'title': name, 'style': style, 'page': 'leads',
                                          'component': 'filters', 'node': name, 'image': str(path),
                                          'caption': 'A focused decision', 'fullPage': True})

    def test_images_are_immutable_and_feedback_survives_restart(self):
        first, second = self.artifact(), self.artifact('two')
        feedback = self.store.add_feedback({'ids': [first['id'], second['id']], 'scope': 'style', 'text': 'Less rounded'})
        restarted = Store(self.store.home)
        self.assertEqual(restarted.all('feedback')[0]['styles'], ['same-style'])
        self.assertEqual(len(restarted.all('jobs')), 1)
        self.assertTrue(all(a['reviewed'] for a in restarted.all('artifacts')))
        (self.store.home / 'assets/one.png').write_bytes(b'replaced')
        self.assertTrue((self.store.home / 'assets' / first['image']).read_bytes().startswith(b'\x89PNG'))
        self.assertFalse(feedback['processed'])

    def test_viewing_is_not_reviewing(self):
        artifact = self.artifact()
        self.store.review([artifact['id']], {'viewed': True})
        self.assertTrue(self.store.all('artifacts')[0]['viewed'])
        self.assertFalse(self.store.all('artifacts')[0]['reviewed'])

    def test_scope_and_annotation_validation(self):
        artifact = self.artifact()
        self.store.add_feedback({'ids': [artifact['id']], 'text': 'Move this', 'scope': 'component',
                                 'region': {'shape': 'ellipse', 'x': .2, 'y': .3, 'w': .1, 'h': .2}})
        with self.assertRaises(ValueError):
            self.store.add_feedback({'ids': [artifact['id']], 'text': 'Bad', 'region': {'shape': 'rect', 'x': .9, 'y': 0, 'w': .5, 'h': .1}})
        with self.assertRaises(ValueError):
            self.store.import_artifact({'title': 'Bad', 'style': 's', 'page': 'p', 'component': 'c', 'node': 'n', 'caption': 'c', 'image': '/etc/passwd'})

    def test_pause_expiry_and_et_schedule(self):
        monday = datetime(2026, 11, 16, 10, tzinfo=ET).timestamp()
        settings = {'paused': False, 'runUntil': monday - 1, 'schedule': {'enabled': True,
                    'start': '09:00', 'end': '13:00', 'days': [0], 'through': '2026-11-20'}}
        self.assertEqual(work_window(settings, monday), datetime(2026, 11, 16, 13, tzinfo=ET).timestamp())
        self.assertIsNone(work_window(settings, monday + 4 * 3600))
        self.assertIsNone(work_window(settings, monday + 7 * 86400))
        settings['paused'] = True
        self.assertIsNone(work_window(settings, monday))
        with self.assertRaises(ValueError):
            self.store.control({'action': 'run', 'hours': 100})

    def test_pause_stops_real_worker_and_preserves_job(self):
        self.store.control({'action': 'run', 'hours': .1})
        job = self.store.job('Test wait', 'Wait')
        supervisor = Supervisor(self.store, [sys.executable, '-c', 'import sys,time; sys.stdin.read(); time.sleep(60)'])
        try:
            supervisor.tick()
            process = supervisor.process
            self.assertIsNone(process.poll())
            self.store.control({'action': 'pause'})
            supervisor.tick()
            self.assertIsNotNone(process.poll())
            self.assertEqual(self.store.all('jobs')[0]['status'], 'queued')
            self.assertEqual(self.store.all('jobs')[0]['attempts'], 0)
        finally:
            supervisor.close()

    def test_success_imports_output_and_failure_has_retry_limit(self):
        self.store.control({'action': 'run', 'hours': .1})
        job = self.store.job('Test evidence', 'Research', kind='research')
        evidence = self.store.home / 'evidence/result.md'
        evidence.write_text('A concrete workflow finding.')
        result_path = self.store.home / 'runs' / job['id'] / 'claude' / 'result.json'
        code = 'import sys,json,pathlib; sys.stdin.read(); pathlib.Path(sys.argv[1]).write_text(json.dumps({"status":"complete","summary":"Evidence saved","evidence":[sys.argv[2]]}))'
        supervisor = Supervisor(self.store, [sys.executable, '-c', code, str(result_path), str(evidence)])
        try:
            supervisor.tick()
            supervisor.process.wait(timeout=5)
            supervisor.tick()
            self.assertEqual(self.store.all('jobs')[0]['status'], 'done')
            bad = self.store.job('Test failure', 'Fail')
            bad['attempts'] = MAX_ATTEMPTS - 1
            self.store.put('jobs', bad)
            supervisor.command = [sys.executable, '-c', 'import sys; sys.stdin.read(); sys.exit(1)']
            supervisor.tick()
            supervisor.process.wait(timeout=5)
            supervisor.tick()
            self.assertEqual(next(j for j in self.store.all('jobs') if j['id'] == bad['id'])['status'], 'blocked')
        finally:
            supervisor.close()

    def test_hard_deadline_stops_chatty_worker(self):
        self.store.control({'action': 'run', 'hours': .1})
        self.store.job('Deadline test', 'Wait')
        supervisor = Supervisor(self.store, [sys.executable, '-c', 'import sys,time; sys.stdin.read(); print("active",flush=True); time.sleep(60)'])
        try:
            supervisor.tick()
            process = supervisor.process
            supervisor.active['deadline'] = time.time() - 1
            supervisor.tick()
            self.assertIsNotNone(process.poll())
            self.assertIn('time limit', self.store.all('jobs')[0]['error'])
        finally:
            supervisor.close()

    def test_tool_switch_stops_current_worker_without_losing_job(self):
        self.store.control({'action': 'run', 'hours': .1})
        self.store.job('Switch test', 'Wait')
        supervisor = Supervisor(self.store, [sys.executable, '-c', 'import sys,time; sys.stdin.read(); time.sleep(60)'])
        try:
            supervisor.tick()
            process = supervisor.process
            self.store.control({'action': 'engine', 'engine': 'pen'})
            supervisor.tick()
            self.assertIsNotNone(process.poll())
            self.assertEqual(self.store.all('jobs')[0]['status'], 'queued')
            self.assertEqual(self.store.settings()['engine'], 'pen')
            self.assertFalse(self.store.settings()['paused'])
            self.assertEqual(len(self.store.all('jobs')), 1)
        finally:
            supervisor.close()

    def test_freehand_marks_are_validated_and_bound_to_their_points(self):
        artifact = self.artifact()
        region = {'shape': 'freehand', 'x': 0, 'y': 0, 'w': 1, 'h': 1,
                  'points': [[.1, .2], [.4, .2], [.4, .5], [.1, .2]]}
        feedback = self.store.add_feedback({'ids': [artifact['id']], 'text': 'This area', 'region': region})
        self.assertEqual(feedback['region']['x'], .1)
        self.assertAlmostEqual(feedback['region']['w'], .3)
        self.assertAlmostEqual(feedback['region']['h'], .3)
        for points in [[[0, 0]], [[0, 0], [2, 0]], [[0, 0], ['x', 1]], [[0, 0]] * 601]:
            with self.assertRaises(ValueError):
                self.store.add_feedback({'ids': [artifact['id']], 'text': 'Invalid',
                                         'region': dict(region, points=points)})

    def test_configured_timezone_changes_daily_work_window(self):
        now = datetime(2026, 11, 16, 10, tzinfo=ET).timestamp()
        settings = {'paused': False, 'runUntil': 0, 'timezone': 'America/Los_Angeles',
                    'schedule': {'enabled': True, 'start': '09:00', 'end': '13:00',
                                 'days': [0], 'through': '2026-11-20'}}
        self.assertIsNone(work_window(settings, now))
        self.assertIsNotNone(work_window(settings, now + 8 * 3600))

    def test_project_configuration_is_local_and_controls_export_size(self):
        self.assertEqual(self.store.settings()['projectPath'], '')
        self.store.update_settings({'projectName': 'Example', 'projectPath': str(self.store.home),
                                   'projectInstructions': str(self.store.home / 'brief.md'),
                                   'targetSize': [1440, 900]})
        with self.assertRaises(ValueError):
            self.artifact()
        folder = self.store.home / 'runs' / 'prompt-test'
        folder.mkdir()
        prompt = Supervisor(self.store).prompt({'engine': 'claude', 'id': 'prompt-test', 'kind': 'design',
                                               'title': 'Example', 'brief': 'Polish existing controls', 'deadline': 1}, folder)
        self.assertIn(str(self.store.home / 'brief.md'), prompt)
        self.assertIn('[1440, 900]', prompt)
        self.assertEqual(Store(self.store.home).settings()['projectName'], 'Example')

    def test_http_rejects_cross_origin_writes_and_persists_valid_review(self):
        artifact = self.artifact()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store, 'test-token'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            body = json.dumps({'ids': [artifact['id']], 'text': 'A real comment'}).encode()
            request = urllib.request.Request(base + '/api/feedback', data=body, headers={'Origin': 'https://unrelated.example', 'X-Review-Token': 'test-token'})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, 403)
            request = urllib.request.Request(base + '/api/feedback', data=body, headers={'Origin': base, 'X-Review-Token': 'test-token'})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 200)
            self.assertEqual(Store(self.store.home).all('feedback')[0]['text'], 'A real comment')
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
