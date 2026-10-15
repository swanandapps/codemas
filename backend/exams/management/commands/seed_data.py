"""
Seed CodeMas with 98 Indian JS students, six historical (closed) exams and one
open demo exam.

The seed is meant to be *truthful*: everything it writes is what the real
pipeline would have produced for the same student behaviour.

  * Every student writes their own program for every question. Programs are
    composed from structural fragments (algorithm, layout, input reading,
    parsing, printing, declaration and function habits, optional extras; see
    _seed_programs.py), so honest students don't hand in each other's code.
  * Every program is executed against its question's test cases with the real
    executor (``execution.tasks.run_local``) before anything is written. A
    program meant to pass that fails, or a deliberately buggy one that passes,
    aborts the seed. Result rows store the real outputs, and the submission
    status is derived from them exactly like the execution task.
  * Copying is planted through behaviour and code only (``PLANTS``): a few
    students paste a leaked solution, one pastes a lightly edited copy of a
    classmate's program. The seed never writes a BehaviouralFlag or a
    PlagiarismFlag itself.
  * Phase 1 is the production scorer (``run_behavioural_check`` on every
    submission, PlagiarismPolicy reset to its model defaults first).
  * Phase 2 is the production exam-close entry point,
    ``run_exam_plagiarism_check(exam_id, trigger='exam_close', notify=False)``,
    on every closed exam, run eagerly in-process: it records a PlagiarismRun,
    re-scores Phase 1, and cross-compares the HIGH-confidence suspects of every
    question with the whole cohort. The open demo exam gets no Phase 2: that
    happens for real when it closes.
"""
import contextlib
import io
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from exams.models import Exam, Question, TestCase, ExamEnrollment
from exams.starter_code import DEMO_STARTERS
from exams.management.commands import _seed_programs as programs
from submissions.models import Submission
from results.models import Result
from plagiarism.models import (
    BehaviouralFlag, PlagiarismFlag, PlagiarismPolicy, PlagiarismRun, PolicyVersion,
    ReviewAuditLog, POLICY_FIELDS,
)


INDIAN_STUDENTS = [
    # (first, last)
    ("Aarav", "Sharma"), ("Arjun", "Singh"), ("Aditya", "Patel"), ("Akash", "Kumar"),
    ("Ajay", "Gupta"), ("Amit", "Mehta"), ("Anand", "Joshi"), ("Ankit", "Rao"),
    ("Arnav", "Nair"), ("Aryan", "Reddy"), ("Ashish", "Agarwal"), ("Bhavin", "Shah"),
    ("Chirag", "Desai"), ("Darshan", "Iyer"), ("Deepak", "Kapoor"), ("Dev", "Mishra"),
    ("Dhruv", "Pandey"), ("Gaurav", "Verma"), ("Harsh", "Yadav"), ("Hitesh", "Tiwari"),
    ("Ishan", "Pillai"), ("Jay", "Shetty"), ("Karan", "Das"), ("Kartik", "Bose"),
    ("Krishanu", "Mukherjee"), ("Lokesh", "Garg"), ("Manish", "Kohli"), ("Mayank", "Naidu"),
    ("Mihir", "Malhotra"), ("Mohit", "Varma"), ("Neeraj", "Rajan"), ("Nikhil", "Doshi"),
    ("Nilesh", "Tripathi"), ("Omkar", "Chatterjee"), ("Parth", "Pillai"), ("Piyush", "Nair"),
    ("Pranav", "Kumar"), ("Prateek", "Sharma"), ("Rahul", "Gupta"), ("Raj", "Singh"),
    ("Rajesh", "Patel"), ("Rakesh", "Mehta"), ("Ravi", "Rao"), ("Ritesh", "Joshi"),
    ("Rohan", "Reddy"), ("Rohit", "Agarwal"), ("Sahil", "Iyer"), ("Saurabh", "Shah"),
    ("Shyam", "Desai"), ("Siddharth", "Verma"),
    ("Aditi", "Sharma"), ("Akanksha", "Singh"), ("Ananya", "Patel"), ("Ankita", "Kumar"),
    ("Anusha", "Gupta"), ("Aparna", "Mehta"), ("Archana", "Joshi"), ("Arti", "Rao"),
    ("Bhavna", "Nair"), ("Deepa", "Reddy"), ("Devanshi", "Agarwal"), ("Diya", "Shah"),
    ("Isha", "Desai"), ("Jyoti", "Iyer"), ("Kavya", "Kapoor"), ("Kirti", "Mishra"),
    ("Komal", "Pandey"), ("Kritika", "Verma"), ("Lakshmi", "Yadav"), ("Madhuri", "Tiwari"),
    ("Manasi", "Pillai"), ("Meena", "Shetty"), ("Meghna", "Das"), ("Mira", "Bose"),
    ("Nandini", "Mukherjee"), ("Neha", "Garg"), ("Nikita", "Kohli"), ("Nisha", "Naidu"),
    ("Pallavi", "Malhotra"), ("Poonam", "Varma"), ("Pooja", "Rajan"), ("Prachi", "Doshi"),
    ("Priya", "Tripathi"), ("Radhika", "Chatterjee"), ("Ritu", "Pillai"), ("Riya", "Nair"),
    ("Sakshi", "Kumar"), ("Sandhya", "Sharma"), ("Shreya", "Gupta"), ("Shweta", "Singh"),
    ("Simran", "Patel"), ("Sneha", "Mehta"), ("Sonam", "Joshi"), ("Srishti", "Rao"),
    ("Swati", "Reddy"), ("Tanvi", "Agarwal"), ("Tara", "Shah"), ("Vidya", "Desai"),
]

# Sections of the one cohort: every student belongs to one section (stored in User.cohort)
COHORTS = ['Section A', 'Section B', 'Section C', 'Section D']

# Simulation only: how long a typical honest student spends on a first attempt.
# This drives the *behaviour* we simulate — it is NOT used for scoring. Scoring
# uses the PlagiarismPolicy baselines via plagiarism.tasks.
TYPICAL_SOLVE_SECONDS = {'easy': 180, 'medium': 480, 'hard': 900}

