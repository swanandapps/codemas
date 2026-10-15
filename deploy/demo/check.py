"""Rehearse the demo against the live API with two throwaway students, then reset.

Flow: trainer makes a 1-question JavaScript binary search exam (30 min) — by AI
generation with --ai, otherwise a hand-written question of the same shape — and
activates it for one section; two students each fail an attempt, then pass,
then Submit exam; the trainer sees their submissions, runs the plagiarism check,
confirms the pair with a note; the students see it. Finally deploy/demo/reset.py
deletes the exam. Uses Section B students, never the demo students.

    backend/venv/bin/python deploy/demo/check.py [--ai]

Runs from any folder. Passwords come from Railway and are never printed.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

API = 'https://codemas-api.up.railway.app/api'
REPO = Path(__file__).resolve().parents[2]  # railway CLI needs the linked repo as cwd
SECTION = 'Section B'
AVOID = {'aarav_sharma0', 'tara_shah96'}

env = json.loads(subprocess.run(['railway', 'variables', '-s', 'backend', '--json'], cwd=REPO,
                                capture_output=True, text=True, check=True).stdout)
failures = []


def login(username, password):
    r = requests.post(f'{API}/auth/login/', json={'username': username, 'password': password}, timeout=30)
    r.raise_for_status()
    s = requests.Session()
    s.headers['Authorization'] = f"Bearer {r.json()['access']}"
    return s


def step(msg):
    print(f'\n== {msg}', flush=True)


def check(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
    if not cond:
        failures.append(msg)
    return cond


QUESTION = {
    'title': 'Find the Target Index',
    'description': ('Given a sorted array of distinct integers and a target, print the index of the target '
                    'using binary search, or -1 if it is not present.\n\nInput: line 1 holds the array as '
                    'space-separated integers; line 2 holds the target.\nOutput: one integer.'),
    'difficulty': 'easy',
    'test_cases': [
        {'input_data': '1 3 5 7 9 11\n7', 'expected_output': '3', 'is_hidden': False},
        {'input_data': '2 4 6 8\n5', 'expected_output': '-1', 'is_hidden': True},
        {'input_data': '-10 -3 0 4 8 15 23\n-10', 'expected_output': '0', 'is_hidden': True},
    ],
    'starter_code': {
        'javascript': ("const lines = require('fs').readFileSync(0, 'utf8').trim().split('\\n');\n"
                       "const arr = lines[0].split(' ').map(Number);\nconst target = Number(lines[1]);\n\n"
                       "function findTargetIndex(arr, target) {\n  // Write your code here\n  return -1;\n}\n\n"
                       "console.log(findTargetIndex(arr, target));\n"),
        'python': '',
    },
}

WRONG = """const lines = require('fs').readFileSync(0, 'utf8').trim().split('\\n');
const arr = lines[0].split(' ').map(Number);
const target = Number(lines[1]);

function findTargetIndex(arr, target) {
  let lo = 0, hi = arr.length - 1;
  while (lo < hi) {               // off-by-one: misses the last candidate
    const mid = Math.floor((lo + hi) / 2);
    if (arr[mid] === target) return mid;
    if (arr[mid] < target) lo = mid + 1; else hi = mid - 1;
  }
  return -1;
}

