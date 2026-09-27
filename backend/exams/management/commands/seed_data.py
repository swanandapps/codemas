import os
import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from accounts.models import User
from exams.models import Exam, Question, TestCase, ExamEnrollment
from submissions.models import Submission
from results.models import Result
from plagiarism.models import BehaviouralFlag, PlagiarismFlag


INDIAN_STUDENTS = [
    # (first, last, gender)
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

COHORTS = ['Batch-A-2025', 'Batch-B-2025', 'Batch-C-2025', 'Batch-D-2025']

# ── JS Code Solutions (multiple variants per question style) ─────────────────

TWO_SUM_SOLUTIONS = [
    """function twoSum(nums, target) {
    for (let i = 0; i < nums.length; i++) {
        for (let j = i + 1; j < nums.length; j++) {
            if (nums[i] + nums[j] === target) return [i, j];
        }
    }
}
const [n, ...rest] = require('fs').readFileSync('/dev/stdin','utf8').trim().split('\\n');
const nums = rest[0].split(' ').map(Number);
const target = Number(rest[1]);
console.log(twoSum(nums, target).join(' '));""",

    """function twoSum(nums, target) {
    const map = new Map();
    for (let i = 0; i < nums.length; i++) {
        const comp = target - nums[i];
        if (map.has(comp)) return [map.get(comp), i];
        map.set(nums[i], i);
    }
}
const lines = require('fs').readFileSync('/dev/stdin','utf8').trim().split('\\n');
const nums = lines[1].split(' ').map(Number);
const target = Number(lines[2]);
console.log(twoSum(nums, target).join(' '));""",

    """const lines = require('fs').readFileSync('/dev/stdin','utf8').trim().split('\\n');
const nums = lines[1].split(' ').map(Number);
const target = parseInt(lines[2]);
const seen = {};
for (let i = 0; i < nums.length; i++) {
    const need = target - nums[i];
    if (seen[need] !== undefined) {
        console.log(seen[need] + ' ' + i);
        break;
    }
    seen[nums[i]] = i;
}""",
]

FLATTEN_SOLUTIONS = [
    """function flatten(arr) {
    return arr.reduce((acc, val) =>
        Array.isArray(val) ? acc.concat(flatten(val)) : acc.concat(val), []);
}
const input = JSON.parse(require('fs').readFileSync('/dev/stdin','utf8').trim());
console.log(flatten(input).join(' '));""",

    """function flatten(arr, depth = Infinity) {
    if (depth === 0) return arr.slice();
    return arr.reduce((acc, val) => {
        if (Array.isArray(val)) acc.push(...flatten(val, depth - 1));
        else acc.push(val);
        return acc;
    }, []);
}
const input = JSON.parse(require('fs').readFileSync('/dev/stdin','utf8').trim());
console.log(flatten(input).join(' '));""",

    """const input = JSON.parse(require('fs').readFileSync('/dev/stdin','utf8').trim());
console.log(input.flat(Infinity).join(' '));""",
]

DEBOUNCE_SOLUTIONS = [
    """function debounce(fn, delay) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}
// Test harness
let count = 0;
const inc = debounce(() => count++, 100);
inc(); inc(); inc();
setTimeout(() => console.log(count), 200);""",

    """function debounce(func, wait) {
    let timeout = null;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
let calls = 0;
const d = debounce(() => calls++, 50);
d(); d(); d();
setTimeout(() => process.stdout.write(String(calls)), 150);""",
]

CURRY_SOLUTIONS = [
    """function curry(fn) {
    return function curried(...args) {
        if (args.length >= fn.length) return fn.apply(this, args);
        return function(...args2) {
            return curried.apply(this, args.concat(args2));
        };
    };
}
const add = curry((a, b, c) => a + b + c);
const line = require('fs').readFileSync('/dev/stdin','utf8').trim();
const [a,b,c] = line.split(' ').map(Number);
console.log(add(a)(b)(c));""",

    """const curry = fn => {
    const arity = fn.length;
    return function curried(...args) {
        return args.length >= arity
            ? fn(...args)
            : (...moreArgs) => curried(...args, ...moreArgs);
    };
};
const multiply = curry((a, b, c) => a * b * c);
const [a,b,c] = require('fs').readFileSync('/dev/stdin','utf8').trim().split(' ').map(Number);
console.log(multiply(a)(b)(c));""",
]

MEMOIZE_SOLUTIONS = [
    """function memoize(fn) {
    const cache = new Map();
    return function(...args) {
        const key = JSON.stringify(args);
        if (cache.has(key)) return cache.get(key);
        const result = fn.apply(this, args);
        cache.set(key, result);
        return result;
    };
}
const fib = memoize(n => n <= 1 ? n : fib(n-1) + fib(n-2));
const n = parseInt(require('fs').readFileSync('/dev/stdin','utf8').trim());
console.log(fib(n));""",

    """function memoize(fn) {
    const cache = {};
    return (...args) => {
        const k = args.toString();
        if (k in cache) return cache[k];
        return (cache[k] = fn(...args));
    };
}
let callCount = 0;
const expensiveAdd = memoize((a, b) => { callCount++; return a + b; });
const [a,b] = require('fs').readFileSync('/dev/stdin','utf8').trim().split(' ').map(Number);
console.log(expensiveAdd(a,b));""",
]

PROMISE_ALL_SOLUTIONS = [
    """function promiseAll(promises) {
    return new Promise((resolve, reject) => {
        const results = [];
        let remaining = promises.length;
        if (remaining === 0) return resolve([]);
        promises.forEach((p, i) => {
            Promise.resolve(p).then(val => {
                results[i] = val;
                if (--remaining === 0) resolve(results);
            }).catch(reject);
        });
    });
}
promiseAll([Promise.resolve(1), Promise.resolve(2), Promise.resolve(3)])
    .then(r => console.log(r.join(' ')));""",

    """async function promiseAll(promises) {
    const results = new Array(promises.length);
    await Promise.all(promises.map(async (p, i) => {
        results[i] = await p;
    }));
    return results;
}
promiseAll([
    new Promise(r => setTimeout(() => r(10), 10)),
    new Promise(r => setTimeout(() => r(20), 5)),
]).then(r => console.log(r.join(' ')));""",
]

DEEP_CLONE_SOLUTIONS = [
    """function deepClone(obj) {
    if (obj === null || typeof obj !== 'object') return obj;
    if (Array.isArray(obj)) return obj.map(deepClone);
    const clone = {};
    for (const key in obj) {
        if (obj.hasOwnProperty(key)) clone[key] = deepClone(obj[key]);
    }
    return clone;
}
const input = JSON.parse(require('fs').readFileSync('/dev/stdin','utf8').trim());
const cloned = deepClone(input);
cloned.name = 'modified';
console.log(input.name);""",

    """const deepClone = obj => JSON.parse(JSON.stringify(obj));
const input = JSON.parse(require('fs').readFileSync('/dev/stdin','utf8').trim());
const c = deepClone(input);
c.x = 999;
console.log(input.x ?? 'unchanged');""",
]

EVENT_EMITTER_SOLUTIONS = [
    """class EventEmitter {
    constructor() { this.events = {}; }
    on(event, listener) {
        if (!this.events[event]) this.events[event] = [];
        this.events[event].push(listener);
        return this;
    }
    off(event, listener) {
        if (this.events[event])
            this.events[event] = this.events[event].filter(l => l !== listener);
        return this;
    }
    emit(event, ...args) {
        (this.events[event] || []).forEach(l => l(...args));
        return this;
    }
    once(event, listener) {
        const wrapper = (...args) => { listener(...args); this.off(event, wrapper); };
        return this.on(event, wrapper);
    }
}
const em = new EventEmitter();
let count = 0;
em.on('ping', () => count++);
em.emit('ping').emit('ping').emit('ping');
console.log(count);""",
]

LRU_SOLUTIONS = [
    """class LRUCache {
    constructor(capacity) {
        this.capacity = capacity;
        this.map = new Map();
    }
    get(key) {
        if (!this.map.has(key)) return -1;
        const val = this.map.get(key);
        this.map.delete(key);
        this.map.set(key, val);
        return val;
    }
    put(key, value) {
        if (this.map.has(key)) this.map.delete(key);
        else if (this.map.size === this.capacity)
            this.map.delete(this.map.keys().next().value);
        this.map.set(key, value);
    }
}
const cache = new LRUCache(2);
cache.put(1, 10); cache.put(2, 20);
console.log(cache.get(1));
cache.put(3, 30);
console.log(cache.get(2));""",
]

OBSERVER_SOLUTIONS = [
    """class Subject {
    constructor() { this.observers = []; this.state = null; }
    subscribe(observer) { this.observers.push(observer); }
    unsubscribe(observer) { this.observers = this.observers.filter(o => o !== observer); }
    setState(state) {
        this.state = state;
        this.notify();
    }
    notify() { this.observers.forEach(o => o.update(this.state)); }
}
const subject = new Subject();
const log = [];
subject.subscribe({ update: s => log.push(s) });
subject.setState('online');
subject.setState('offline');
console.log(log.join(','));""",
]

THROTTLE_SOLUTIONS = [
    """function throttle(fn, limit) {
    let lastCall = 0;
    return function(...args) {
        const now = Date.now();
        if (now - lastCall >= limit) {
            lastCall = now;
            return fn.apply(this, args);
        }
    };
}
let count = 0;
const throttled = throttle(() => count++, 100);
throttled(); throttled(); throttled();
setTimeout(() => { throttled(); console.log(count); }, 150);""",

    """function throttle(func, interval) {
    let shouldFire = true;
    return function(...args) {
        if (shouldFire) {
            func(...args);
            shouldFire = false;
            setTimeout(() => shouldFire = true, interval);
        }
    };
}
let n = 0;
const t = throttle(() => n++, 200);
t(); t(); t();
setTimeout(() => console.log(n), 100);""",
]

# Map question index to solution pool
SOLUTION_POOLS = [
    TWO_SUM_SOLUTIONS,       # Q0
    FLATTEN_SOLUTIONS,        # Q1
    DEBOUNCE_SOLUTIONS,       # Q2
    CURRY_SOLUTIONS,          # Q3
    MEMOIZE_SOLUTIONS,        # Q4
    PROMISE_ALL_SOLUTIONS,    # Q5
    DEEP_CLONE_SOLUTIONS,     # Q6
    EVENT_EMITTER_SOLUTIONS,  # Q7
    LRU_SOLUTIONS,            # Q8
    OBSERVER_SOLUTIONS,       # Q9
    THROTTLE_SOLUTIONS,       # Q10
    TWO_SUM_SOLUTIONS,        # Q11 (reused with variation)
    FLATTEN_SOLUTIONS,        # Q12
    CURRY_SOLUTIONS,          # Q13
    MEMOIZE_SOLUTIONS,        # Q14
    PROMISE_ALL_SOLUTIONS,    # Q15
    DEEP_CLONE_SOLUTIONS,     # Q16
    EVENT_EMITTER_SOLUTIONS,  # Q17
    LRU_SOLUTIONS,            # Q18
    OBSERVER_SOLUTIONS,       # Q19
]

BAD_CODE_SNIPPETS = [
    "function solve(n) { return n; }\nconsole.log(solve(42));",
    "// TODO: implement\nconsole.log('undefined');",
    "const x = parseInt(require('fs').readFileSync('/dev/stdin','utf8'));\nconsole.log(x + 1);",
    "console.log('hello world');",
    "process.stdin.resume();\nprocess.stdin.on('data', d => { console.log(d.toString().trim()); });",
]

EXAM_DATA = [
    {
        'title': 'Advanced JavaScript: Closures & Scope',
        'description': 'Deep dive into JavaScript closures, lexical scope, and the module pattern. Students will implement real-world utility functions.',
        'duration_minutes': 90,
        'questions': [
            {
                'title': 'Two Sum',
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
                'description': 'Implement your own version of Promise.all from scratch. It should resolve with an array of all resolved values in order, and reject immediately if any promise rejects.\n\nOutput: space-separated resolved values',
                'difficulty': 'hard', 'max_attempts': 2,
                'test_cases': [
                    ('', '1 2 3'),
                    ('', '10 20'),
                ]
            },
            {
                'title': 'Debounce',
                'description': 'Implement a debounce function that delays invoking func until after wait milliseconds have elapsed since the last invocation. Used extensively in search inputs and resize handlers.\n\nOutput: number of times the function actually executed',
                'difficulty': 'medium', 'max_attempts': 3,
                'test_cases': [
                    ('', '1'),
                    ('', '1'),
                ]
            },
            {
                'title': 'Throttle',
                'description': 'Implement a throttle function that ensures the given function is called at most once in the specified time interval, no matter how many times it is invoked.\n\nOutput: call count after interval',
                'difficulty': 'medium', 'max_attempts': 3,
                'test_cases': [
                    ('', '1'),
                    ('', '2'),
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
                'description': 'Implement a deep clone function that creates a completely independent copy of a nested object/array. Mutating the clone must not affect the original.\n\nInput: JSON object with a name property\nOutput: original name after clone is mutated',
                'difficulty': 'medium', 'max_attempts': 3,
                'test_cases': [
                    ('{"name":"Alice","scores":[1,2,3]}', 'Alice'),
                    ('{"name":"Bob","nested":{"x":1}}', 'Bob'),
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
                'description': 'Design a data structure that follows the Least Recently Used (LRU) cache eviction policy. Implement get(key) and put(key, value) — both in O(1) time.\n\nOutput: results of get operations (space-separated)',
                'difficulty': 'hard', 'max_attempts': 2,
                'test_cases': [
                    ('', '10 -1'),
                    ('', '10 -1'),
                ]
            },
            {
                'title': 'Event Emitter',
                'description': 'Build a Node.js-style EventEmitter class with on, off, emit, and once methods. The once method registers a listener that fires only one time then removes itself.\n\nOutput: count of times listener fired',
                'difficulty': 'medium', 'max_attempts': 3,
                'test_cases': [
                    ('', '3'),
                    ('', '3'),
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
                'description': 'Implement the Observer (pub/sub) pattern with a Subject class that maintains a list of observers. When state changes via setState, all subscribers receive the new state via their update method.\n\nOutput: comma-separated list of states received by observer',
                'difficulty': 'medium', 'max_attempts': 3,
                'test_cases': [
                    ('', 'online,offline'),
                    ('', 'active,idle,active'),
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
                'description': 'Classic interview question. Flatten a deeply nested array without using Array.prototype.flat.\n\nInput: JSON array\nOutput: space-separated numbers',
                'difficulty': 'easy', 'max_attempts': 3,
                'test_cases': [
                    ('[1,[2,3],[4,[5,6]]]', '1 2 3 4 5 6'),
                    ('[[[[1]]],2,[[3]]]', '1 2 3'),
                ]
            },
            {
                'title': 'Implement Curry (Interview)',
                'description': 'Implement curry for functions of any arity — must support both curried(a)(b)(c) and curried(a,b)(c) call styles.\n\nInput: three integers\nOutput: result of multiply(a)(b)(c)',
                'difficulty': 'medium', 'max_attempts': 3,
                'test_cases': [
                    ('4 5 2', '40'),
                    ('2 2 2', '8'),
                ]
            },
            {
                'title': 'Promise.all + Timeout',
                'description': 'Implement promiseAllWithTimeout — resolves if all promises complete within the timeout, otherwise rejects with "TIMEOUT".\n\nOutput: resolved values or TIMEOUT',
                'difficulty': 'hard', 'max_attempts': 2,
                'test_cases': [
                    ('', '1 2 3'),
                    ('', 'TIMEOUT'),
                ]
            },
        ]
    },
]


class Command(BaseCommand):
    help = 'Seed 100 Indian JS students with realistic submissions'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Clear all existing data first')

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            BehaviouralFlag.objects.all().delete()
            PlagiarismFlag.objects.all().delete()
            Result.objects.all().delete()
            Submission.objects.all().delete()
            ExamEnrollment.objects.all().delete()
            TestCase.objects.all().delete()
            Question.objects.all().delete()
            Exam.objects.all().delete()
            User.objects.filter(role='student').delete()

        with transaction.atomic():
            trainer = self._ensure_trainer()
            exams = self._create_exams(trainer)
            students = self._create_students()
            self._enroll_students(students, exams)
            all_questions = [q for exam in exams for q in exam.questions.all()]
            self._create_submissions(students, exams, all_questions)
            self._create_plagiarism_pairs(students, all_questions)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone! {len(students)} students, {len(exams)} exams, '
            f'{len(all_questions)} questions seeded.'
        ))

    def _ensure_trainer(self):
        trainer, created = User.objects.get_or_create(
            username='trainer',
            defaults={'email': 'trainer@codemas.dev', 'role': 'trainer'}
        )
        if created:
            trainer.set_password(os.getenv('SEED_TRAINER_PASSWORD', 'trainer123'))
            trainer.save()
            self.stdout.write('Created trainer account (trainer / trainer123)')
        return trainer

    def _create_exams(self, trainer):
        exams = []
        # Anchor in mid-2024 — weekly contests during the Masai cohort
        from django.utils.timezone import make_aware
        from datetime import datetime
        cohort_start = make_aware(datetime(2024, 6, 3))
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
            for j, qdata in enumerate(edata['questions']):
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
            exams.append(exam)
            self.stdout.write(f'  Exam: {exam.title}')
        return exams

    def _create_students(self):
        students = []
        cohort_cycle = COHORTS * 30  # enough to assign 100 students
        for i, (first, last) in enumerate(INDIAN_STUDENTS):
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
        self.stdout.write(f'  Enrolled all students in all exams')

    def _create_submissions(self, students, exams, all_questions):
        rng = random.Random(42)

        # assign student "profiles" — determines behaviour
        profiles = {}
        for s in students:
            profiles[s.id] = rng.choices(
                ['strong', 'average', 'struggling', 'cheater', 'lazy'],
                weights=[25, 35, 20, 10, 10]
            )[0]

        # pre-index questions by exam
        questions_by_exam = {e.id: list(e.questions.all()) for e in exams}

        total_subs = 0
        total_flags = 0

        for student in students:
            profile = profiles[student.id]

            for exam in exams:
                qs = questions_by_exam[exam.id]
                # each student attempts 80-100% of questions
                coverage = rng.uniform(0.75, 1.0)
                attempted = rng.sample(qs, k=max(1, int(len(qs) * coverage)))

                exam_start_offset_s = rng.randint(0, exam.duration_minutes * 30)

                for qi, question in enumerate(attempted):
                    pool_idx = (all_questions.index(question)) % len(SOLUTION_POOLS)
                    solution_pool = SOLUTION_POOLS[pool_idx]

                    max_att = question.max_attempts
                    pass_rates = _profile_pass_rates(profile)

                    attempt_num = 0
                    passed = False

                    for att in range(max_att):
                        if passed:
                            break
                        attempt_num += 1

                        # timing
                        baseline = {'easy': 180, 'medium': 480, 'hard': 900}[question.difficulty]
                        if profile == 'cheater':
                            elapsed = rng.randint(15, int(baseline * 0.25))
                        elif profile == 'strong':
                            elapsed = rng.randint(int(baseline * 0.5), int(baseline * 1.2))
                        elif profile == 'struggling':
                            elapsed = rng.randint(int(baseline * 1.2), int(baseline * 2.5))
                        else:
                            elapsed = rng.randint(int(baseline * 0.6), int(baseline * 1.8))

                        duration_s = exam.duration_minutes * 60
                        time_remaining = max(0, duration_s - exam_start_offset_s - elapsed)

                        # paste behaviour
                        if profile == 'cheater':
                            paste = rng.random() < 0.9
                            paste_chars = len(rng.choice(solution_pool)) if paste else 0
                        elif profile == 'lazy':
                            paste = rng.random() < 0.4
                            paste_chars = rng.randint(50, 200) if paste else 0
                        else:
                            paste = rng.random() < 0.1
                            paste_chars = rng.randint(10, 50) if paste else 0

                        # tab switches
                        if profile == 'cheater':
                            tabs = rng.randint(3, 12)
                        elif profile == 'lazy':
                            tabs = rng.randint(1, 6)
                        else:
                            tabs = rng.randint(0, 2)

                        # code
                        pr = pass_rates[att]
                        attempt_passed = rng.random() < pr
                        if attempt_passed:
                            code = rng.choice(solution_pool)
                            passed = True
                        else:
                            code = rng.choice(BAD_CODE_SNIPPETS + solution_pool[:1])

                        # Submission time is within the actual exam window
                        sub_time = exam.start_time + timedelta(
                            minutes=rng.randint(0, max(1, exam.duration_minutes - 1))
                        )

                        sub = Submission.objects.create(
                            student=student,
                            exam=exam,
                            question=question,
                            code=code,
                            language='javascript',
                            attempt_number=attempt_num,
                            status='passed' if attempt_passed else 'failed',
                            time_remaining_seconds=time_remaining,
                            execution_time_ms=rng.randint(80, 3500),
                            had_paste_event=paste,
                            paste_char_count=paste_chars,
                            time_to_complete_seconds=elapsed,
                            tab_switch_count=tabs,
                            ip_address='127.0.0.1',
                        )
                        # override auto timestamp
                        Submission.objects.filter(pk=sub.pk).update(submitted_at=sub_time)

                        # create result rows for each test case
                        for tc in question.test_cases.all():
                            Result.objects.get_or_create(
                                submission=sub,
                                test_case=tc,
                                defaults={
                                    'passed': attempt_passed,
                                    'actual_output': tc.expected_output if attempt_passed else 'undefined',
                                    'execution_time_ms': rng.randint(50, 800),
                                }
                            )

                        total_subs += 1

                        # create behavioural flag for suspicious submissions
                        if _should_flag(profile, paste, tabs, elapsed, baseline, rng):
                            paste_score = min(paste_chars / max(len(code), 1), 1.0) if paste else 0.0
                            baseline_ratio = elapsed / baseline
                            time_score = max(0.0, 1.0 - baseline_ratio * 2) if baseline_ratio < 0.5 else 0.0
                            tab_score = min(tabs / 5.0, 1.0) if tabs >= 1 else 0.0
                            risk = round(0.40 * paste_score + 0.30 * time_score + 0.15 * tab_score, 4)
                            if risk > 0.20:
                                signals = []
                                if paste_score > 0.5: signals.append(f'Pasted {int(paste_score*100)}% of code')
                                if time_score > 0.5: signals.append(f'Solved {question.difficulty} in {elapsed}s (baseline {baseline}s)')
                                if tab_score > 0.3: signals.append(f'Left exam tab {tabs} times')
                                conf = 'high' if len(signals) >= 3 else 'medium' if len(signals) == 2 else 'low'
                                BehaviouralFlag.objects.get_or_create(
                                    submission=sub,
                                    defaults={
                                        'risk_score': risk,
                                        'confidence': conf,
                                        'paste_score': paste_score,
                                        'time_score': time_score,
                                        'snapshot_score': tab_score,
                                        'submission_score': 0.0,
                                        'signals_triggered': signals,
                                        'review_status': 'pending',
                                    }
                                )
                                total_flags += 1

        self.stdout.write(f'  Created {total_subs} submissions, {total_flags} behavioural flags')

    def _create_plagiarism_pairs(self, students, all_questions):
        rng = random.Random(99)

        # Phase 2 only runs on Phase 1 suspects — students with HIGH behavioural confidence
        high_confidence_student_ids = set(
            BehaviouralFlag.objects.filter(confidence='high')
            .values_list('submission__student_id', flat=True)
            .distinct()
        )
        suspects = [s for s in students if s.id in high_confidence_student_ids]

        if len(suspects) < 2:
            self.stdout.write('  Not enough high-confidence suspects for plagiarism pairs')
            return

        # Pick the question where the most suspects have a submission
        best_q, best_subs = None, {}
        for q in all_questions:
            sub_cache = {}
            for s in suspects:
                sub = Submission.objects.filter(
                    student=s, question=q, status='passed'
                ).first() or Submission.objects.filter(
                    student=s, question=q
                ).first()
                if sub:
                    sub_cache[s.id] = sub
            if len(sub_cache) > len(best_subs):
                best_q, best_subs = q, sub_cache

        if not best_q or len(best_subs) < 2:
            self.stdout.write('  Not enough suspect submissions to form a ring')
            return

        # Overwrite their code with an identical solution to simulate sharing
        shared_code = rng.choice(FLATTEN_SOLUTIONS)
        for sub in best_subs.values():
            Submission.objects.filter(pk=sub.pk).update(code=shared_code)

        sub_list = list(best_subs.values())
        created_pairs = 0
        for i in range(len(sub_list)):
            for j in range(i + 1, len(sub_list)):
                # Always put lower-PK submission as sub1 to prevent bidirectional duplicates
                s1, s2 = sorted([sub_list[i], sub_list[j]], key=lambda s: s.pk)
                PlagiarismFlag.objects.get_or_create(
                    submission_1=s1,
                    submission_2=s2,
                    defaults={
                        'similarity_score': round(rng.uniform(0.92, 0.99), 3),
                        'flagged': True,
                        'detection_method': 'behavioural_filtered_tfidf',
                    }
                )
                created_pairs += 1

        self.stdout.write(f'  Created {created_pairs} plagiarism pairs for question: {best_q.title} ({len(sub_list)} suspects)')


def _profile_pass_rates(profile):
    return {
        'strong':    [0.80, 0.95, 0.99],
        'average':   [0.55, 0.75, 0.88],
        'struggling':[0.25, 0.45, 0.60],
        'cheater':   [0.90, 0.98, 0.99],
        'lazy':      [0.35, 0.55, 0.70],
    }.get(profile, [0.5, 0.7, 0.85])


def _should_flag(profile, paste, tabs, elapsed, baseline, rng):
    if profile == 'cheater': return True
    if paste and tabs >= 3: return True
    if elapsed < baseline * 0.3 and rng.random() < 0.7: return True
    if paste and elapsed < baseline * 0.5: return True
    return False