PROFILES = ['strong', 'average', 'struggling', 'cheater', 'lazy']
PROFILE_WEIGHTS = [25, 35, 20, 10, 10]


# ── Planted copying ───────────────────────────────────────────────────────────
#
# Small, realistic cases planted through behaviour and code only. Members are
# drawn from the 'cheater' profile first, then 'lazy', then anyone, and each
# student is in at most one case. A copier opens the planted question first,
# pastes the code within minutes after leaving the exam tab several times, and
# sometimes submits a quick attempt of their own before pasting.
#
#   leak    every member pastes the same leaked solution (programs.LEAKED)
#   edited  one student copies a classmate's passing program, then renames
#           every identifier, rewrites the comments and changes how it prints
#
# Phase 1 and Phase 2 must find them on their own.
PLANTS = [
    {'exam': 'Advanced JavaScript: Closures & Scope', 'question': 'Two Sum', 'kind': 'leak', 'members': 3},
    {'exam': 'Async JavaScript & Promises', 'question': 'Debounce', 'kind': 'edited', 'members': 1},
    {'exam': 'Data Structures in JavaScript', 'question': 'LRU Cache', 'kind': 'leak', 'members': 2},
    {'exam': 'Design Patterns in JavaScript', 'question': 'Observer Pattern', 'kind': 'leak', 'members': 4},
]




# ── Exams ─────────────────────────────────────────────────────────────────────
#
# Each question names its program generator explicitly via 'pool' (a key of
# _seed_programs.PROBLEMS). Test cases are chosen so that a single program can
# satisfy all of them (each case has its own input); every generated program
# is verified against them by execution.

