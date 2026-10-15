"""Reset the live demo: delete every exam except the six closed past exams.

That removes the exam created in the demo and the seed's open "Python Binary
Search Exam". Deleting an exam cascades its enrollments, submissions, results,
flags, trainer reviews and plagiarism runs, so students keep only their history
in the past exams. Dry run unless --yes. Getting the open exam back needs a full
re-seed.

    backend/venv/bin/python deploy/demo/reset.py          # show what would go
    backend/venv/bin/python deploy/demo/reset.py --yes    # delete it

Runs from any folder (it reads the trainer password from Railway, never printed).
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

API = 'https://codemas-api.up.railway.app/api'
REPO = Path(__file__).resolve().parents[2]  # railway CLI needs the linked repo as cwd
PAST_EXAMS = {  # the seed's closed exams: every student's history lives here
    'Advanced JavaScript: Closures & Scope',
    'Async JavaScript & Promises',
    'Functional Programming in JS',
    'Data Structures in JavaScript',
    'Design Patterns in JavaScript',
    'JavaScript Interview Gauntlet',
}

env = json.loads(subprocess.run(['railway', 'variables', '-s', 'backend', '--json'], cwd=REPO,
                                capture_output=True, text=True, check=True).stdout)


def session(username, password):
    r = requests.post(f'{API}/auth/login/', json={'username': username, 'password': password}, timeout=30)
    r.raise_for_status()
    s = requests.Session()
    s.headers['Authorization'] = f"Bearer {r.json()['access']}"
    return s


trainer = session('venugopal', env['SEED_TRAINER_PASSWORD'])
extra = [e for e in trainer.get(f'{API}/exams/', timeout=30).json() if e['title'] not in PAST_EXAMS]

if not extra:
    print('Already fresh: only the six past exams exist.')
for e in extra:
    print(f"{'deleting' if '--yes' in sys.argv else 'would delete'} exam {e['id']}: {e['title']}")
    if '--yes' not in sys.argv:
        continue
    for attempt in range(3):  # a delete racing the worker's AI writes can 500 once; retry
        r = trainer.delete(f"{API}/exams/{e['id']}/", timeout=60)
        if r.status_code in (204, 404):
            print('  deleted')
            break
        print(f'  got {r.status_code}, retrying')
        time.sleep(10)

if extra and '--yes' not in sys.argv:
    print('\nDry run. Add --yes to delete.')
