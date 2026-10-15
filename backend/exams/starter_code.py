"""Starter code shown in the editor, HackerRank-style: the input is read for the
student, who only writes the function body. Questions without their own starter
get the generic one, which hands every input line to `solve(lines)`.
"""

GENERIC = {
    'javascript': (
        "// Input is read for you: `lines` holds each line of input as a string.\n"
        "const lines = require('fs').readFileSync(0, 'utf8').trim().split('\\n');\n"
        "\n"
        "function solve(lines) {\n"
        "    // Write your code here and return the answer. It is printed for you.\n"
        "}\n"
        "\n"
        "console.log(solve(lines));\n"
    ),
    'python': (
        "# Input is read for you: `lines` holds each line of input as a string.\n"
        "import sys\n"
        "lines = sys.stdin.read().strip().split('\\n')\n"
        "\n"
        "\n"
        "def solve(lines):\n"
        "    # Write your code here and return the answer. It is printed for you.\n"
        "    pass\n"
        "\n"
        "\n"
        "print(solve(lines))\n"
    ),
}


def for_question(question):
    """{'javascript': ..., 'python': ...} for a question, falling back to GENERIC."""
    return {
        'javascript': question.starter_code_javascript or GENERIC['javascript'],
        'python': question.starter_code_python or GENERIC['python'],
    }


# The open demo exam's questions all read: n, then n sorted integers, then the target.
_READ_JS = (
    "// Input is read for you. Don't change this part.\n"
    "const lines = require('fs').readFileSync(0, 'utf8').split('\\n');\n"
    "const n = Number(lines[0]);\n"
    "const arr = n > 0 ? lines[1].trim().split(/\\s+/).map(Number) : [];\n"
    "const target = Number(lines[2]);\n"
    "\n"
)
_READ_PY = (
    "# Input is read for you. Don't change this part.\n"
    "import sys\n"
    "lines = sys.stdin.read().split('\\n')\n"
    "n = int(lines[0])\n"
    "arr = list(map(int, lines[1].split())) if n > 0 else []\n"
    "target = int(lines[2])\n"
    "\n"
    "\n"
)


def _js(fn, task, call):
    return _READ_JS + f"function {fn}(arr, target) {{\n    // Write your code here. {task}\n}}\n\n{call}\n"


def _py(fn, task, call):
    return _READ_PY + f"def {fn}(arr, target):\n    # Write your code here. {task}\n    pass\n\n\n{call}\n"


# Keyed by question title: used by seed_data and by `manage.py apply_starter_code`.
DEMO_STARTERS = {
    'Find Target in Sorted Array': {
        'javascript': _js('findTarget', "Return the index of target, or -1 if it isn't there.",
                          'console.log(findTarget(arr, target));'),
        'python': _py('find_target', "Return the index of target, or -1 if it isn't there.",
                      'print(find_target(arr, target))'),
    },
    'Count Occurrences of Target': {
        'javascript': _js('countOccurrences', 'Return how many times target appears.',
                          'console.log(countOccurrences(arr, target));'),
        'python': _py('count_occurrences', 'Return how many times target appears.',
                      'print(count_occurrences(arr, target))'),
    },
    'Find First and Last Position': {
        'javascript': _js('firstAndLast', "Return [first, last], or [-1, -1] if target isn't there.",
                          "console.log(firstAndLast(arr, target).join(' '));"),
        'python': _py('first_and_last', "Return [first, last], or [-1, -1] if target isn't there.",
                      'print(*first_and_last(arr, target))'),
    },
}