EXAM_DATA = [
    {
        'title': 'Advanced JavaScript: Closures & Scope',
        'description': 'Deep dive into JavaScript closures, lexical scope, and the module pattern. Students will implement real-world utility functions.',
        'duration_minutes': 90,
        'questions': [
            {
                'title': 'Two Sum',
                'pool': 'two_sum',
                'description': 'Given an integer array nums and a target, return indices of the two numbers that add up to target. You may assume exactly one solution exists.\n\nInput (line 1): array length n\nInput (line 2): space-separated integers\nInput (line 3): target\nOutput: two indices separated by space',
                'difficulty': 'easy', 'max_attempts': 3,
                'test_cases': [
                    ('3\n2 7 11\n9', '0 1'),
                    ('4\n3 2 4 6\n6', '1 2'),
                    ('3\n1 5 3\n8', '1 2'),
                ]
            },
            {
                'title': 'Memoize',
                'pool': 'memoize_fib',
                'description': 'Implement a memoize function that caches results of expensive function calls. The cached function should return the same result for the same arguments without recomputing.\n\nInput: single integer n\nOutput: fibonacci(n) using memoized recursion',
                'difficulty': 'medium', 'max_attempts': 3,
                'test_cases': [
                    ('10', '55'),
                    ('15', '610'),
                    ('20', '6765'),
                ]
            },
            {
                'title': 'Curry Function',
                'pool': 'curry_multiply',
                'description': 'Implement a curry function that transforms a function of N arguments into N chained unary calls.\ncurry(add)(1)(2)(3) should equal add(1,2,3).\n\nInput: three space-separated integers a b c\nOutput: result of curried multiply(a)(b)(c)',
                'difficulty': 'medium', 'max_attempts': 3,
                'test_cases': [
                    ('2 3 4', '24'),
                    ('1 5 6', '30'),
                    ('3 3 3', '27'),
                ]
            },
        ]
    },
    {
        'title': 'Async JavaScript & Promises',
        'description': 'Master asynchronous JavaScript patterns including Promises, async/await, and concurrent execution strategies.',
        'duration_minutes': 75,
        'questions': [
            {
                'title': 'Custom Promise.all',
                'pool': 'promise_all',
                'description': 'Implement your own version of Promise.all from scratch. It should resolve with an array of all resolved values in order, and reject immediately if any promise rejects.\n\nInput: space-separated integers. Each value is wrapped in a promise; later values resolve sooner.\nOutput: the resolved values, space-separated, in input order',
                'difficulty': 'hard', 'max_attempts': 2,
                'test_cases': [
                    ('1 2 3', '1 2 3'),
                    ('10 20', '10 20'),
                    ('7', '7'),
                ]
            },
            {
                'title': 'Debounce',
                'pool': 'debounce',
                'description': 'Implement a debounce function that delays invoking func until after wait milliseconds have elapsed since the last invocation. Used extensively in search inputs and resize handlers.\n\nInput: n — how many times the debounced function is called in a rapid burst\nOutput: number of times the function actually executed',
                'difficulty': 'medium', 'max_attempts': 3,
                'test_cases': [
                    ('3', '1'),
                    ('5', '1'),
                ]
            },
            {
                'title': 'Throttle',
                'pool': 'throttle',
                'description': 'Implement a throttle function that ensures the given function is called at most once in the specified time interval, no matter how many times it is invoked.\n\nInput: k — number of bursts (3 rapid calls each, 250ms apart, 100ms throttle)\nOutput: call count after the last burst',
                'difficulty': 'medium', 'max_attempts': 3,
                'test_cases': [
                    ('1', '1'),
                    ('2', '2'),
                    ('3', '3'),
                ]
            },
        ]
    },
    {
        'title': 'Functional Programming in JS',
        'description': 'Explore functional programming paradigms in JavaScript — pure functions, immutability, compose, and higher-order functions.',
        'duration_minutes': 60,
        'questions': [
            {
                'title': 'Flatten Nested Array',
                'pool': 'flatten_deep',
                'description': 'Write a function that deeply flattens a nested array of any depth.\n\nInput: JSON array (potentially nested)\nOutput: flattened values space-separated',
                'difficulty': 'easy', 'max_attempts': 3,
                'test_cases': [
                    ('[1,[2,[3,[4]]],5]', '1 2 3 4 5'),
                    ('[[1,2],[3,[4,5]]]', '1 2 3 4 5'),
                    ('[1,2,3]', '1 2 3'),
                ]
            },
            {
                'title': 'Deep Clone',
                'pool': 'deep_clone',
                'description': 'Implement a deep clone function that creates a completely independent copy of a nested object/array. Mutating the clone must not affect the original.\n\nInput: JSON object with a nested inner.name property\nOutput: the original inner.name after the clone\'s inner.name is set to "modified"',
                'difficulty': 'medium', 'max_attempts': 3,
                'test_cases': [
                    ('{"inner":{"name":"Alice"},"scores":[1,2,3]}', 'Alice'),
                    ('{"inner":{"name":"Bob","x":1},"tags":["a"]}', 'Bob'),
                ]
            },
        ]
    },
    {
        'title': 'Data Structures in JavaScript',
        'description': 'Implement core data structures from scratch using JavaScript classes — stacks, queues, caches, and trees.',
        'duration_minutes': 120,
        'questions': [
            {
                'title': 'LRU Cache',
                'pool': 'lru_cache',
                'description': 'Design a data structure that follows the Least Recently Used (LRU) cache eviction policy. Implement get(key) and put(key, value) — both in O(1) time.\n\nInput (line 1): capacity\nInput (following lines): "put key value" or "get key"\nOutput: results of get operations (space-separated)',
                'difficulty': 'hard', 'max_attempts': 2,
                'test_cases': [
                    ('2\nput 1 10\nput 2 20\nget 1\nput 3 30\nget 2', '10 -1'),
                    ('2\nput 1 1\nput 2 2\nput 1 5\nput 3 3\nget 1\nget 2\nget 3', '5 -1 3'),
                    ('1\nput 1 1\nput 2 2\nget 1\nget 2', '-1 2'),
                ]
            },
            {
                'title': 'Event Emitter',
                'pool': 'event_emitter',
                'description': 'Build a Node.js-style EventEmitter class with on, off, emit, and once methods. The once method registers a listener that fires only one time then removes itself.\n\nInput: n — how many times "ping" is emitted (one on() listener and one once() listener are registered)\nOutput: "<on count> <once count>"',
                'difficulty': 'medium', 'max_attempts': 3,
                'test_cases': [
                    ('3', '3 1'),
                    ('1', '1 1'),
                    ('0', '0 0'),
                ]
            },
        ]
    },
    {
        'title': 'Design Patterns in JavaScript',
        'description': 'Implement classic software design patterns using modern JavaScript — Observer, Singleton, Factory, and Proxy.',
        'duration_minutes': 90,
        'questions': [
            {
                'title': 'Observer Pattern',
                'pool': 'observer',
                'description': 'Implement the Observer (pub/sub) pattern with a Subject class that maintains a list of observers. When state changes via setState, all subscribers receive the new state via their update method.\n\nInput: space-separated states, applied in order with setState\nOutput: comma-separated list of states received by observer',
                'difficulty': 'medium', 'max_attempts': 3,
                'test_cases': [
                    ('online offline', 'online,offline'),
                    ('active idle active', 'active,idle,active'),
                ]
            },
        ]
    },
    {
        'title': 'JavaScript Interview Gauntlet',
        'description': 'High-pressure mixed exam covering all advanced JS topics. Questions sourced from real FAANG and startup interviews.',
        'duration_minutes': 120,
        'questions': [
            {
                'title': 'Flatten Array (Interview)',
                'pool': 'flatten_no_builtin',
                'description': 'Classic interview question. Flatten a deeply nested array without using Array.prototype.flat.\n\nInput: JSON array\nOutput: space-separated numbers',
                'difficulty': 'easy', 'max_attempts': 3,
                'test_cases': [
                    ('[1,[2,3],[4,[5,6]]]', '1 2 3 4 5 6'),
                    ('[[[[1]]],2,[[3]]]', '1 2 3'),
                ]
            },
            {
                'title': 'Implement Curry (Interview)',
                'pool': 'curry_multiply',
                'description': 'Implement curry for functions of any arity — must support both curried(a)(b)(c) and curried(a,b)(c) call styles.\n\nInput: three integers\nOutput: result of multiply(a)(b)(c)',
                'difficulty': 'medium', 'max_attempts': 3,
                'test_cases': [
                    ('4 5 2', '40'),
                    ('2 2 2', '8'),
                ]
            },
            {
                'title': 'Promise.all + Timeout',
                'pool': 'promise_all_timeout',
                'description': 'Implement promiseAllWithTimeout — resolves if all promises complete within the timeout, otherwise rejects with "TIMEOUT".\n\nInput (line 1): timeout in ms\nInput (line 2): space-separated delays in ms; promise i resolves with i+1 after its delay\nOutput: resolved values (space-separated) or TIMEOUT',
                'difficulty': 'hard', 'max_attempts': 2,
                'test_cases': [
                    ('150\n10 20 30', '1 2 3'),
                    ('50\n10 300', 'TIMEOUT'),
                    ('150\n5', '1'),
                ]
            },
        ]
    },
]

# (exam title, question title) -> question spec from EXAM_DATA
QUESTION_SPECS = {
    (edata['title'], qdata['title']): qdata
    for edata in EXAM_DATA
    for qdata in edata['questions']
}


def pool_for_question(exam_title, question_title):
    """
    The problem (program generator in _seed_programs.PROBLEMS) for a seeded
    question, looked up explicitly by (exam title, question title). Raises
    CommandError if the question has none: the seed must never fall back to
    some other question's code.
    """
    spec = QUESTION_SPECS.get((exam_title, question_title))
    if spec is None:
        raise CommandError(f'No solution pool for question "{question_title}" in exam "{exam_title}"')
    problem = spec.get('pool')
    if problem not in programs.PROBLEMS:
        raise CommandError(f'Question "{question_title}" names unknown solution pool {problem!r}')
    return problem


def outputs_match(output, expected):
    """Same comparison the execution task uses."""
    return output.strip() == expected.strip()


