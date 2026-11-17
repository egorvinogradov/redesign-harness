"""Durable local review state. Only this module writes the SQLite database."""
import hashlib
import json
import os
import shutil
import sqlite3
import struct
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_HOME = Path(os.environ.get('REDESIGN_HARNESS_HOME', Path.home() / 'Library/Application Support/Redesign Harness'))
ET = ZoneInfo('UTC')


def uid():
    return uuid.uuid4().hex


def work_window(settings, now=None):
    now = time.time() if now is None else now
    if settings['paused']:
        return None
    ends = [settings.get('runUntil', 0)]
    schedule = settings.get('schedule', {})
    local = datetime.fromtimestamp(now, ZoneInfo(settings.get('timezone', 'UTC')))
    if schedule.get('enabled') and local.date().isoformat() <= schedule['through']:
        if local.weekday() in schedule['days']:
            start_hour, start_minute = map(int, schedule['start'].split(':'))
            end_hour, end_minute = map(int, schedule['end'].split(':'))
            start = local.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
            end = local.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
            if start.timestamp() <= now < end.timestamp():
                ends.append(end.timestamp())
    deadline = max(ends)
    return deadline if deadline > now else None


class Store:
    def __init__(self, home=DEFAULT_HOME):
        self.home = Path(home).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.home.chmod(0o700)
        for name in ['assets', 'runs', 'workspace', 'evidence']:
            (self.home / name).mkdir(exist_ok=True)
        self.path = self.home / 'review.sqlite'
        with self.db() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, data TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS feedback (id TEXT PRIMARY KEY, data TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, data TEXT NOT NULL, created REAL NOT NULL);
            ''')
            settings = {'paused': True, 'runUntil': 0, 'schedule': {'enabled': False},
                        'canvas': '', 'engine': 'claude', 'projectName': 'Your project',
                        'projectPath': '', 'projectInstructions': '', 'timezone': 'UTC', 'targetSize': [1920, 1080],
                        'worker': 'Claude', 'claudeModel': '',
                        'reviewDisplay': 'Actual size', 'lastError': None}
            db.execute('INSERT OR IGNORE INTO settings VALUES (1, ?)', (json.dumps(settings),))

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def settings(self):
        with self.db() as db:
            return json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])

    def update_settings(self, patch):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            data = json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
            data.update(patch)
            db.execute('UPDATE settings SET data=? WHERE id=1', (json.dumps(data),))
        return data

    def all(self, table):
        if table not in {'artifacts', 'feedback', 'jobs', 'events'}:
            raise ValueError('Unknown collection')
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute(f'SELECT data FROM {table} ORDER BY created DESC')]

    def put(self, table, data):
        if table not in {'artifacts', 'feedback', 'jobs'}:
            raise ValueError('Unknown collection')
        with self.db() as db:
            db.execute(f'INSERT INTO {table} VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                       (data['id'], json.dumps(data), data['created']))
        return data

    def event(self, text, kind='info'):
        with self.db() as db:
            db.execute('INSERT INTO events (data, created) VALUES (?, ?)',
                       (json.dumps({'text': text, 'kind': kind, 'created': time.time()}), time.time()))
            db.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 300)')

    def job(self, title, brief, priority=10, kind='design', key=None):
        key = key or title
        existing = next((j for j in self.all('jobs') if j['key'] == key), None)
        if existing:
            return existing
        return self.put('jobs', {'id': uid(), 'title': title, 'brief': brief, 'kind': kind, 'key': key,
                                'priority': priority, 'status': 'queued', 'attempts': 0, 'created': time.time()})

    def _png(self, image, copy=False):
        path = Path(image).resolve()
        if not path.is_relative_to(self.home) or not path.is_file():
            raise ValueError('Image must be a local export inside the director data directory')
        raw = path.read_bytes()
        if raw[:8] != b'\x89PNG\r\n\x1a\n' or len(raw) < 24:
            raise ValueError('Export a PNG image')
        width, height = struct.unpack('>II', raw[16:24])
        if not width or not height:
            raise ValueError('Empty image')
        filename = hashlib.sha256(raw).hexdigest() + '.png'
        if copy:
            destination = self.home / 'assets' / filename
            if path != destination:
                shutil.copyfile(path, destination)
        return filename, [width, height]

    def _density_fields(self, artifact, image2x=None, steps2x=None, sources=None):
        step_images = artifact['steps']
        step_dimensions = [self._png(self.home / 'assets' / image)[1] for image in step_images]
        dimensions = [artifact['dimensions'], *step_dimensions]
        if steps2x is not None and (not isinstance(steps2x, list) or len(steps2x) != len(step_images)):
            raise ValueError('steps2x must align with the standard-resolution steps')
        if sources is not None and (not isinstance(sources, list) or len(sources) != len(dimensions)
                                    or any(source is not None and not isinstance(source, dict) for source in sources)):
            raise ValueError('sources must contain one provenance object or null per frame')
        retina = [image2x, *(steps2x if steps2x is not None else [None] * len(step_images))]
        stored = [artifact.get('image2x'), *artifact.get('steps2x', [None] * len(step_images))]
        for index, image in enumerate(retina):
            if image is None:
                continue
            filename, pixels = self._png(image, copy=True)
            if pixels != [dimension * 2 for dimension in dimensions[index]]:
                raise ValueError('Retina export must be exactly twice the standard frame dimensions')
            stored[index] = filename
        patch = {'image2x': stored[0], 'steps2x': stored[1:], 'stepDimensions': step_dimensions}
        if sources is not None:
            patch['sources'] = sources
        return patch

    def attach_density(self, artifact_id, image2x=None, steps2x=None, sources=None):
        """Attach native density exports without replacing reviews, IDs, or original PNGs."""
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data FROM artifacts WHERE id=?', (artifact_id,)).fetchone()
            if not row:
                raise ValueError('Screenshot not found')
            artifact = json.loads(row[0])
            artifact.update(self._density_fields(artifact, image2x, steps2x, sources))
            db.execute('UPDATE artifacts SET data=? WHERE id=?', (json.dumps(artifact), artifact_id))
        return artifact

    def import_artifact(self, data, job_id=None):
        required = ['title', 'style', 'page', 'component', 'node', 'image', 'caption']
        if any(not isinstance(data.get(k), str) or not data[k] for k in required):
            raise ValueError('Artifact needs title, style, page, component, node, image and caption')
        if len(data['caption']) > 180:
            raise ValueError('Caption must fit in 180 characters')
        images = [data['image']] + data.get('steps', [])
        if len(images) > 7:
            raise ValueError('Use at most six interaction steps')
        exported = [self._png(image, copy=True) for image in images]
        files = [image[0] for image in exported]
        dimensions = [image[1] for image in exported]
        if data.get('fullPage') and dimensions[0] != self.settings().get('targetSize', [1920, 1080]):
            raise ValueError('Full screen export must match the configured targetSize')
        existing = next((a for a in self.all('artifacts') if a['image'] == files[0] and a['node'] == data['node'] and a['steps'] == files[1:]), None)
        if existing:
            return self.attach_density(existing['id'], data.get('image2x'), data.get('steps2x'), data.get('sources'))
        artifact = {k: data.get(k) for k in ['title', 'style', 'page', 'component', 'node', 'caption', 'engine',
                                           'parent', 'recommendation', 'fullPage', 'stepCaptions']}
        artifact.update(id=uid(), created=time.time(), job=job_id, image=files[0], steps=files[1:],
                        dimensions=dimensions[0], viewed=False, reviewed=False, reaction=None, decision=None)
        artifact.update(self._density_fields(artifact, data.get('image2x'), data.get('steps2x'), data.get('sources')))
        self.put('artifacts', artifact)
        return artifact

    def review(self, ids, patch):
        if not ids or len(ids) > 100:
            raise ValueError('Select screenshots first')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for artifact_id in ids:
                row = db.execute('SELECT data FROM artifacts WHERE id=?', (artifact_id,)).fetchone()
                if not row:
                    raise ValueError('Screenshot not found')
                artifact = json.loads(row[0])
                artifact.update(patch)
                db.execute('UPDATE artifacts SET data=? WHERE id=?', (json.dumps(artifact), artifact_id))

    def add_feedback(self, data):
        ids = data.get('ids', [])
        artifacts = {a['id']: a for a in self.all('artifacts')}
        if not ids or any(i not in artifacts for i in ids):
            raise ValueError('Select existing screenshots')
        text = data.get('text', '').strip()
        reaction = data.get('reaction')
        decision = data.get('decision')
        if reaction is not None and reaction not in [-2, -1, 0, 1, 2]:
            raise ValueError('Invalid reaction')
        if decision is not None and decision not in ['approved', 'vetoed']:
            raise ValueError('Invalid decision')
        if not text and reaction is None and decision is None:
            raise ValueError('Add a comment or reaction')
        scope = data.get('scope', 'interpret')
        if scope not in ['interpret', 'screen', 'style', 'component', 'group']:
            raise ValueError('Invalid scope')
        region = data.get('region')
        if region:
            if len(ids) != 1 or region.get('shape') not in ['rect', 'ellipse', 'freehand']:
                raise ValueError('An area belongs to one screenshot')
            for key in ['x', 'y', 'w', 'h']:
                if not isinstance(region.get(key), (float, int)) or not 0 <= region[key] <= 1:
                    raise ValueError('Area coordinates must be normalized')
            if region['x'] + region['w'] > 1.001 or region['y'] + region['h'] > 1.001:
                raise ValueError('Area is outside the image')
            if region['shape'] == 'freehand':
                points = region.get('points')
                if not isinstance(points, list) or not 2 <= len(points) <= 600:
                    raise ValueError('A freehand mark needs 2–600 points')
                for point in points:
                    if not isinstance(point, list) or len(point) != 2 or any(type(v) not in [int, float] or not 0 <= v <= 1 for v in point):
                        raise ValueError('Stroke points must be normalized')
                xs, ys = zip(*points)
                region = dict(region, x=min(xs), y=min(ys), w=max(xs)-min(xs), h=max(ys)-min(ys))
            step = region.get('step', 0)
            if type(step) is not int or not 0 <= step <= len(artifacts[ids[0]]['steps']):
                raise ValueError('Unknown interaction step')
        feedback = {'id': uid(), 'created': time.time(), 'ids': ids, 'text': text[:6000], 'scope': scope,
                    'region': region, 'reaction': reaction, 'decision': decision, 'processed': False,
                    'styles': list({artifacts[i]['style'] for i in ids}),
                    'components': list({artifacts[i]['component'] for i in ids}), 'resolution': None}
        self.put('feedback', feedback)
        patch = {'viewed': True, 'reviewed': True}
        if reaction is not None:
            patch['reaction'] = reaction
        if decision:
            patch['decision'] = decision
        self.review(ids, patch)
        self.job('Apply your feedback', 'Interpret feedback ' + feedback['id'] +
                 '. Read the current board and every pending feedback item. Apply style feedback across its family. '
                 'For a region, revise only that component and publish a focused crop. '
                 'A reaction is a preference signal, not a requirement to redraw everything. '
                 'Respect explicit vetoes and approvals. Record applied scope and affected designs.',
                 priority=100, kind='feedback', key='feedback:' + feedback['id'])
        return feedback

    def snapshot(self):
        settings = self.settings()
        return {'settings': settings, 'deadline': work_window(settings), 'artifacts': self.all('artifacts'),
                'feedback': self.all('feedback'), 'jobs': self.all('jobs'), 'events': self.all('events')[:30]}

    def control(self, data):
        action = data.get('action')
        if action == 'pause':
            return self.update_settings({'paused': True, 'runUntil': 0})
        if action == 'engine':
            engine = data.get('engine')
            if engine not in ['claude', 'pen']:
                raise ValueError('Choose Claude or Pen Dev')
            self.event('Design tool switched to ' + {'claude': 'Claude', 'pen': 'Pen Dev'}[engine])
            return self.update_settings({'engine': engine, 'worker': {'claude': 'Claude', 'pen': 'Codex + Pen canvas'}[engine], 'lastError': None})
        if action == 'run':
            hours = float(data.get('hours', 0))
            if not 0.05 <= hours <= 8:
                raise ValueError('Choose between 3 minutes and 8 hours')
            return self.update_settings({'paused': False, 'runUntil': time.time() + hours * 3600, 'lastError': None})
        if action == 'schedule':
            schedule = data['schedule']
            if not schedule.get('enabled'):
                return self.update_settings({'schedule': {'enabled': False}})
            start = datetime.strptime(schedule['start'], '%H:%M')
            end = datetime.strptime(schedule['end'], '%H:%M')
            hours = (end - start).total_seconds() / 3600
            through = datetime.strptime(schedule['through'], '%Y-%m-%d').date()
            today = datetime.now(ZoneInfo(self.settings().get('timezone', 'UTC'))).date()
            if not 0 < hours <= 8 or not today <= through <= today + timedelta(days=30):
                raise ValueError('Use a daytime window up to 8 hours, ending within 30 days')
            if not schedule['days'] or any(type(d) is not int or d not in range(7) for d in schedule['days']):
                raise ValueError('Choose work days')
            return self.update_settings({'schedule': schedule, 'paused': False, 'lastError': None})
        if action == 'retry':
            job = next((j for j in self.all('jobs') if j['id'] == data.get('id')), None)
            if not job or job['status'] != 'blocked':
                raise ValueError('No blocked job selected')
            job.update(status='queued', attempts=0, error=None)
            return self.put('jobs', job)
        raise ValueError('Unknown control')