console.log(findTargetIndex(arr, target));
"""
# For an AI exam the student fills in the generated starter's function body, like in the demo.
WRONG_BODY = '''let lo = 0, hi = arr.length - 1;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (arr[mid] === target) return mid;
    if (arr[mid] < target) lo = mid + 1; else hi = mid - 1;
  }
  return -1;'''
RIGHT_BODY = WRONG_BODY.replace('while (lo < hi)', 'while (lo <= hi)')
RIGHT = WRONG.replace('while (lo < hi) {               // off-by-one: misses the last candidate',
                      'while (lo <= hi) {')

trainer = login('venugopal', env['SEED_TRAINER_PASSWORD'])
exam_id = None
try:
    step('Trainer creates the exam')
    if '--ai' in sys.argv:
        t0 = time.time()
        r = trainer.post(f'{API}/ai/generate-exam/', json={'topic': 'binary search', 'language': 'javascript',
                                                            'difficulty': 'easy', 'num_questions': 1}, timeout=130)
        if not check(r.status_code == 200, f'AI generation {r.status_code} in {time.time() - t0:.1f}s'):
            raise SystemExit(r.json())
        draft = r.json()
        q = draft['questions'][0]
        print(json.dumps(q, indent=1))
        check(sum(not tc['is_hidden'] for tc in q['test_cases']) == 1, 'exactly one visible sample test')
        starter = q['starter_code']['javascript']
        check("readFileSync(0" in starter and '// Write your code here' in starter, 'JS starter reads stdin, has the body to fill')
        WRONG = starter.replace('// Write your code here', WRONG_BODY)
        RIGHT = starter.replace('// Write your code here', RIGHT_BODY)
    else:
        draft = {'title': 'JavaScript Binary Search', 'description': 'One binary search question.',
                 'questions': [QUESTION]}
    r = trainer.post(f'{API}/exams/create-full/', json={**draft, 'title': '[CHECK] ' + draft['title'],
                                                         'duration_minutes': 30, 'language': 'javascript'}, timeout=30)
    exam_id = r.json()['id']
    check(r.status_code == 201, f'saved exam {exam_id} (30 min)')
    r = trainer.patch(f'{API}/exams/{exam_id}/', json={'is_active': True, 'sections': [SECTION]}, timeout=30)
    check(r.status_code == 200, f'activated for {SECTION}')
    enrolled = [e['username'] for e in trainer.get(f'{API}/exams/{exam_id}/enrollments/', timeout=30).json()]
    print(f'{len(enrolled)} enrolled')

    picks = []
    for name in enrolled:
        if name in AVOID or len(picks) == 2:
            continue
        try:
            picks.append((name, login(name, env['SEED_STUDENT_PASSWORD'])))
        except requests.HTTPError:
            print(f'login failed for {name}')
    check(len(picks) == 2, f'students: {[p[0] for p in picks]}')

    step('Students: wrong attempt, then right attempt')
    attempts = {}
    for i, (name, s) in enumerate(picks):
        exam = s.get(f'{API}/exams/{exam_id}/', timeout=30).json()
        check(exam['duration_minutes'] == 30 and exam['id'] in [e['id'] for e in s.get(f'{API}/exams/', timeout=30).json()],
              f'{name} sees the 30-minute exam on the Exams page')
        qid = exam['questions'][0]['id']
        for code in (WRONG, RIGHT):
            body = code if i == 0 else code.replace('let lo = 0', 'let lo = 0 ')
            r = s.post(f'{API}/submissions/create/', json={
                'question': qid, 'code': body, 'language': 'javascript', 'time_remaining_seconds': 1700,
                'had_paste_event': True, 'paste_char_count': len(body), 'time_to_complete_seconds': 90,
                'tab_switch_count': 3}, timeout=30)
            check(r.status_code == 201, f'{name} attempt {r.json().get("attempt_number")} accepted')
            attempts.setdefault(name, []).append((s, r.json()['id']))

    step('Grading, rubric reviews and hints')
    for name, rows in attempts.items():
        for n, (s, sid) in enumerate(rows):
            st = None
            for _ in range(45):
                st = s.get(f'{API}/submissions/{sid}/status/', timeout=30).json().get('status')
                if st not in ('pending', 'queued', 'running'):
                    break
                time.sleep(2)
            want = 'failed' if n == 0 else 'passed'
            check(st == want, f'{name} attempt {n + 1}: {st} (expected {want})')
    time.sleep(20)  # rubric and hint run in the background after grading
    for name, rows in attempts.items():
        s = rows[0][0]
        for n, (_, sid) in enumerate(rows):
            rub = s.get(f'{API}/ai/rubric/{sid}/', timeout=30)
            hint = s.get(f'{API}/ai/hint/{sid}/', timeout=30)
            rb = rub.json() if rub.ok else {}
            print(f'  {name} attempt {n + 1}: rubric {rub.status_code} '
                  f'{rb.get("total_score", rb.get("status"))} | hint {hint.status_code} '
                  f'{(hint.json().get("hint") or hint.json().get("status") or "")[:70] if hint.ok else ""}')

    step('Attempt limit and Submit exam')
    name, s = picks[0]
    used = len(attempts[name])
    print(f'{name} used {used} of 3 attempts')
    for name, s in picks:
        check(s.post(f'{API}/exams/{exam_id}/finish/', timeout=30).status_code == 200, f'{name} Submit exam')

    step('Trainer sees the submissions')
    report = trainer.get(f'{API}/dashboard/exams/{exam_id}/', timeout=30).json()
    rows = {r['username']: r for r in report['students']}
    for name, _ in picks:
        r = rows.get(name, {})
        check(r.get('submitted'), f'exam report: {name} submitted, solved {r.get("questions_solved")}/{r.get("total_questions")}')
    subs = trainer.get(f'{API}/submissions/', params={'exam': exam_id}, timeout=30).json()
    print('trainer submissions list:', subs.get('count', len(subs) if isinstance(subs, list) else '?'))

    step('Run plagiarism check')
    before = len(trainer.get(f'{API}/plagiarism/runs/', params={'exam_id': exam_id}, timeout=30).json())
    t0 = time.time()
    trainer.post(f'{API}/plagiarism/cohorts/{exam_id}/rerun/', timeout=30)
    run = None
    for _ in range(60):
        runs = trainer.get(f'{API}/plagiarism/runs/', params={'exam_id': exam_id}, timeout=30).json()
        if len(runs) > before and runs[0]['status'] in ('completed', 'failed'):
            run = runs[0]
            break
        time.sleep(2)
    check(run and run['status'] == 'completed' and run['s_flags_total'] >= 1,
          f'run in {time.time() - t0:.0f}s: {run and run["b_flags_total"]} behaviour flags, '
          f'{run and run["s_flags_total"]} similar pairs')
    report = trainer.get(f'{API}/dashboard/exams/{exam_id}/', timeout=30).json()
    print('exam report flags:', [(r['username'], r['behavioural_flags'], r['similarity_flags'])
                                 for r in report['students'] if r['behavioural_flags'] or r['similarity_flags']])
finally:
    if exam_id:
        step('Reset')
        subprocess.run([sys.executable, str(REPO / 'deploy/demo/reset.py'), '--yes'])
print('\nALL PASSED' if not failures else f'\n{len(failures)} FAILED: {failures}')