def production_similarity(codes):
    """Pairwise similarity exactly as Phase 2 computes it (normalise, TF-IDF, cosine)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from plagiarism.tasks import normalize_code
    normalized = [normalize_code(c, 'javascript') for c in codes]
    return cosine_similarity(TfidfVectorizer().fit_transform(normalized))


# ── Planning (pure: no database) ──────────────────────────────────────────────

def _choose_plants(profiles):
    """Fills PLANTS with roster indices; each student copies in at most one case."""
    rng = random.Random(99)
    pools = []
    for wanted in ('cheater', 'lazy', None):
        group = [i for i, p in enumerate(profiles)
                 if (p == wanted if wanted else p not in ('cheater', 'lazy'))]
        rng.shuffle(group)
        pools.extend(group)
    plants, used = [], 0
    for spec in PLANTS:
        size = spec['members']
        minimum = 2 if spec['kind'] == 'leak' else 1
        members = pools[used:used + size]
        if len(members) < minimum:
            continue  # tiny roster: not enough students for this case
        used += len(members)
        plants.append({**spec, 'members': members, 'source': None, 'code': None})
    return plants


def _final_attempts(attempts, key):
    """Each student's attempt Phase 2 compares: first passing attempt, else latest."""
    best = {}
    for a in attempts:
        if a['key'] != key:
            continue
        cur = best.get(a['student'])
        if cur is None or (not cur['expect_pass'] and (a['expect_pass'] or a['attempt'] > cur['attempt'])):
            best[a['student']] = a
    return best


def plan_seed(n_students, policy=None):
    """
    Simulates the whole cohort without touching the database and returns
    {'profiles', 'attempts', 'plants'}. Deterministic for a given roster size.

    Only behaviour is simulated (time, paste, tab switches, whether an attempt
    is right or wrong); each attempt's program comes from the student's own
    author profile for that question (_seed_programs), and its real status is
    checked by execution before anything is written.

    time_to_complete_seconds follows the frontend's definition: seconds since
    the exam window opened at the moment of submission (exam_duration -
    time_left), so it accumulates across questions.
    """
    policy = policy or policy_defaults()
    rng = random.Random(42)
    profiles = [rng.choices(PROFILES, weights=PROFILE_WEIGHTS)[0] for _ in range(n_students)]

    # Every student gets a distinct structure (core, layout+reader, parser)
    # per question, plus their own habits and names.
    authors = {}
    for key in QUESTION_SPECS:
        problem = pool_for_question(*key)
        qrng = random.Random(f'authors/{key[0]}/{key[1]}')
        structs = programs.structures(problem)
        qrng.shuffle(structs)
        authors[key] = [programs.make_author(problem, structs[i % len(structs)], qrng.randrange(1 << 30))
                        for i in range(n_students)]

    plants = _choose_plants(profiles)
    planted = {(m, p['exam']): (idx, p) for idx, p in enumerate(plants) for m in p['members']}

    attempts = []

    def add(**kw):
        attempts.append(kw)

    for s in range(n_students):
        profile = profiles[s]
        # 'cheater' students only cheat where a solution has leaked (PLANTS);
        # everywhere else they work like an average student
        pass_rates = _profile_pass_rates('average' if profile == 'cheater' else profile)
        for edata in EXAM_DATA:
            exam_title = edata['title']
            qs = edata['questions']
            duration_s = edata['duration_minutes'] * 60
            coverage = rng.uniform(0.75, 1.0)
            attempted = rng.sample(qs, k=max(1, int(len(qs) * coverage)))

            plant_idx, plant = planted.get((s, exam_title), (None, None))
            planted_q = None
            if plant:
                planted_q = next(q for q in qs if q['title'] == plant['question'])
                attempted = [planted_q] + [q for q in attempted if q is not planted_q]
                clock = rng.randint(5, 25)  # joined promptly, opened the leaked question first
            else:
                clock = rng.randint(0, 180)  # joined a little after the window opened

            out_of_time = False
            for q in attempted:
                if out_of_time:
                    break
                key = (exam_title, q['title'])
                problem = q['pool']
                author = authors[key][s]
                bugs = programs.bugs_for(problem, author['core'])
                base = dict(student=s, key=key, problem=problem, duration_s=duration_s)

                if q is planted_q:
                    baseline = policy[f"{q['difficulty']}_baseline_s"]
                    attempt_no = 1
                    if q['max_attempts'] >= 2 and rng.random() < 0.3:
                        # a quick attempt of their own first, then the paste
                        clock += max(10, int(baseline * rng.uniform(0.05, 0.12)))
                        add(**base, attempt=1, code=programs.build_program(problem, author, bug=rng.choice(bugs)),
                            expect_pass=False, clock=clock, paste=False, paste_frac=0.0,
                            tabs=rng.randint(1, 3), plant=None)
                        attempt_no = 2
                        clock += rng.randint(20, 40)
                    else:
                        clock += max(10, int(baseline * rng.uniform(0.08, 0.25)))
                    add(**base, attempt=attempt_no, code=None,  # filled in once the plant's code is known
                        expect_pass=True, clock=clock, paste=True, paste_frac=rng.uniform(0.92, 1.0),
                        tabs=rng.randint(5, 9), plant=plant_idx)
                    continue

                typical = TYPICAL_SOLVE_SECONDS[q['difficulty']]
                prev_bug = None
                for att in range(q['max_attempts']):
                    if att == 0:
                        if profile == 'strong':
                            spent = rng.randint(int(typical * 0.5), int(typical * 1.2))
                        elif profile == 'struggling':
                            spent = rng.randint(int(typical * 1.2), int(typical * 2.5))
                        else:
                            spent = rng.randint(int(typical * 0.6), int(typical * 1.8))
                    else:
                        spent = rng.randint(int(typical * 0.15), int(typical * 0.6))
                    if clock + spent >= duration_s:
                        out_of_time = True
                        break
                    clock += spent

                    passed = rng.random() < pass_rates[att]
                    if passed:
                        code = programs.build_program(problem, author)
                    else:
                        # a fresh mistake on a retry when there is another one to make
                        bug = rng.choice([b for b in bugs if b != prev_bug] or bugs)
                        prev_bug = bug
                        code = programs.build_program(problem, author, bug=bug)

                    if profile == 'lazy':
                        paste = rng.random() < 0.4
                        paste_frac = rng.randint(50, 200) / len(code) if paste else 0.0
                        tabs = rng.randint(1, 6)
                    else:
                        paste = rng.random() < 0.1
                        paste_frac = rng.randint(10, 50) / len(code) if paste else 0.0
                        tabs = rng.randint(0, 4) if profile == 'cheater' else rng.randint(0, 2)

                    add(**base, attempt=att + 1, code=code, expect_pass=passed, clock=clock,
                        paste=paste, paste_frac=paste_frac, tabs=tabs, plant=None)
                    if passed:
                        break

    for idx, plant in enumerate(plants):
        key = (plant['exam'], plant['question'])
        problem = pool_for_question(*key)
        if plant['kind'] == 'leak':
            plant['code'] = programs.LEAKED[problem]
        else:
            _plant_edited_copy(plant, key, problem, attempts, authors, policy['similarity_threshold'])
        for a in attempts:
            if a['plant'] == idx:
                a['code'] = plant['code']

    # a case that could not be planted (tiny roster) leaves no copied attempt behind
    attempts = [a for a in attempts if a['code'] is not None]
    for a in attempts:
        a['paste_chars'] = int(len(a['code']) * a['paste_frac'])
    return {'profiles': profiles, 'attempts': attempts, 'plants': plants, 'authors': authors}


def _plant_edited_copy(plant, key, problem, attempts, authors, threshold):
    """
    One student copies a classmate's passing program and edits it lightly:
    every identifier renamed, comments rewritten, and the output printed a
    different way (console.log <-> process.stdout.write). Structure is kept.

    The copied classmate (source) is an honest student who passed the
    question. Candidates are tried from the most unusual program in the cohort
    (under the production metric) down, and the first whose edited copy still
    clearly resembles it (>= threshold + 0.05) and resembles nobody else
    (< threshold - 0.02) is used, so the planted case is clean: Phase 2 should
    pair the copier with the source and with no one else.
    """
    finals = _final_attempts(attempts, key)
    cohort = [s for s in sorted(finals) if s not in plant['members']]
    eligible = [s for s in cohort if finals[s]['expect_pass']]
    if not eligible:
        return
    sim = production_similarity([finals[s]['code'] for s in cohort])
    pos = {s: i for i, s in enumerate(cohort)}

    def most_alike(s):
        row = [sim[pos[s], j] for j in range(len(cohort)) if j != pos[s]]
        return max(row) if row else 0.0

    swap = {'log': 'write', 'write': 'log', 'helper_log': 'helper_write', 'helper_write': 'helper_log'}
    erng = random.Random(f'edited/{key[0]}/{key[1]}')
    names_seed, comment_seed = erng.randrange(1 << 30), erng.randrange(1 << 30)
    for source in sorted(eligible, key=lambda s: (most_alike(s), s)):
        author = authors[key][source]
        copy = programs.build_program(problem, author, names_seed=names_seed,
                                      printer=swap[author['printer']], comment_seed=comment_seed)
        with_copy = production_similarity([finals[s]['code'] for s in cohort] + [copy])[-1][:-1]
        to_source = with_copy[pos[source]]
        to_others = max((v for j, v in enumerate(with_copy) if j != pos[source]), default=0.0)
        if to_source >= threshold + 0.05 and to_others < threshold - 0.02:
            plant['source'], plant['code'] = source, copy
            return


# ── Verification by execution ─────────────────────────────────────────────────

def execute_and_verify(jobs, max_workers=None):
    """
    jobs: iterable of ((exam title, question title), code, expect_pass).

    Runs every distinct program against its question's test cases with the
    real executor and returns {(code, input_data): (output, error, exec_ms)}.
    Raises CommandError if a program meant to pass fails any test case, or a
    deliberately buggy one passes all of them: the seed refuses to record a
    status that the code would not actually earn.
    """
    from execution.tasks import run_local

    jobs = {(key, code): expect for key, code, expect in jobs}
    runs = sorted({(code, inp) for (key, code) in jobs for inp, _ in QUESTION_SPECS[key]['test_cases']})
    workers = max_workers or min(16, max(4, (os.cpu_count() or 2) * 2))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        outcomes = list(ex.map(lambda r: run_local(r[0], 'javascript', r[1]), runs))
    table = dict(zip(runs, outcomes))

    problems = []
    for (key, code), expect in sorted(jobs.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        cases = QUESTION_SPECS[key]['test_cases']
        passes = [outputs_match(table[(code, inp)][0], exp) for inp, exp in cases]
        if expect and not all(passes):
            failing = [(inp, table[(code, inp)][:2]) for (inp, _), ok in zip(cases, passes) if not ok]
            problems.append(f'{key[1]}: program meant to pass fails {failing}\n{code}')
        if not expect and all(passes):
            problems.append(f'{key[1]}: deliberately buggy program passes every test case\n{code}')
    if problems:
        raise CommandError('Programs are inconsistent with their test cases:\n  ' + '\n  '.join(problems[:5]))
    return table


def policy_defaults():
    return {f: PlagiarismPolicy._meta.get_field(f).default for f in POLICY_FIELDS}


class Command(BaseCommand):
    help = 'Seed 98 Indian JS students with realistic, execution-verified submissions'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Clear all existing exam/student data first')
        parser.add_argument('--students', type=int, default=None,
                            help='Only seed the first N students (used by tests)')

    def handle(self, *args, **options):
        started = time.monotonic()
        n = len(INDIAN_STUDENTS) if options['students'] is None else min(options['students'], len(INDIAN_STUDENTS))

        # Plan and execute every program first, before touching the database:
        # if any program's real result disagrees with the plan we abort with
        # nothing deleted.
        self.stdout.write('Planning submissions (every student writes their own programs)...')
        plan = plan_seed(n)
        attempts = plan['attempts']
        self.stdout.write(f'  {len(attempts)} attempts, {len({a["code"] for a in attempts})} distinct programs')
        self.stdout.write('Verifying solution pools against test cases...')
        exec_table = execute_and_verify((a['key'], a['code'], a['expect_pass']) for a in attempts)
        self.stdout.write(f'  {len(exec_table)} executions verified (0 code/status mismatches)')

        with transaction.atomic():
            if options['clear']:
                self._clear()
            elif Submission.objects.filter(exam__title__in=[e['title'] for e in EXAM_DATA]).exists():
                raise CommandError('Seed data already present — re-run with --clear')

            self._fix_superuser_roles()
            policy = self._reset_policy_to_defaults()
            trainer = self._ensure_trainer()
            exams = self._create_exams(trainer)
            students = self._create_students(n)
            self._enroll_students(students, exams)
            all_questions = [q for exam in exams for q in exam.questions.all()]
            self._write_submissions(plan, students, exams, exec_table)
            self._describe_plants(plan, students)
            self._score_behaviour(exams, policy)
            self._run_exam_close_checks(exams)
            # past exams were reviewed after they ended: Investigation starts with no backlog
            call_command('settle_past_reviews', yes=True, stdout=io.StringIO())
            demo = self._create_demo_open_exam(trainer, students)
            self._ensure_single_open_exam(demo)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone! {len(students)} students, {len(exams)} exams, '
            f'{len(all_questions)} questions seeded in {time.monotonic() - started:.0f}s.'
        ))

    # ── reset ────────────────────────────────────────────────────────────────

    def _clear(self):
        self.stdout.write('Clearing existing data...')
        from support.models import DisputeRequest
        # disputes and audit logs point at flag ids that are about to disappear
        DisputeRequest.objects.all().delete()
        ReviewAuditLog.objects.all().delete()
        BehaviouralFlag.objects.all().delete()
        PlagiarismFlag.objects.all().delete()
        Result.objects.all().delete()
        Submission.objects.all().delete()
        ExamEnrollment.objects.all().delete()
        TestCase.objects.all().delete()
        Question.objects.all().delete()
        Exam.objects.all().delete()  # cascades PlagiarismRun / AI summaries
        # Never delete staff/superusers (e.g. a manually created 'admin'), even
        # if an old account was created with the model's default 'student' role.
        User.objects.filter(role='student', is_superuser=False, is_staff=False).delete()

    def _fix_superuser_roles(self):
        """createsuperuser now defaults to trainer; repair accounts made before that."""
        fixed = User.objects.filter(is_superuser=True, role='student').update(role='trainer')
        if fixed:
            self.stdout.write(f'  Set role=trainer on {fixed} superuser account(s)')

    def _reset_policy_to_defaults(self):
        """
        Scoring uses the live PlagiarismPolicy, so pin it to the model defaults
        (weights sum to 1.0) before scoring, and drop the Redis copy so
        get_policy() reads the row we just wrote.
        """
        defaults = policy_defaults()
        if abs(sum(defaults[f] for f in ('paste_weight', 'time_weight', 'tab_weight', 'submission_weight')) - 1.0) > 1e-9:
            raise CommandError(f'PlagiarismPolicy model default weights do not sum to 1.0: {defaults}')
        policy = PlagiarismPolicy.get()
        before = {f: getattr(policy, f) for f in POLICY_FIELDS}
        if before != defaults:
            for f, v in defaults.items():
                setattr(policy, f, v)
            policy.updated_by = None
            policy.save()
            PolicyVersion.objects.create(
                changed_by=None,
                change_reason='seed_data: reset to model defaults',
                snapshot_before=before,
                snapshot_after=defaults,
            )
            self.stdout.write('  PlagiarismPolicy reset to model defaults')
        cache.delete('plagiarism_policy')
        return defaults

    # ── users / exams ────────────────────────────────────────────────────────

    def _ensure_trainer(self):
        trainer, created = User.objects.get_or_create(
            username='venugopal',
            defaults={'email': 'venugopal@codemas.dev', 'role': 'trainer', 'first_name': 'Venugopal'}
        )
        if created:
            trainer.set_password(os.getenv('SEED_TRAINER_PASSWORD', 'trainer123'))
            trainer.save()
            self.stdout.write('Created trainer account (venugopal / trainer123)')
        elif trainer.role != 'trainer':
            trainer.role = 'trainer'
            trainer.save(update_fields=['role'])
        return trainer

    def _create_exams(self, trainer):
        exams = []
        # Anchor in mid-2024 — weekly contests during the Masai cohort
        cohort_start = timezone.make_aware(datetime(2024, 6, 3))
        for i, edata in enumerate(EXAM_DATA):
            exam, _ = Exam.objects.get_or_create(
                title=edata['title'],
                defaults={
                    'description': edata['description'],
                    'created_by': trainer,
                    'duration_minutes': edata['duration_minutes'],
                    'is_active': False,  # historical — already closed, prevents auto_manage_exams re-trigger
                    'start_time': cohort_start + timedelta(weeks=i),
                    'end_time': cohort_start + timedelta(weeks=i) + timedelta(minutes=edata['duration_minutes']),
                }
            )
            for qdata in edata['questions']:
                pool_for_question(edata['title'], qdata['title'])  # fail before writing anything odd
                q, created = Question.objects.get_or_create(
                    exam=exam,
                    title=qdata['title'],
                    defaults={
                        'description': qdata['description'],
                        'difficulty': qdata['difficulty'],
                        'max_attempts': qdata['max_attempts'],
                        'language': 'javascript',
                        'tags': 'javascript,interview',
                    }
                )
                if created:
                    for inp, out in qdata['test_cases']:
                        TestCase.objects.create(
                            question=q,
                            input_data=inp,
                            expected_output=out,
                            is_hidden=True,
                        )
                else:
                    existing = list(q.test_cases.order_by('id').values_list('input_data', 'expected_output'))
                    if existing != list(qdata['test_cases']):
                        raise CommandError(
                            f'Question "{q.title}" has stale test cases in the DB — re-run with --clear'
                        )
            exams.append(exam)
            self.stdout.write(f'  Exam: {exam.title}')
        return exams

    def _create_demo_open_exam(self, trainer, students):
        """
        The rest of the seed is deliberately historical (is_active=False) so
        it doesn't re-trigger auto_manage_exams' plagiarism batch on every run.
        For a live demo we need exactly one exam that's actually open right
        now, with every seeded student enrolled and its questions ready.
        """
        now = timezone.now()
        demo_questions = [
            {
                'title': 'Find Target in Sorted Array',
                'description': (
                    'Given a sorted array of integers and a target value, return the index of '
                    'the target in the array. If the target is not found, return -1.\n'
                    'Input format:\n- First line: n (number of elements in the array)\n'
                    '- Second line: n space-separated integers (the sorted array)\n'
                    '- Third line: target (the integer to search for)\n'
                    'Output format:\n- A single integer representing the index of the target or -1 if not found.'
                ),
                'test_cases': [
                    ('5\n1 2 3 4 5\n3\n', '2'),
                    ('7\n10 20 30 40 50 60 70\n25\n', '-1'),
                    ('3\n5 15 25\n15\n', '1'),
                ],
            },
            {
                'title': 'Count Occurrences of Target',
                'description': (
                    'Given a sorted array of integers and a target value, return the count of '
                    'occurrences of the target in the array.\n'
                    'Input format:\n- First line: n (number of elements in the array)\n'
                    '- Second line: n space-separated integers (the sorted array)\n'
                    '- Third line: target (the integer to search for)\n'
                    'Output format:\n- A single integer representing the count of occurrences of the target.'
                ),
                'test_cases': [
                    ('6\n1 1 2 2 2 3\n2\n', '3'),
                    ('5\n4 4 4 4 4\n4\n', '5'),
                    ('4\n1 2 3 4\n5\n', '0'),
                ],
            },
            {
                'title': 'Find First and Last Position',
                'description': (
                    'Given a sorted array of integers and a target value, return the first and '
                    'last position of the target in the array.\n'
                    'Input format:\n- First line: n (number of elements in the array)\n'
                    '- Second line: n space-separated integers (the sorted array)\n'
                    '- Third line: target (the integer to search for)\n'
                    'Output format:\n- Two space-separated integers representing the first and last '
                    'positions of the target, or -1 -1 if not found.'
                ),
                'test_cases': [
                    ('7\n5 7 7 8 8 10 10\n8\n', '3 4'),
                    ('5\n1 2 3 4 5\n6\n', '-1 -1'),
                    ('6\n1 1 2 2 2 3\n1\n', '0 1'),
                ],
            },
        ]

        exam, _ = Exam.objects.get_or_create(
            title='Python Binary Search Exam',
            defaults={
                'description': 'An exam focused on binary search algorithms in Python.',
                'created_by': trainer,
                'duration_minutes': 60,
            },
        )
        # Force it open regardless of whether it pre-existed from an earlier run.
        Exam.objects.filter(pk=exam.pk).update(
            is_active=True,
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=14),
        )
        exam.refresh_from_db()

        for qdata in demo_questions:
            q, created = Question.objects.get_or_create(
                exam=exam,
                title=qdata['title'],
                defaults={
                    'description': qdata['description'],
                    'difficulty': 'medium',
                    'max_attempts': 3,
                    'language': 'python',
                },
            )
            starter = DEMO_STARTERS.get(q.title)
            if starter and not (q.starter_code_javascript or q.starter_code_python):
                Question.objects.filter(pk=q.pk).update(
                    starter_code_javascript=starter['javascript'], starter_code_python=starter['python'])
            if created:
                for inp, out in qdata['test_cases']:
                    TestCase.objects.create(
                        question=q,
                        input_data=inp,
                        expected_output=out,
                        is_hidden=True,
                    )

        enrollments = [ExamEnrollment(exam=exam, student=s) for s in students]
        ExamEnrollment.objects.bulk_create(enrollments, ignore_conflicts=True)

        self.stdout.write(f'  Demo open exam: {exam.title} (is_active=True, open now)')
        return exam

    def _ensure_single_open_exam(self, demo):
        # .update() deliberately bypasses the pre_save signal: these exams are
        # being reset, not "closed", so no plagiarism batch should be queued.
        closed = Exam.objects.filter(is_active=True).exclude(pk=demo.pk).update(is_active=False)
        if closed:
            self.stdout.write(f'  Deactivated {closed} other open exam(s)')

    def _create_students(self, limit=None):
        students = []
        cohort_cycle = COHORTS * 30  # enough to assign 100 students
        roster = INDIAN_STUDENTS if limit is None else INDIAN_STUDENTS[:limit]
        for i, (first, last) in enumerate(roster):
            username = f'{first.lower()}_{last.lower()}{i}'
            email = f'{username}@codemas.dev'
            student, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'role': 'student',
                    'cohort': cohort_cycle[i],
                    'first_name': first,
                    'last_name': last,
                }
            )
            if created:
                student.set_password(os.getenv('SEED_STUDENT_PASSWORD', 'student123'))
                student.save()
            students.append(student)
        self.stdout.write(f'  Created {len(students)} students')
        return students

    def _enroll_students(self, students, exams):
        enrollments = [
            ExamEnrollment(exam=exam, student=student)
            for exam in exams
            for student in students
        ]
        ExamEnrollment.objects.bulk_create(enrollments, ignore_conflicts=True)
        self.stdout.write('  Enrolled all students in all exams')

    # ── submissions ──────────────────────────────────────────────────────────

    def _write_submissions(self, plan, students, exams, exec_table):
        """
        Writes the planned attempts. Status and Result rows come from the real
        execution outputs (already checked against the plan).
        """
        from plagiarism.tasks import normalize_code

        exam_by_title = {e.title: e for e in exams}
        questions = {}
        for exam in exams:
            for q in exam.questions.order_by('id'):
                tcs = list(q.test_cases.order_by('id'))
                spec_cases = QUESTION_SPECS[(exam.title, q.title)]['test_cases']
                if [(t.input_data, t.expected_output) for t in tcs] != list(spec_cases):
                    raise CommandError(f'Question "{q.title}" has stale test cases in the DB — re-run with --clear')
                questions[(exam.title, q.title)] = (q, tcs)

        subs, runs_per_sub = [], []
        for a in plan['attempts']:
            exam = exam_by_title[a['key'][0]]
            question, tcs = questions[a['key']]
            runs = [exec_table[(a['code'], tc.input_data)] for tc in tcs]
            all_passed = all(outputs_match(out, tc.expected_output) for (out, _, _), tc in zip(runs, tcs))
            if all_passed != a['expect_pass']:  # execute_and_verify already guarantees this
                raise CommandError(f'{question.title}: planned passed={a["expect_pass"]} but execution says {all_passed}')
            sub = Submission(
                student=students[a['student']],
                exam=exam,
                question=question,
                code=a['code'],
                normalized_code=normalize_code(a['code'], 'javascript'),
                language='javascript',
                attempt_number=a['attempt'],
                status='passed' if all_passed else 'failed',
                time_remaining_seconds=a['duration_s'] - a['clock'],
                execution_time_ms=sum(ms for _, _, ms in runs),
                had_paste_event=a['paste'],
                paste_char_count=a['paste_chars'],
                time_to_complete_seconds=a['clock'],
                tab_switch_count=a['tabs'],
                ip_address='127.0.0.1',
            )
            subs.append(sub)
            runs_per_sub.append((runs, tcs, exam.start_time + timedelta(seconds=a['clock'])))

        Submission.objects.bulk_create(subs, batch_size=500)
        # submitted_at is auto_now_add: set it afterwards, inside the exam
        # window and in attempt order
        for sub, (_, _, at) in zip(subs, runs_per_sub):
            sub.submitted_at = at
        Submission.objects.bulk_update(subs, ['submitted_at'], batch_size=500)
        Result.objects.bulk_create([
            Result(
                submission=sub,
                test_case=tc,
                passed=outputs_match(out, tc.expected_output),
                actual_output=out,
                execution_time_ms=ms,
                error_message=err,
            )
            for sub, (runs, tcs, _) in zip(subs, runs_per_sub)
            for (out, err, ms), tc in zip(runs, tcs)
        ], batch_size=1000)
        self.stdout.write(f'  Created {len(subs)} submissions (results from real execution)')

    def _describe_plants(self, plan, students):
        for plant in plan['plants']:
            if not plant['code']:
                continue
            names = ', '.join(students[m].username for m in plant['members'])
            if plant['kind'] == 'leak':
                self.stdout.write(f'  Planted: {len(plant["members"])} students paste a leaked '
                                  f'"{plant["question"]}" solution ({names})')
            else:
                self.stdout.write(f'  Planted: {names} pastes an edited copy of '
                                  f'{students[plant["source"]].username}\'s "{plant["question"]}"')

    # ── integrity scoring (production code) ──────────────────────────────────

    def _score_behaviour(self, exams, policy):
        """
        Phase 1 as production runs it per submission: run_behavioural_check on
        every submission, which scores with compute_behavioural_risk under the
        live policy and stores a BehaviouralFlag only above min_risk_score.
        """
        from plagiarism.tasks import get_policy, run_behavioural_check

        live = get_policy()
        if any(live[k] != policy[k] for k in live):
            raise CommandError(f'get_policy() returned {live}, expected the reset defaults {policy}')

        ids = list(Submission.objects.filter(exam__in=exams).order_by('id').values_list('id', flat=True))
        with contextlib.redirect_stdout(io.StringIO()):  # the task prints one line per submission
            for sub_id in ids:
                run_behavioural_check(sub_id)
        flags = BehaviouralFlag.objects.filter(submission__exam__in=exams).count()
        self.stdout.write(f'  Phase 1 (production run_behavioural_check): {flags} flags from {len(ids)} submissions')

    def _run_exam_close_checks(self, exams):
        """
        Phase 2 through the real exam-close entry point on every closed exam:
        run_exam_plagiarism_check(exam_id, trigger='exam_close', notify=False).
        It records a PlagiarismRun, re-scores Phase 1, and queues one
        run_question_plagiarism_check per question with apply_async. Celery is
        switched to eager mode for the duration, so those per-question tasks
        run here, in order, inside this transaction, instead of on a worker
        (which could not see the uncommitted rows). notify=False: no trainer
        email and no AI explanation for demo data. Nothing else changes.
        """
        from codemas.celery import app as celery_app
        from plagiarism.tasks import run_exam_plagiarism_check

        conf = celery_app.conf
        saved = (conf.task_always_eager, conf.task_eager_propagates)
        conf.task_always_eager, conf.task_eager_propagates = True, True
        try:
            for exam in exams:
                if exam.is_active:
                    raise CommandError(f'"{exam.title}" is open; Phase 2 only runs on closed exams')
                with contextlib.redirect_stdout(io.StringIO()):  # the tasks print per question / pair
                    run_exam_plagiarism_check(exam.id, trigger='exam_close', notify=False)
                run = PlagiarismRun.objects.filter(exam=exam).order_by('-ran_at', '-id').first()
                if run is None or run.status != 'completed':
                    raise CommandError(f'Phase 2 did not complete for "{exam.title}"')
                students = len(
                    {sid for pair in PlagiarismFlag.objects.filter(submission_1__exam=exam)
                     .values_list('submission_1__student_id', 'submission_2__student_id') for sid in pair})
                self.stdout.write(
                    f'  Phase 2 (exam close) "{exam.title}": {run.b_high_confidence} HIGH suspects, '
                    f'{run.s_flags_total} similarity flags, {students} students flagged')
        finally:
            conf.task_always_eager, conf.task_eager_propagates = saved


def _profile_pass_rates(profile):
    return {
        'strong':    [0.80, 0.95, 0.99],
        'average':   [0.55, 0.75, 0.88],
        'struggling':[0.25, 0.45, 0.60],
        'cheater':   [0.90, 0.98, 0.99],
        'lazy':      [0.35, 0.55, 0.70],
    }.get(profile, [0.5, 0.7, 0.85])
