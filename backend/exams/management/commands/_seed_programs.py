"""
Program generator for the seed: every honest student writes their own program.

Why this exists
---------------
Phase 2 (plagiarism.tasks.run_question_plagiarism_check) normalises JavaScript
by stripping comments and blank lines and replacing EVERY identifier outside a
small keyword list with VAR_0, VAR_1, ... in order of first appearance. It then
compares TF-IDF vectors (default sklearn tokenizer: words of 2+ characters, so
punctuation and operators are invisible) by cosine similarity, flagging pairs at
or above PlagiarismPolicy.similarity_threshold (0.80 by default).

So renaming variables or rewording comments changes nothing the detector sees.
What does change the vector is structure: which keywords appear and how often
(for/while/of/let/const/function/return/new/this/map/filter/reduce/...), how
many distinct identifiers there are, how often each is used, and the ORDER in
which they first appear (that decides which VAR_k each one becomes).

A program here is composed from independent fragments, each with real
structural alternatives:

  core     the algorithm (2-6 genuinely different approaches per problem),
           each with its own realistic bugs
  entry    program layout x input reader: top-level script (definitions first
           or input first), an IIFE, or a main() function above/below the
           definitions; read via readFileSync('/dev/stdin'), readFileSync(0),
           an fs handle, stdin 'data'/'end' events, or readline
  parse    how the input text is split and converted
  printer  console.log / process.stdout.write, inline or via a helper
  names    identifier names (invisible to the detector, but real students
           don't share them either)
  comments a few optional comment lines

Students get distinct (core, entry, parse) structures per question, so no two
honest students hand in the same program. Every generated program is executed
against the question's real test cases before the seed writes anything.
"""
import random
import re


# ── names ─────────────────────────────────────────────────────────────────────

# Every role placeholder (@role@) used by a template draws a name from here.
# Names must be valid identifiers that do not shadow a global the program uses.
NAME_POOLS = {
    # input / plumbing
    'text': ['input', 'raw', 'data', 'stdin', 'content', 'src', 'txt'],
    'fs': ['fs', 'fileSystem', 'nodeFs'],
    'main': ['main', 'solve', 'run', 'start', 'handle'],
    'buf': ['buffer', 'acc', 'received', 'chunks', 'stdinText'],
    'chunk': ['chunk', 'piece', 'part', 'c'],
    'rl': ['rl', 'reader', 'lineReader', 'iface'],
    'collected': ['lines', 'rows', 'inputLines', 'all'],
    'line': ['line', 'ln', 'row', 'l'],
    'emit': ['print', 'out', 'show', 'emit', 'write'],
    'emitArg': ['value', 'v', 'x', 'msg', 'what'],
    # parse
    'n': ['n', 'count', 'num', 'times', 'calls', 'k'],
    'a': ['a', 'x', 'first'], 'b': ['b', 'y', 'second'], 'c': ['c', 'z', 'third'],
    'parts': ['parts', 'nums', 'vals', 'args', 'abc'],
    'tok': ['tok', 't', 'piece', 'word', 'p'],
    's': ['s', 'str', 'x', 'item', 'el'],
    'lines': ['lines', 'rows', 'input_lines', 'ls'],
    'row': ['row', 'arrLine', 'second', 'numsLine'],
    'last': ['last', 'targetLine', 'third', 'tLine'],
    'size': ['size', 'len', 'count', 'n'],
    'tokens': ['tokens', 'all', 'words', 'items'],
    'part': ['part', 'piece', 'chunk', 'tok'],
    'nums': ['nums', 'arr', 'numbers', 'list', 'a'],
    'target': ['target', 'targetSum', 'target_value'],
    'values': ['values', 'vals', 'nums', 'items', 'list'],
    'data': ['data', 'obj', 'parsed', 'payload', 'input_obj', 'arr'],
    'rawStr': ['trimmed', 'cleaned', 'jsonText', 's'],
    'capacity': ['capacity', 'cap', 'limit', 'size'],
    'ops': ['ops', 'commands', 'queries', 'rest', 'operations'],
    'first': ['first', 'head', 'line0', 'top'],
    'second': ['second', 'line1', 'delayLine', 'rest'],
    'l': ['l', 'x', 'row', 's'],
    'states': ['states', 'events', 'words', 'updates', 'list'],
    'w': ['w', 'word', 'tok', 's'],
    'ms': ['ms', 'timeoutMs', 'limit', 'deadline', 'timeout'],
    'delays': ['delays', 'times', 'waits', 'durations'],
    # shared helpers
    'fn': ['fn', 'func', 'f', 'callback', 'cb'],
    'args': ['args', 'params', 'rest', 'a'],
    'more': ['more', 'next', 'rest', 'extra', 'args2'],
    'i': ['i', 'idx', 'index', 'pos'],
    'j': ['j', 'k', 'jdx', 'other'],
    'k': ['k', 'n', 'x', 'm'],
    'x': ['x', 'p', 'u', 'm'],
    'y': ['y', 'q', 'w', 'v'],
    'z': ['z', 'r', 't', 'c'],
    'v': ['v', 'val', 'value', 'item', 'el'],
    'count': ['count', 'calls', 'hits', 'counter', 'executed', 'total'],
    'res': ['res', 'resolve', 'done', 'ok', 'r'],
    'resolve': ['resolve', 'res', 'ok', 'fulfil'],
    'reject': ['reject', 'rej', 'fail', 'nope'],
    'result': ['result', 'res', 'value', 'out', 'answer'],
    'results': ['results', 'out', 'res', 'collected', 'answers'],
    # two sum
    'twoSum': ['twoSum', 'findPair', 'solve2', 'pairIndices', 'findTwo', 'twoSumIdx'],
    'arr': ['arr', 'nums', 'a', 'list', 'numbers'],
    'goal': ['goal', 'target', 'sum', 't', 'want'],
    'seen': ['seen', 'map', 'lookup', 'idxOf', 'positions'],
    'need': ['need', 'comp', 'complement', 'diff', 'want'],
    'pair': ['pair', 'ans', 'res', 'answer', 'found'],
    'index': ['index', 'seen', 'pos', 'where', 'map'],
    'answer': ['answer', 'ans', 'output', 'res'],
    'rest': ['rest', 'need', 'other', 'complement', 'rem'],
    'pos': ['pos', 'where', 'indexOf', 'locations', 'map'],
    'order': ['order', 'idx', 'sortedIdx', 'perm', 'ids'],
    'lo': ['lo', 'left', 'l', 'low', 'start'],
    'hi': ['hi', 'right', 'r', 'high', 'end'],
    'sum': ['sum', 's', 'total', 'cur', 'current'],
    'found': ['found', 'pair', 'result', 'match', 'ans'],
    # memoize
    'memo': ['memoize', 'memoizeFn', 'memoizeOne', 'memoizeAll'],
    'fib': ['fib', 'fibonacci', 'memoFib', 'fastFib', 'fibo'],
    'slowFib': ['rawFib', 'slowFib', 'fibImpl', 'plainFib', 'naiveFib'],
    'cache': ['cache', 'memo', 'store', 'saved', 'known'],
    'key': ['key', 'k', 'id', 'hash', 'sig'],
    'store': ['store', 'cache', 'memo', 'table', 'seen'],
    'table': ['table', 'memo', 'dp', 'saved', 'cache'],
    'wrapped': ['wrapped', 'inner', 'cached', 'memoized', 'fast'],
    'Memo': ['Memoizer', 'MemoCache', 'Memo', 'CacheBox'],
    'inst': ['inst', 'm', 'memo', 'box', 'cacheObj'],
    'cached': ['cached', 'last', 'saved', 'once'],
    # curry
    'curry': ['curry', 'curryFn', 'makeCurry', 'autoCurry', 'curryIt'],
    'curried': ['curried', 'inner', 'next', 'step', 'partial'],
    'mul': ['multiply', 'mul', 'curriedMul', 'times', 'product3'],
    'product': ['product', 'mult', 'multiply3', 'prod', 'mul3'],
    'arity': ['arity', 'needed', 'n', 'len', 'total'],
    'collect': ['collect', 'gather', 'build', 'acc', 'take'],
    'sofar': ['sofar', 'prev', 'got', 'acc', 'have'],
    'next': ['next', 'more', 'newArgs', 'incoming', 'extra'],
    'all': ['all', 'combined', 'merged', 'full', 'together'],
    'need2': ['need', 'expected', 'want', 'arity', 'required'],
    'step': ['step', 'go', 'take', 'build', 'next'],
    'got': ['got', 'have', 'collected', 'sofar', 'saved'],
    'merged': ['merged', 'combined', 'all', 'joined', 'list'],
    # promise all
    'pall': ['promiseAll', 'myPromiseAll', 'promiseAllCustom', 'promiseAllImpl'],
    'list': ['promises', 'list', 'tasks', 'items', 'input'],
    'p': ['p', 'promise', 'task', 'item', 'pr'],
    'val': ['val', 'value', 'v', 'res', 'out'],
    'left': ['left', 'remaining', 'pending', 'todo', 'count'],
    'acc': ['acc', 'chain', 'prev', 'sofar', 'memo'],
    'done': ['done', 'finished', 'settled', 'completed', 'count'],
    'idx': ['idx', 'i', 'at', 'position', 'n'],
    'delayed': ['delayed', 'promises', 'tasks', 'jobs', 'wrapped'],
    'delay': ['delay', 'later', 'after', 'wait', 'resolveLater'],
    'out': ['out', 'result', 'values', 'res', 'arr'],
    # debounce / throttle
    'debounce': ['debounce', 'debounceFn', 'debounceCall'],
    'throttle': ['throttle', 'throttleFn', 'throttleCall'],
    'wait': ['wait', 'delay', 'ms', 'interval', 'timeout'],
    'timer': ['timer', 'timeoutId', 'handle', 't', 'pending'],
    'executed': ['executedFunction', 'debounced', 'wrapper', 'inner'],
    'later': ['later', 'run', 'fire', 'callLater', 'go'],
    'timeout': ['timeout', 'timer', 'tid', 'id'],
    'handle': ['handle', 'timer', 'id', 'tid'],
    'last': ['last', 'lastCall', 'lastTime', 'stamp'],
    'pending': ['pending', 'scheduled', 'waiting', 'armed'],
    'latest': ['latest', 'lastArgs', 'saved', 'params'],
    'check': ['check', 'tick', 'poll', 'maybeFire'],
    'elapsed': ['elapsed', 'since', 'gap', 'passed'],
    'Debouncer': ['Debouncer', 'DebounceBox', 'Deb'],
    'd': ['d', 'deb', 'box', 'inst'],
    'inc': ['inc', 'bump', 'tick', 'hit', 'call'],
    'b': ['b', 'burst', 'round', 'step'],
    'fire': ['fire', 'throttled', 'tick', 'call', 'go'],
    'limit': ['limit', 'interval', 'wait', 'gapMs', 'every'],
    'lastCall': ['lastCall', 'lastRun', 'prev', 'last'],
    'now': ['now', 'current', 'ts', 'time'],
    'ready': ['ready', 'canFire', 'open', 'allowed'],
    'nextAt': ['nextAt', 'nextAllowed', 'until', 'blockedUntil'],
    'Throttler': ['Throttler', 'Throttle', 'Gate'],
    'gate': ['gate', 'thr', 'inst', 'box'],
    'tries': ['tries', 'rounds', 'r', 'j'],
    # flatten
    'flatten': ['flatten', 'flattenDeep', 'flattenAll', 'flattenArr', 'flattenList'],
    'acc2': ['acc', 'res', 'out', 'flat', 'collected'],
    'item': ['item', 'el', 'val', 'x', 'node'],
    'depth': ['depth', 'level', 'd', 'max'],
    'stack': ['stack', 'todo', 'work', 'pending'],
    'nxt': ['next', 'top', 'cur', 'item'],
    'walk': ['walk', 'visit', 'go', 'helper', 'dfs'],
    'sink': ['out', 'result', 'acc', 'bucket', 'res'],
    'queue': ['queue', 'q', 'todo', 'work'],
    # deep clone
    'deepClone': ['deepClone', 'deepCloneObj', 'deepCloneValue', 'deepCloneAny'],
    'obj': ['obj', 'o', 'value', 'src', 'source'],
    'clone': ['clone', 'copy', 'out', 'result', 'dst'],
    'copy': ['copy', 'cloned', 'c', 'dup', 'twin'],
    'entry': ['pair', 'entry', 'kv', 'e'],
    'prop': ['prop', 'key', 'k', 'field', 'name'],
    # event emitter
    'EE': ['EventEmitter', 'MyEventEmitter', 'EventEmitterLite', 'SimpleEventEmitter'],
    'em': ['em', 'emitter', 'bus', 'events', 'ee'],
    'onHits': ['onCount', 'a', 'onHits', 'regular', 'onCalls'],
    'onceHits': ['onceCount', 'b', 'onceHits', 'single', 'onceCalls'],
    'event': ['event', 'name', 'evt', 'type', 'eventName'],
    'listener': ['listener', 'fn', 'handler', 'cb', 'callback'],
    'wrapper': ['wrapper', 'onceWrapper', 'wrapped', 'w', 'one'],
    'entryL': ['l', 'entry', 'rec', 'item', 'h'],
    'fired': ['fired', 'called', 'used', 'ran', 'done'],
    'bucket': ['bucket', 'set', 'list', 'handlers', 'group'],
    'snapshot': ['snapshot', 'copy', 'current', 'toCall', 'list'],
    # lru
    'LRU': ['LRUCache', 'MyLRUCache', 'LRUCacheImpl', 'SimpleLRUCache'],
    'Node': ['Node', 'ListNode', 'Entry', 'DNode'],
    'lru': ['cache', 'lru', 'c', 'store'],
    'op': ['op', 'cmd', 'action', 'kind'],
    'value': ['value', 'val', 'v', 'data'],
    'parts2': ['parts', 'p', 'bits', 'fields', 'w'],
    'node': ['node', 'n', 'entry', 'item'],
    'lruNode': ['lru', 'oldest', 'victim', 'tailNode'],
    'keys': ['keys', 'order', 'recent', 'queue', 'usage'],
    'tick': ['tick', 'clock', 'time', 'counter', 'stamp'],
    'oldest': ['oldest', 'victim', 'minKey', 'evict'],
    'k2': ['k', 'key2', 'kk', 'other'],
    # observer
    'Subject': ['Subject', 'Observable', 'Store', 'Publisher'],
    'subject': ['subject', 'store', 'obs', 'pub', 'source'],
    'observer': ['observer', 'o', 'sub', 'listener', 'watcher'],
    'state': ['state', 'value', 's', 'next', 'newState'],
    'received': ['received', 'log', 'seen', 'history', 'got'],
    'subscribe': ['subscribe', 'addSubscriber', 'onSubscribe'],
    'createSubject': ['createSubject', 'makeSubject', 'subjectOf', 'newSubject'],
    'observers': ['observers', 'subs', 'listeners', 'watchers', 'fns'],
    'nextId': ['nextId', 'counter', 'uid', 'seq'],
    'id': ['id', 'key', 'token', 'handle'],
    # promise all + timeout
    'pat': ['promiseAllWithTimeout'],
    'vals': ['vals', 'values', 'res', 'out', 'results'],
    'err': ['err', 'e', 'error', 'reason'],
    'timedOut': ['timedOut', 'expired', 'late', 'tooLate'],
    'd2': ['d', 'delay', 'ms2', 'wait'],
    'bound': ['bound', 'have', 'given', 'collected'],
    'curryM': ['curry', 'curried', 'autoCurry'],
    'self': ['self', 'original', 'target_fn', 'that'],
    'gather': ['gather', 'collector', 'take', 'grab'],
    'incoming': ['incoming', 'newArgs', 'passed', 'more'],
    'next2': ['next', 'proceed', 'nextStep', 'cont'],
    'step1': ['step1', 'withA', 'partA', 'f1'],
    'step2': ['step2', 'withB', 'partB', 'f2'],
    'deadline': ['deadline', 'timeoutP', 'limiter', 'expiry'],
    'collectAll': ['collectAll', 'allDone', 'everything', 'gathered'],
    'Deadline': ['Deadline', 'Timer', 'TimeoutGuard', 'Watchdog'],
    'dl': ['dl', 'guard', 'watch', 'timerObj'],
}

# globals / API names the templates use literally
RESERVED = {
    'require', 'process', 'console', 'Map', 'Set', 'Promise', 'JSON', 'Number',
    'String', 'Array', 'Object', 'Date', 'setTimeout', 'clearTimeout',
    'Infinity', 'undefined', 'parseInt', 'structuredClone', 'arguments', 'this',
    'Boolean', 'Math', 'Error', 'null', 'true', 'false', 'new', 'class', 'function',
    'return', 'const', 'let', 'var', 'for', 'of', 'in', 'if', 'else', 'while',
    'async', 'await', 'yield', 'do', 'switch', 'case', 'break', 'continue',
    'delete', 'typeof', 'instanceof', 'try', 'catch', 'finally', 'throw',
    'on', 'once', 'off', 'emit', 'get', 'put', 'call', 'apply', 'bind', 'then',
    'next', 'prev', 'key', 'val', 'value', 'inner', 'name', 'message',
}
# property / method names used as `obj.<name>` in templates are fine to reuse
# as local identifiers in JS, but keeping them out avoids confusing programs.


class Names(dict):
    """role -> identifier, drawn lazily from NAME_POOLS with a private RNG."""

    def __init__(self, rng):
        super().__init__()
        self.rng = rng
        self.used = set(RESERVED)

    def __missing__(self, role):
        pool = [n for n in NAME_POOLS.get(role, [role]) if n not in self.used]
        if pool:
            name = self.rng.choice(pool)
        else:
            base = NAME_POOLS.get(role, [role])[0]
            i = 2
            while f'{base}{i}' in self.used:
                i += 1
            name = f'{base}{i}'
        self.used.add(name)
        self[role] = name
        return name


def _fill(template, names):
    return re.sub(r'@(\w+)@', lambda m: names[m.group(1)], template)


def _indent(block, n=4):
    pad = ' ' * n
    return '\n'.join(pad + line if line.strip() else line for line in block.split('\n'))


# ── printers ──────────────────────────────────────────────────────────────────
#
# Templates print with the pseudo-call __out__(EXPR); the printer decides what
# that becomes. Helper printers add a small top-level function.

PRINTERS = {
    'log': (None, lambda e: f'console.log({e})'),
    'write': (None, lambda e: f"process.stdout.write(String({e}) + '\\n')"),
    'helper_log': (
        'function @emit@(@emitArg@) {\n    console.log(@emitArg@);\n}',
        lambda e: f'@emit@({e})',
    ),
    'helper_write': (
        "const @emit@ = (@emitArg@) => process.stdout.write(`${@emitArg@}\\n`);",
        lambda e: f'@emit@({e})',
    ),
}


def _render_out(code, printer):
    render = PRINTERS[printer][1]
    out, i = [], 0
    while True:
        k = code.find('__out__(', i)
        if k < 0:
            out.append(code[i:])
            return ''.join(out)
        out.append(code[i:k])
        j = p = k + len('__out__(')
        depth = 1
        while depth:
            if code[p] == '(':
                depth += 1
            elif code[p] == ')':
                depth -= 1
            p += 1
        out.append(render(code[j:p - 1]))
        i = p


# ── input readers & layouts ───────────────────────────────────────────────────

SYNC_READERS = {
    'dev_stdin': ('', "require('fs').readFileSync('/dev/stdin', 'utf8')"),
    'fd0': ('', "require('fs').readFileSync(0, 'utf8')"),
    'fd0_buffer': ('', 'require(\'fs\').readFileSync(0).toString()'),
    'fs_handle': ("const @fs@ = require('fs');", "@fs@.readFileSync('/dev/stdin').toString()"),
}
ASYNC_READERS = {
    'stdin_events': r"""let @buf@ = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (@chunk@) => {
    @buf@ += @chunk@;
});
process.stdin.on('end', () => @main@(@buf@));""",
    'readline': r"""const @rl@ = require('readline').createInterface({ input: process.stdin });
const @collected@ = [];
@rl@.on('line', (@line@) => @collected@.push(@line@));
@rl@.on('close', () => @main@(@collected@.join('\n')));""",
}

ENTRIES = (
    [('top_defs_first', r) for r in SYNC_READERS]
    + [('top_input_first', r) for r in SYNC_READERS]
    + [('iife', r) for r in SYNC_READERS]
    + [('main_top', r) for r in list(SYNC_READERS) + list(ASYNC_READERS)]
    + [('main_bottom', r) for r in list(SYNC_READERS) + list(ASYNC_READERS)]
)


def _assemble(layout, reader, defs, parse, body, helper):
    blocks = []

    def add(*bs):
        blocks.extend(b for b in bs if b)

    main_block = parse + '\n' + body
    if reader in SYNC_READERS:
        prelude, expr = SYNC_READERS[reader]
    else:
        prelude, expr = '', None

    if layout == 'top_defs_first':
        add(helper, defs, prelude, f'const @text@ = {expr};', main_block)
    elif layout == 'top_input_first':
        add(prelude, f'const @text@ = {expr};', parse, helper, defs, body)
    elif layout == 'iife':
        add(helper, defs, prelude,
            '(() => {\n' + _indent(f'const @text@ = {expr};\n' + main_block) + '\n})();')
    else:
        main_fn = 'function @main@(@text@) {\n' + _indent(main_block) + '\n}'
        call = ASYNC_READERS[reader] if expr is None else '\n'.join(
            b for b in (prelude, f'@main@({expr});') if b)
        if layout == 'main_top':
            add(helper, defs, main_fn, call)
        else:  # main_bottom
            add(main_fn, helper, defs, call)
    return blocks


# ── parsers (one family per input shape) ──────────────────────────────────────

PARSERS = {
    'int': [
        'const @n@ = parseInt(@text@.trim(), 10);',
        'const @n@ = Number(@text@.trim());',
        'const @n@ = +@text@;',
    ],
    'triple': [
        "const [@a@, @b@, @c@] = @text@.trim().split(' ').map(Number);",
        "const @parts@ = @text@.trim().split(/\\s+/).map((@s@) => parseInt(@s@, 10));\n"
        "const @a@ = @parts@[0];\nconst @b@ = @parts@[1];\nconst @c@ = @parts@[2];",
        "const @parts@ = [];\nfor (const @tok@ of @text@.split(' ')) @parts@.push(Number(@tok@));\n"
        "const [@a@, @b@, @c@] = @parts@;",
    ],
    'two_sum': [
        "const @lines@ = @text@.trim().split('\\n');\n"
        "const @nums@ = @lines@[1].split(' ').map(Number);\n"
        "const @target@ = Number(@lines@[2]);",
        "const [, @row@, @last@] = @text@.trim().split('\\n');\n"
        "const @nums@ = @row@.trim().split(/\\s+/).map(Number);\n"
        "const @target@ = parseInt(@last@, 10);",
        "const @tokens@ = @text@.split(/\\s+/).filter(Boolean).map(Number);\n"
        "const @size@ = @tokens@[0];\n"
        "const @nums@ = @tokens@.slice(1, 1 + @size@);\n"
        "const @target@ = @tokens@[1 + @size@];",
        "const @lines@ = @text@.split('\\n');\n"
        "const @nums@ = [];\n"
        "for (const @part@ of @lines@[1].trim().split(' ')) {\n"
        "    @nums@.push(parseInt(@part@, 10));\n"
        "}\n"
        "const @target@ = +@lines@[2];",
    ],
    'num_list': [
        'const @values@ = @text@.trim().split(/\\s+/).map(Number);',
        "const @values@ = @text@.trim().split(' ').map((@s@) => parseInt(@s@, 10));",
        'const @values@ = [];\nfor (const @tok@ of @text@.trim().split(/\\s+/)) @values@.push(+@tok@);',
    ],
    'json': [
        'const @data@ = JSON.parse(@text@);',
        'const @rawStr@ = @text@.trim();\nconst @data@ = JSON.parse(@rawStr@);',
    ],
    'lru': [
        "const @lines@ = @text@.trim().split('\\n');\n"
        'const @capacity@ = parseInt(@lines@[0], 10);\n'
        'const @ops@ = @lines@.slice(1);',
        "const [@first@, ...@ops@] = @text@.trim().split('\\n');\n"
        'const @capacity@ = Number(@first@);',
        "const @lines@ = @text@.split(/\\r?\\n/).filter((@l@) => @l@.trim() !== '');\n"
        'const @capacity@ = +@lines@.shift();\n'
        'const @ops@ = @lines@;',
    ],
    'words': [
        'const @states@ = @text@.trim().split(/\\s+/);',
        "const @states@ = @text@.split(' ').map((@s@) => @s@.trim()).filter((@s@) => @s@.length > 0);",
        "const @states@ = [];\nfor (const @w@ of @text@.trim().split(' ')) {\n    if (@w@) @states@.push(@w@);\n}",
    ],
    'timeout': [
        "const [@first@, @second@] = @text@.trim().split('\\n');\n"
        'const @ms@ = parseInt(@first@, 10);\n'
        'const @delays@ = @second@.trim().split(/\\s+/).map(Number);',
        "const @lines@ = @text@.trim().split('\\n');\n"
        'const @ms@ = Number(@lines@[0]);\n'
        "const @delays@ = @lines@[1].split(' ').map((@s@) => +@s@);",
        'const @nums@ = @text@.split(/\\s+/).filter(Boolean).map(Number);\n'
        'const @ms@ = @nums@[0];\n'
        'const @delays@ = @nums@.slice(1);',
    ],
}


# ── cores ─────────────────────────────────────────────────────────────────────
#
# Each core is f(bug, rng) -> (defs, body). bug is None for a correct program
# or one of the core's listed bug ids. rng picks small sub-variants (loop style,
# helper or not) that every student makes differently anyway.

def _pick(rng, *options):
    return rng.choice(options)


# Two Sum ─ input: nums, target ─ output "i j"

def ts_brute(bug, rng):
    j0 = '@i@' if bug == 'self_pair' else '@i@ + 1'
    defs = f"""function @twoSum@(@arr@, @goal@) {{
    for (let @i@ = 0; @i@ < @arr@.length; @i@++) {{
        for (let @j@ = {j0}; @j@ < @arr@.length; @j@++) {{
            if (@arr@[@i@] + @arr@[@j@] === @goal@) return [@i@, @j@];
        }}
    }}
    return [-1, -1];
}}"""
    if bug == 'values':
        body = "const @pair@ = @twoSum@(@nums@, @target@);\n__out__(@nums@[@pair@[0]] + ' ' + @nums@[@pair@[1]]);"
    else:
        body = _pick(rng,
                     "const @pair@ = @twoSum@(@nums@, @target@);\n__out__(@pair@.join(' '));",
                     "const [@i@, @j@] = @twoSum@(@nums@, @target@);\n__out__(`${@i@} ${@j@}`);")
    return defs, body


def ts_map(bug, rng):
    check = '        if (@seen@.has(@need@)) return [@seen@.get(@need@), @i@];'
    if bug == 'reversed':
        check = '        if (@seen@.has(@need@)) return [@i@, @seen@.get(@need@)];'
    store = '        @seen@.set(@arr@[@i@], @i@);'
    inner = f'{store}\n{check}' if bug == 'insert_first' else f'{check}\n{store}'
    defs = f"""function @twoSum@(@arr@, @goal@) {{
    const @seen@ = new Map();
    for (let @i@ = 0; @i@ < @arr@.length; @i@++) {{
        const @need@ = @goal@ - @arr@[@i@];
{inner}
    }}
    return null;
}}"""
    body = "__out__(@twoSum@(@nums@, @target@).join(' '));"
    return defs, body


def ts_object(bug, rng):
    ans = "(@index@[@rest@] + 1) + ' ' + (@i@ + 1)" if bug == 'one_based' else "@index@[@rest@] + ' ' + @i@"
    body = f"""const @index@ = {{}};
let @answer@ = '';
for (let @i@ = 0; @i@ < @nums@.length; @i@++) {{
    const @rest@ = @target@ - @nums@[@i@];
    if (@index@[@rest@] !== undefined) {{
        @answer@ = {ans};
        break;
    }}
    @index@[@nums@[@i@]] = @i@;
}}
__out__(@answer@);"""
    return '', body


def ts_two_pass(bug, rng):
    cond = '@j@ !== undefined' if bug == 'no_self_check' else '@j@ !== undefined && @j@ !== @i@'
    build = _pick(rng,
                  '    @arr@.forEach((@v@, @k@) => @pos@.set(@v@, @k@));',
                  '    for (let @k@ = 0; @k@ < @arr@.length; @k@++) @pos@.set(@arr@[@k@], @k@);')
    defs = f"""function @twoSum@(@arr@, @goal@) {{
    const @pos@ = new Map();
{build}
    for (let @i@ = 0; @i@ < @arr@.length; @i@++) {{
        const @j@ = @pos@.get(@goal@ - @arr@[@i@]);
        if ({cond}) return [@i@, @j@];
    }}
    return [];
}}"""
    body = "const @pair@ = @twoSum@(@nums@, @target@);\n__out__(@pair@[0] + ' ' + @pair@[1]);"
    return defs, body


def ts_pointers(bug, rng):
    ret = '[@order@[@lo@], @order@[@hi@]]'
    if bug != 'unsorted_output':
        ret += '.sort((@x@, @y@) => @x@ - @y@)'
    defs = f"""function @twoSum@(@arr@, @goal@) {{
    const @order@ = @arr@.map((_, @k@) => @k@).sort((@x@, @y@) => @arr@[@x@] - @arr@[@y@]);
    let @lo@ = 0;
    let @hi@ = @order@.length - 1;
    while (@lo@ < @hi@) {{
        const @sum@ = @arr@[@order@[@lo@]] + @arr@[@order@[@hi@]];
        if (@sum@ === @goal@) return {ret};
        if (@sum@ < @goal@) @lo@++;
        else @hi@--;
    }}
    return [];
}}"""
    body = "__out__(@twoSum@(@nums@, @target@).join(' '));"
    return defs, body


def ts_while(bug, rng):
    j0 = '0' if bug == 'j_from_zero' else '@i@ + 1'
    body = f"""let @i@ = 0;
let @found@ = null;
while (@i@ < @nums@.length && !@found@) {{
    let @j@ = {j0};
    while (@j@ < @nums@.length) {{
        if (@nums@[@i@] + @nums@[@j@] === @target@) {{
            @found@ = [@i@, @j@];
            break;
        }}
        @j@++;
    }}
    @i@++;
}}
__out__(@found@[0] + ' ' + @found@[1]);"""
    return '', body


# Memoize ─ input: n ─ output fib(n)

def _fib_lambda(bug):
    base = '1' if bug == 'base_one' else '@k@'
    return f'(@k@) => (@k@ < 2 ? {base} : @fib@(@k@ - 1) + @fib@(@k@ - 2))'


def mf_map_json(bug, rng):
    defs = f"""function @memo@(@fn@) {{
    const @cache@ = new Map();
    return function (...@args@) {{
        const @key@ = JSON.stringify(@args@);
        if (@cache@.has(@key@)) return @cache@.get(@key@);
        const @result@ = @fn@.apply(this, @args@);
        @cache@.set(@key@, @result@);
        return @result@;
    }};
}}
const @fib@ = @memo@({_fib_lambda(bug)});"""
    return defs, '__out__(@fib@(@n@));'


def mf_object(bug, rng):
    if bug == 'ignores_args':
        inner = """    let @cached@;
    return (...@args@) => {
        if (@cached@ !== undefined) return @cached@;
        @cached@ = @fn@(...@args@);
        return @cached@;
    };"""
    else:
        inner = """    const @cache@ = {};
    return (...@args@) => {
        const @key@ = @args@.join(',');
        if (!(@key@ in @cache@)) @cache@[@key@] = @fn@(...@args@);
        return @cache@[@key@];
    };"""
    defs = f"""const @memo@ = (@fn@) => {{
{inner}
}};
const @fib@ = @memo@({_fib_lambda(None)});"""
    return defs, '__out__(@fib@(@n@));'


def mf_single(bug, rng):
    second = '@fib@(@k@ - 3)' if bug == 'wrong_recurrence' else '@fib@(@k@ - 2)'
    defs = f"""function @memo@(@fn@) {{
    const @store@ = new Map();
    return (@x@) => {{
        if (!@store@.has(@x@)) @store@.set(@x@, @fn@(@x@));
        return @store@.get(@x@);
    }};
}}
function @slowFib@(@k@) {{
    if (@k@ < 2) return @k@;
    return @fib@(@k@ - 1) + {second};
}}
const @fib@ = @memo@(@slowFib@);"""
    return defs, '__out__(@fib@(@n@));'


def mf_array(bug, rng):
    zero = '1' if bug == 'base_swap' else '0'
    defs = f"""function @memo@(@fn@) {{
    const @table@ = [];
    return function @wrapped@(@x@) {{
        if (@table@[@x@] === undefined) {{
            @table@[@x@] = @fn@(@x@);
        }}
        return @table@[@x@];
    }};
}}
const @fib@ = @memo@(function (@k@) {{
    if (@k@ === 0) return {zero};
    if (@k@ === 1) return 1;
    return @fib@(@k@ - 1) + @fib@(@k@ - 2);
}});"""
    return defs, '__out__(@fib@(@n@));'


def mf_class(bug, rng):
    defs = f"""class @Memo@ {{
    constructor(@fn@) {{
        this.@fn@ = @fn@;
        this.@cache@ = new Map();
    }}
    call(@x@) {{
        if (!this.@cache@.has(@x@)) this.@cache@.set(@x@, this.@fn@(@x@));
        return this.@cache@.get(@x@);
    }}
}}
function @memo@(@fn@) {{
    const @inst@ = new @Memo@(@fn@);
    return (@x@) => @inst@.call(@x@);
}}
const @fib@ = @memo@({_fib_lambda(bug)});"""
    body = '__out__(@fib@(@n@ - 1));' if bug == 'off_by_one' else '__out__(@fib@(@n@));'
    return defs, body


# Curry ─ input: a b c ─ output multiply(a)(b)(c)

def _multiply(bug, rng):
    op = '+' if bug == 'add' else '*'
    return _pick(rng,
                 f'const @mul@ = @curry@((@x@, @y@, @z@) => @x@ {op} @y@ {op} @z@);',
                 f'function @product@(@x@, @y@, @z@) {{\n    return @x@ {op} @y@ {op} @z@;\n}}\n'
                 f'const @mul@ = @curry@(@product@);')


def _curry_body(rng):
    return _pick(rng,
                 '__out__(@mul@(@a@)(@b@)(@c@));',
                 'const @result@ = @mul@(@a@)(@b@)(@c@);\n__out__(@result@);',
                 'const @step1@ = @mul@(@a@);\nconst @step2@ = @step1@(@b@);\n__out__(@step2@(@c@));',
                 'const @result@ = @mul@(@a@, @b@)(@c@);\nif (@result@ !== @mul@(@a@)(@b@, @c@)) {\n'
                 '    console.error(\'call styles disagree\');\n}\n__out__(@result@);')


def cu_apply(bug, rng):
    defs = """function @curry@(@fn@) {
    return function @curried@(...@args@) {
        if (@args@.length >= @fn@.length) return @fn@.apply(this, @args@);
        return function (...@more@) {
            return @curried@.apply(this, @args@.concat(@more@));
        };
    };
}
""" + _multiply(bug, rng)
    return defs, _curry_body(rng)


def cu_arrow(bug, rng):
    cmp = '>' if bug == 'strict_gt' else '>='
    defs = f"""const @curry@ = (@fn@) => {{
    const @arity@ = @fn@.length;
    const @curried@ = (...@args@) =>
        @args@.length {cmp} @arity@ ? @fn@(...@args@) : (...@more@) => @curried@(...@args@, ...@more@);
    return @curried@;
}};
""" + _multiply(None, rng)
    return defs, _curry_body(rng)


def cu_bind(bug, rng):
    need = '2' if bug == 'two_args' else '@fn@.length'
    defs = f"""function @curry@(@fn@) {{
    return function @curried@(...@args@) {{
        if (@args@.length < {need}) {{
            return @curried@.bind(null, ...@args@);
        }}
        return @fn@(...@args@);
    }};
}}
""" + _multiply(None, rng)
    return defs, _curry_body(rng)


def cu_collect(bug, rng):
    merge = '[...@next@]' if bug == 'forgets_args' else '[...@sofar@, ...@next@]'
    defs = f"""function @curry@(@fn@) {{
    const @collect@ = (@sofar@) => (...@next@) => {{
        const @all@ = {merge};
        return @all@.length >= @fn@.length ? @fn@(...@all@) : @collect@(@all@);
    }};
    return @collect@([]);
}}
""" + _multiply(None, rng)
    return defs, _curry_body(rng)


def cu_arguments(bug, rng):
    cmp = '>' if bug == 'strict_gt' else '>='
    defs = f"""function @curry@(@fn@) {{
    const @need2@ = @fn@.length;
    function @step@(@got@) {{
        return function () {{
            const @merged@ = @got@.slice();
            for (let @i@ = 0; @i@ < arguments.length; @i@++) @merged@.push(arguments[@i@]);
            if (@merged@.length {cmp} @need2@) return @fn@.apply(null, @merged@);
            return @step@(@merged@);
        }};
    }}
    return @step@([]);
}}
""" + _multiply(None, rng)
    return defs, _curry_body(rng)


def cu_recursive(bug, rng):
    cmp = '>' if bug == 'strict_gt' else '>='
    defs = f"""function @curry@(@fn@, ...@bound@) {{
    if (@bound@.length {cmp} @fn@.length) return @fn@(...@bound@);
    return (...@next@) => @curry@(@fn@, ...@bound@, ...@next@);
}}
""" + _multiply(None, rng)
    return defs, _curry_body(rng)


def cu_prototype(bug, rng):
    merge = '@more@' if bug == 'forgets_args' else '@got@.concat(@more@)'
    defs = f"""Function.prototype.@curryM@ = function () {{
    const @self@ = this;
    const @need2@ = this.length;
    const @gather@ = function (@got@) {{
        return function (...@more@) {{
            const @merged@ = {merge};
            if (@merged@.length >= @need2@) return @self@.apply(null, @merged@);
            return @gather@(@merged@);
        }};
    }};
    return @gather@([]);
}};
function @curry@(@fn@) {{
    return @fn@.@curryM@();
}}
""" + _multiply(None, rng)
    return defs, _curry_body(rng)


def cu_while(bug, rng):
    cmp = '<=' if bug == 'off_by_one' else '<'
    defs = f"""function @curry@(@fn@) {{
    const @arity@ = @fn@.length;
    function @next2@(@sofar@) {{
        return function (...@incoming@) {{
            const @all@ = @sofar@.slice();
            let @i@ = 0;
            while (@i@ < @incoming@.length) {{
                @all@.push(@incoming@[@i@]);
                @i@ += 1;
            }}
            if (@all@.length {cmp} @arity@) {{
                return @next2@(@all@);
            }}
            return @fn@(...@all@);
        }};
    }}
    return @next2@([]);
}}
""" + _multiply(None, rng)
    return defs, _curry_body(rng)


# Promise.all ─ input: values (later values resolve sooner) ─ output in order

def _pa_body(rng):
    make = _pick(
        rng,
        'const @delayed@ = @values@.map((@v@, @i@) => new Promise((@res@) => setTimeout(() => @res@(@v@), (@values@.length - @i@) * 10)));',
        'function @delay@(@v@, @ms@) {\n    return new Promise((@res@) => setTimeout(() => @res@(@v@), @ms@));\n}\n'
        'const @delayed@ = [];\nfor (let @i@ = 0; @i@ < @values@.length; @i@++) {\n'
        '    @delayed@.push(@delay@(@values@[@i@], (@values@.length - @i@) * 10));\n}',
    )
    return make + '\n' + _pick(rng,
                               "@pall@(@delayed@).then((@out@) => __out__(@out@.join(' ')));",
                               "@pall@(@delayed@).then((@out@) => {\n    __out__(@out@.join(' '));\n});")


def pa_counter(bug, rng):
    if bug == 'push_order':
        init, store = 'const @results@ = [];', '@results@.push(@val@);'
    else:
        init, store = 'const @results@ = new Array(@list@.length);', '@results@[@i@] = @val@;'
    defs = f"""function @pall@(@list@) {{
    return new Promise((@resolve@, @reject@) => {{
        {init}
        let @left@ = @list@.length;
        if (@left@ === 0) return @resolve@(@results@);
        @list@.forEach((@p@, @i@) => {{
            Promise.resolve(@p@).then((@val@) => {{
                {store}
                if (--@left@ === 0) @resolve@(@results@);
            }}, @reject@);
        }});
    }});
}}"""
    return defs, _pa_body(rng)


def pa_await(bug, rng):
    end = '@list@.length - 1' if bug == 'skips_last' else '@list@.length'
    loop = _pick(rng,
                 f'    for (let @i@ = 0; @i@ < {end}; @i@++) {{\n        @results@[@i@] = await @list@[@i@];\n    }}',
                 f'    let @i@ = 0;\n    while (@i@ < {end}) {{\n        @results@.push(await @list@[@i@]);\n        @i@++;\n    }}')
    defs = f"""async function @pall@(@list@) {{
    const @results@ = [];
{loop}
    return @results@;
}}"""
    return defs, _pa_body(rng)


def pa_reduce(bug, rng):
    merged = '[@v@, ...@acc2@]' if bug == 'reversed' else '[...@acc2@, @v@]'
    defs = f"""function @pall@(@list@) {{
    return @list@.reduce(
        (@acc@, @p@) => @acc@.then((@acc2@) => Promise.resolve(@p@).then((@v@) => {merged})),
        Promise.resolve([])
    );
}}"""
    return defs, _pa_body(rng)


def pa_done(bug, rng):
    target = '@list@.length - 1' if bug == 'early' else '@list@.length'
    defs = f"""function @pall@(@list@) {{
    return new Promise((@resolve@, @reject@) => {{
        const @out@ = [];
        let @done@ = 0;
        for (LETK @i@ = 0; @i@ < @list@.length; @i@++) {{
            @list@[@i@].then((@v@) => {{
                @out@[@i@] = @v@;
                @done@ += 1;
                if (@done@ === {target}) @resolve@(@out@);
            }}).catch(@reject@);
        }}
    }});
}}"""
    return defs, _pa_body(rng)


def pa_recursive(bug, rng):
    nxt = '[@v@].concat(@acc2@)' if bug == 'reversed' else '@acc2@.concat([@v@])'
    defs = f"""function @pall@(@list@) {{
    const @step@ = (@idx@, @acc2@) =>
        @idx@ === @list@.length
            ? Promise.resolve(@acc2@)
            : Promise.resolve(@list@[@idx@]).then((@v@) => @step@(@idx@ + 1, {nxt}));
    return @step@(0, []);
}}"""
    return defs, _pa_body(rng)


# Debounce ─ input: n rapid calls ─ output executions after the dust settles

def _db_body(bug, rng):
    loop = _pick(rng,
                 'for (let @i@ = 0; @i@ < @n@; @i@++) @inc@();',
                 'let @i@ = 0;\nwhile (@i@ < @n@) {\n    @inc@();\n    @i@++;\n}',
                 'Array.from({ length: @n@ }).forEach(() => @inc@());')
    report = '__out__(@count@);' if bug == 'reads_too_early' else 'setTimeout(() => __out__(@count@), 200);'
    return f'let @count@ = 0;\nconst @inc@ = @debounce@(() => {{\n    @count@++;\n}}, 50);\n{loop}\n{report}'


def db_apply(bug, rng):
    clear = '' if bug == 'no_cancel' else '        clearTimeout(@timer@);\n'
    defs = f"""function @debounce@(@fn@, @wait@) {{
    let @timer@;
    return function (...@args@) {{
{clear}        @timer@ = setTimeout(() => @fn@.apply(this, @args@), @wait@);
    }};
}}"""
    return defs, _db_body(bug, rng)


def db_later(bug, rng):
    clear = '' if bug == 'no_cancel' else '        clearTimeout(@timeout@);\n'
    defs = f"""function @debounce@(@fn@, @wait@) {{
    let @timeout@ = null;
    return function @executed@(...@args@) {{
        const @later@ = () => {{
            @timeout@ = null;
            @fn@(...@args@);
        }};
{clear}        @timeout@ = setTimeout(@later@, @wait@);
    }};
}}"""
    return defs, _db_body(bug, rng)


def db_arrow(bug, rng):
    clear = '' if bug == 'no_cancel' else '        if (@handle@) clearTimeout(@handle@);\n'
    defs = f"""const @debounce@ = (@fn@, @wait@) => {{
    let @handle@ = 0;
    return (...@args@) => {{
{clear}        @handle@ = setTimeout(() => {{
            @handle@ = 0;
            @fn@(...@args@);
        }}, @wait@);
    }};
}};"""
    return defs, _db_body(bug, rng)


def db_timestamp(bug, rng):
    guard = ('        @pending@ = true;\n        setTimeout(@check@, @wait@);'
             if bug == 'no_flag' else
             '        if (!@pending@) {\n            @pending@ = true;\n            setTimeout(@check@, @wait@);\n        }')
    defs = f"""function @debounce@(@fn@, @wait@) {{
    let @last@ = 0;
    let @pending@ = false;
    let @latest@ = [];
    const @check@ = () => {{
        const @elapsed@ = Date.now() - @last@;
        if (@elapsed@ >= @wait@) {{
            @pending@ = false;
            @fn@(...@latest@);
        }} else {{
            setTimeout(@check@, @wait@ - @elapsed@);
        }}
    }};
    return (...@args@) => {{
        @last@ = Date.now();
        @latest@ = @args@;
{guard}
    }};
}}"""
    return defs, _db_body(bug, rng)


def db_class(bug, rng):
    clear = '' if bug == 'no_cancel' else '        clearTimeout(this.@timer@);\n'
    defs = f"""class @Debouncer@ {{
    constructor(@fn@, @wait@) {{
        this.@fn@ = @fn@;
        this.@wait@ = @wait@;
        this.@timer@ = null;
    }}
    call(...@args@) {{
{clear}        this.@timer@ = setTimeout(() => this.@fn@(...@args@), this.@wait@);
    }}
}}
function @debounce@(@fn@, @wait@) {{
    const @d@ = new @Debouncer@(@fn@, @wait@);
    return (...@args@) => @d@.call(...@args@);
}}"""
    return defs, _db_body(bug, rng)


# Throttle ─ input: k bursts of 3 calls, 250ms apart, 100ms throttle ─ output k

def _th_body(rng):
    burst = _pick(rng,
                  '    setTimeout(() => {\n        @fire@();\n        @fire@();\n        @fire@();\n    }, @b@ * 250);',
                  '    setTimeout(() => {\n        for (let @tries@ = 0; @tries@ < 3; @tries@++) @fire@();\n    }, @b@ * 250);')
    return (f'let @count@ = 0;\nconst @fire@ = @throttle@(() => {{\n    @count@++;\n}}, 100);\n'
            f'for (let @b@ = 0; @b@ < @n@; @b@++) {{\n{burst}\n}}\n'
            'setTimeout(() => __out__(@count@), @n@ * 250 + 50);')


def th_timestamp(bug, rng):
    record = '' if bug == 'never_records' else '            @lastCall@ = @now@;\n'
    defs = f"""function @throttle@(@fn@, @limit@) {{
    let @lastCall@ = -Infinity;
    return function (...@args@) {{
        const @now@ = Date.now();
        if (@now@ - @lastCall@ >= @limit@) {{
{record}            return @fn@.apply(this, @args@);
        }}
    }};
}}"""
    return defs, _th_body(rng)


def th_flag(bug, rng):
    reset = ('' if bug == 'never_resets' else
             '            setTimeout(() => {\n                @ready@ = true;\n            }, @limit@);\n')
    defs = f"""function @throttle@(@fn@, @limit@) {{
    let @ready@ = true;
    return (...@args@) => {{
        if (@ready@) {{
            @ready@ = false;
            @fn@(...@args@);
{reset}        }}
    }};
}}"""
    return defs, _th_body(rng)


def th_next_allowed(bug, rng):
    upd = '@nextAt@ = @limit@;' if bug == 'absolute_time' else '@nextAt@ = Date.now() + @limit@;'
    defs = f"""const @throttle@ = (@fn@, @limit@) => {{
    let @nextAt@ = 0;
    return (...@args@) => {{
        if (Date.now() < @nextAt@) return;
        {upd}
        @fn@(...@args@);
    }};
}};"""
    return defs, _th_body(rng)


def th_class(bug, rng):
    record = '' if bug == 'never_records' else '            this.@last@ = @now@;\n'
    defs = f"""class @Throttler@ {{
    constructor(@fn@, @limit@) {{
        this.@fn@ = @fn@;
        this.@limit@ = @limit@;
        this.@last@ = 0;
    }}
    call(...@args@) {{
        const @now@ = Date.now();
        if (@now@ - this.@last@ >= this.@limit@) {{
{record}            this.@fn@(...@args@);
        }}
    }}
}}
function @throttle@(@fn@, @limit@) {{
    const @gate@ = new @Throttler@(@fn@, @limit@);
    return (...@args@) => @gate@.call(...@args@);
}}"""
    return defs, _th_body(rng)


# Flatten ─ input: JSON array ─ output values space-separated

def _fl_body(rng, spread=False):
    expr = '[...@flatten@(@data@)]' if spread else '@flatten@(@data@)'
    return _pick(rng,
                 f"__out__({expr}.join(' '));",
                 f"const @result@ = {expr};\n__out__(@result@.join(' '));")


def fl_reduce_concat(bug, rng):
    rec = '@acc2@.concat(@item@)' if bug == 'one_level' else '@acc2@.concat(@flatten@(@item@))'
    defs = f"""function @flatten@(@arr@) {{
    return @arr@.reduce(
        (@acc2@, @item@) => (Array.isArray(@item@) ? {rec} : @acc2@.concat(@item@)),
        []
    );
}}"""
    return defs, _fl_body(rng)


def fl_reduce_push(bug, rng):
    nested = ('{\n            /* skip nested */\n        }' if bug == 'drops_nested'
              else '@acc2@.push(...@flatten@(@item@, @depth@ - 1));')
    defs = f"""function @flatten@(@arr@, @depth@ = Infinity) {{
    if (@depth@ === 0) return @arr@.slice();
    return @arr@.reduce((@acc2@, @item@) => {{
        if (Array.isArray(@item@)) {nested}
        else @acc2@.push(@item@);
        return @acc2@;
    }}, []);
}}"""
    return defs, _fl_body(rng)


def fl_builtin(bug, rng):
    depth = '1' if bug == 'one_level' else 'Infinity'
    return '', _pick(rng,
                     f"__out__(@data@.flat({depth}).join(' '));",
                     f"const @result@ = @data@.flat({depth});\n__out__(@result@.join(' '));")


def fl_stack(bug, rng):
    ret = 'return @sink@;' if bug == 'no_reverse' else 'return @sink@.reverse();'
    defs = f"""function @flatten@(@arr@) {{
    const @sink@ = [];
    const @stack@ = [...@arr@];
    while (@stack@.length) {{
        const @nxt@ = @stack@.pop();
        if (Array.isArray(@nxt@)) @stack@.push(...@nxt@);
        else @sink@.push(@nxt@);
    }}
    {ret}
}}"""
    return defs, _fl_body(rng)


def fl_queue(bug, rng):
    expand = '@queue@.push(...@nxt@);' if bug == 'breadth_first' else '@queue@.unshift(...@nxt@);'
    defs = f"""function @flatten@(@arr@) {{
    const @queue@ = @arr@.slice();
    const @sink@ = [];
    while (@queue@.length > 0) {{
        const @nxt@ = @queue@.shift();
        if (Array.isArray(@nxt@)) {{
            {expand}
        }} else {{
            @sink@.push(@nxt@);
        }}
    }}
    return @sink@;
}}"""
    return defs, _fl_body(rng)


def fl_walk(bug, rng):
    rec = '@sink@.push(@item@);' if bug == 'no_recursion' else '@walk@(@item@);'
    defs = f"""function @flatten@(@arr@) {{
    const @sink@ = [];
    function @walk@(@list@) {{
        for (const @item@ of @list@) {{
            if (Array.isArray(@item@)) {rec}
            else @sink@.push(@item@);
        }}
    }}
    @walk@(@arr@);
    return @sink@;
}}"""
    # bug no_recursion pushes nested arrays whole: join() prints them comma-separated
    return defs, _fl_body(rng)


def fl_generator(bug, rng):
    rec = 'yield @flatten@(@item@);' if bug == 'yield_generator' else 'yield* @flatten@(@item@);'
    defs = f"""function* @flatten@(@arr@) {{
    for (const @item@ of @arr@) {{
        if (Array.isArray(@item@)) {rec}
        else yield @item@;
    }}
}}"""
    return defs, _fl_body(rng, spread=True)


def fl_string(bug, rng):
    expr = "String(@data@).split(',')" if bug != 'drops_nested' else '@data@.filter((@item@) => !Array.isArray(@item@))'
    return '', _pick(rng,
                     f"__out__({expr}.join(' '));",
                     f"const @result@ = {expr};\n__out__(@result@.join(' '));")


# Deep clone ─ input: JSON object ─ output original inner.name after editing the clone

def _dc_body(rng):
    return _pick(rng,
                 "const @copy@ = @deepClone@(@data@);\n@copy@.inner.name = 'modified';\n__out__(@data@.inner.name);",
                 "const @copy@ = @deepClone@(@data@);\n@copy@['inner']['name'] = 'modified';\n__out__(@data@['inner']['name']);")


def dc_recursive(bug, rng):
    obj_part = ('    return @obj@;' if bug == 'arrays_only' else
                """    const @clone@ = {};
    for (const @prop@ in @obj@) {
        if (Object.prototype.hasOwnProperty.call(@obj@, @prop@)) @clone@[@prop@] = @deepClone@(@obj@[@prop@]);
    }
    return @clone@;""")
    defs = f"""function @deepClone@(@obj@) {{
    if (@obj@ === null || typeof @obj@ !== 'object') return @obj@;
    if (Array.isArray(@obj@)) return @obj@.map(@deepClone@);
{obj_part}
}}"""
    return defs, _dc_body(rng)


def dc_json(bug, rng):
    defs = ('const @deepClone@ = (@obj@) => ({ ...@obj@ });' if bug == 'spread_shallow'
            else 'const @deepClone@ = (@obj@) => JSON.parse(JSON.stringify(@obj@));')
    return defs, _dc_body(rng)


def dc_structured(bug, rng):
    inner = 'Object.assign({}, @obj@)' if bug == 'assign_shallow' else 'structuredClone(@obj@)'
    defs = f'function @deepClone@(@obj@) {{\n    return {inner};\n}}'
    return defs, _dc_body(rng)


def dc_entries(bug, rng):
    val = '@v@' if bug == 'no_recursion' else '@deepClone@(@v@)'
    defs = f"""const @deepClone@ = (@obj@) => {{
    if (typeof @obj@ !== 'object' || @obj@ === null) return @obj@;
    if (Array.isArray(@obj@)) return @obj@.map((@v@) => @deepClone@(@v@));
    return Object.fromEntries(Object.entries(@obj@).map(([@prop@, @v@]) => [@prop@, {val}]));
}};"""
    return defs, _dc_body(rng)


def dc_keys_reduce(bug, rng):
    val = '@obj@[@prop@]' if bug == 'no_recursion' else '@deepClone@(@obj@[@prop@])'
    defs = f"""function @deepClone@(@obj@) {{
    if (Array.isArray(@obj@)) {{
        const @clone@ = [];
        for (let @i@ = 0; @i@ < @obj@.length; @i@++) @clone@.push(@deepClone@(@obj@[@i@]));
        return @clone@;
    }}
    if (@obj@ && typeof @obj@ === 'object') {{
        return Object.keys(@obj@).reduce((@acc2@, @prop@) => {{
            @acc2@[@prop@] = {val};
            return @acc2@;
        }}, {{}});
    }}
    return @obj@;
}}"""
    return defs, _dc_body(rng)


# Event emitter ─ input: n emits ─ output "<on count> <once count>"

def _ee_body(rng):
    loop = _pick(rng,
                 "for (let @i@ = 0; @i@ < @n@; @i@++) @em@.emit('ping');",
                 "let @i@ = @n@;\nwhile (@i@-- > 0) {\n    @em@.emit('ping');\n}")
    report = _pick(rng, "__out__(@onHits@ + ' ' + @onceHits@);", '__out__(`${@onHits@} ${@onceHits@}`);')
    return (f'const @em@ = new @EE@();\nlet @onHits@ = 0;\nlet @onceHits@ = 0;\n'
            f"@em@.on('ping', () => {{\n    @onHits@++;\n}});\n"
            f"@em@.once('ping', () => {{\n    @onceHits@++;\n}});\n{loop}\n{report}")


def ee_object(bug, rng):
    if bug == 'once_is_on':
        once = '    once(@event@, @listener@) {\n        return this.on(@event@, @listener@);\n    }'
    else:
        target = '@listener@' if bug == 'off_wrong_fn' else '@wrapper@'
        once = f"""    once(@event@, @listener@) {{
        const @wrapper@ = (...@args@) => {{
            @listener@(...@args@);
            this.off(@event@, {target});
        }};
        return this.on(@event@, @wrapper@);
    }}"""
    defs = f"""class @EE@ {{
    constructor() {{
        this.events = {{}};
    }}
    on(@event@, @listener@) {{
        if (!this.events[@event@]) this.events[@event@] = [];
        this.events[@event@].push(@listener@);
        return this;
    }}
    off(@event@, @listener@) {{
        if (this.events[@event@]) {{
            this.events[@event@] = this.events[@event@].filter((@entryL@) => @entryL@ !== @listener@);
        }}
        return this;
    }}
    emit(@event@, ...@args@) {{
        (this.events[@event@] || []).slice().forEach((@entryL@) => @entryL@(...@args@));
        return this;
    }}
{once}
}}"""
    return defs, _ee_body(rng)


def ee_map_records(bug, rng):
    keep = 'this.listeners.set(@event@, []);' if bug == 'clears_all' else \
        'this.listeners.set(@event@, @snapshot@.filter((@entryL@) => !@entryL@.once));'
    defs = f"""class @EE@ {{
    constructor() {{
        this.listeners = new Map();
    }}
    on(@event@, @fn@, once = false) {{
        if (!this.listeners.has(@event@)) this.listeners.set(@event@, []);
        this.listeners.get(@event@).push({{ @fn@, once }});
        return this;
    }}
    once(@event@, @fn@) {{
        return this.on(@event@, @fn@, true);
    }}
    off(@event@, @fn@) {{
        const @snapshot@ = this.listeners.get(@event@) || [];
        this.listeners.set(@event@, @snapshot@.filter((@entryL@) => @entryL@.@fn@ !== @fn@));
        return this;
    }}
    emit(@event@, ...@args@) {{
        const @snapshot@ = this.listeners.get(@event@) || [];
        {keep}
        @snapshot@.forEach((@entryL@) => @entryL@.@fn@(...@args@));
        return this;
    }}
}}"""
    return defs, _ee_body(rng)


def ee_set(bug, rng):
    remove = '' if bug == 'once_is_on' else '            @bucket@.delete(@wrapper@);\n'
    defs = f"""class @EE@ {{
    constructor() {{
        this.handlers = new Map();
    }}
    on(@event@, @fn@) {{
        if (!this.handlers.has(@event@)) this.handlers.set(@event@, new Set());
        this.handlers.get(@event@).add(@fn@);
        return this;
    }}
    off(@event@, @fn@) {{
        const @bucket@ = this.handlers.get(@event@);
        if (@bucket@) @bucket@.delete(@fn@);
        return this;
    }}
    once(@event@, @fn@) {{
        const @bucket@ = this.handlers.get(@event@) || new Set();
        this.handlers.set(@event@, @bucket@);
        const @wrapper@ = (...@args@) => {{
{remove}            @fn@(...@args@);
        }};
        @bucket@.add(@wrapper@);
        return this;
    }}
    emit(@event@, ...@args@) {{
        for (const @fn@ of [...(this.handlers.get(@event@) || [])]) @fn@(...@args@);
        return this;
    }}
}}"""
    return defs, _ee_body(rng)


def ee_flag(bug, rng):
    check = '' if bug == 'once_is_on' else '            if (@fired@) return;\n            @fired@ = true;\n'
    defs = f"""class @EE@ {{
    constructor() {{
        this.map = {{}};
    }}
    on(@event@, @listener@) {{
        (this.map[@event@] = this.map[@event@] || []).push(@listener@);
        return this;
    }}
    off(@event@, @listener@) {{
        const @bucket@ = this.map[@event@] || [];
        const @i@ = @bucket@.indexOf(@listener@);
        if (@i@ !== -1) @bucket@.splice(@i@, 1);
        return this;
    }}
    once(@event@, @listener@) {{
        let @fired@ = false;
        const @wrapper@ = (...@args@) => {{
{check}            @listener@(...@args@);
        }};
        return this.on(@event@, @wrapper@);
    }}
    emit(@event@, ...@args@) {{
        const @bucket@ = this.map[@event@];
        if (!@bucket@) return false;
        for (const @listener@ of @bucket@.slice()) @listener@(...@args@);
        return true;
    }}
}}"""
    return defs, _ee_body(rng)


# LRU cache ─ input: capacity + ops ─ output get results

def _lru_body(rng):
    return _pick(rng, """const @lru@ = new @LRU@(@capacity@);
const @results@ = [];
for (const @line@ of @ops@) {
    const [@op@, @key@, @value@] = @line@.trim().split(' ');
    if (@op@ === 'put') @lru@.put(Number(@key@), Number(@value@));
    else @results@.push(@lru@.get(Number(@key@)));
}
__out__(@results@.join(' '));""", """const @lru@ = new @LRU@(@capacity@);
const @results@ = [];
@ops@.forEach((@line@) => {
    const @parts2@ = @line@.trim().split(' ');
    if (@parts2@[0] === 'put') @lru@.put(+@parts2@[1], +@parts2@[2]);
    else @results@.push(@lru@.get(+@parts2@[1]));
});
__out__(@results@.join(' '));""")


def lru_map(bug, rng):
    refresh = ('' if bug == 'fifo' else
               '        const @value@ = this.map.get(@key@);\n        this.map.delete(@key@);\n'
               '        this.map.set(@key@, @value@);\n        return @value@;\n')
    get_ret = '        return this.map.get(@key@);\n' if bug == 'fifo' else ''
    evict = '[...this.map.keys()].pop()' if bug == 'evicts_newest' else 'this.map.keys().next().value'
    defs = f"""class @LRU@ {{
    constructor(@capacity@) {{
        this.capacity = @capacity@;
        this.map = new Map();
    }}
    get(@key@) {{
        if (!this.map.has(@key@)) return -1;
{refresh}{get_ret}    }}
    put(@key@, @value@) {{
        if (this.map.has(@key@)) this.map.delete(@key@);
        else if (this.map.size === this.capacity) this.map.delete({evict});
        this.map.set(@key@, @value@);
    }}
}}"""
    return defs, _lru_body(rng)


def lru_linked(bug, rng):
    move = '' if bug == 'fifo' else '        this._remove(@node@);\n        this._addFront(@node@);\n'
    defs = f"""class @Node@ {{
    constructor(@key@, @value@) {{
        this.key = @key@;
        this.val = @value@;
        this.prev = null;
        this.next = null;
    }}
}}
class @LRU@ {{
    constructor(@capacity@) {{
        this.capacity = @capacity@;
        this.index = new Map();
        this.head = new @Node@(0, 0);
        this.tail = new @Node@(0, 0);
        this.head.next = this.tail;
        this.tail.prev = this.head;
    }}
    _remove(@node@) {{
        @node@.prev.next = @node@.next;
        @node@.next.prev = @node@.prev;
    }}
    _addFront(@node@) {{
        @node@.next = this.head.next;
        @node@.prev = this.head;
        this.head.next.prev = @node@;
        this.head.next = @node@;
    }}
    get(@key@) {{
        const @node@ = this.index.get(@key@);
        if (!@node@) return -1;
{move}        return @node@.val;
    }}
    put(@key@, @value@) {{
        if (this.index.has(@key@)) this._remove(this.index.get(@key@));
        else if (this.index.size === this.capacity) {{
            const @lruNode@ = this.tail.prev;
            this._remove(@lruNode@);
            this.index.delete(@lruNode@.key);
        }}
        const @node@ = new @Node@(@key@, @value@);
        this._addFront(@node@);
        this.index.set(@key@, @node@);
    }}
}}"""
    return defs, _lru_body(rng)


def lru_array(bug, rng):
    touch = '' if bug == 'fifo' else '        this._touch(@key@);\n'
    put_touch = ('            this.store[@key@] = @value@;\n            return;\n' if bug == 'update_no_refresh' else
                 '            this.store[@key@] = @value@;\n            this._touch(@key@);\n            return;\n')
    defs = f"""class @LRU@ {{
    constructor(@capacity@) {{
        this.capacity = @capacity@;
        this.store = {{}};
        this.keys = [];
    }}
    _touch(@key@) {{
        const @i@ = this.keys.indexOf(@key@);
        if (@i@ > -1) this.keys.splice(@i@, 1);
        this.keys.push(@key@);
    }}
    get(@key@) {{
        if (!(@key@ in this.store)) return -1;
{touch}        return this.store[@key@];
    }}
    put(@key@, @value@) {{
        if (@key@ in this.store) {{
{put_touch}        }}
        if (this.keys.length >= this.capacity) {{
            const @oldest@ = this.keys.shift();
            delete this.store[@oldest@];
        }}
        this.store[@key@] = @value@;
        this.keys.push(@key@);
    }}
}}"""
    return defs, _lru_body(rng)


def lru_tick(bug, rng):
    stamp = '' if bug == 'fifo' else '        @node@.used = ++this.clock;\n'
    pick = '<' if bug != 'evicts_newest' else '>'
    defs = f"""class @LRU@ {{
    constructor(@capacity@) {{
        this.capacity = @capacity@;
        this.items = new Map();
        this.clock = 0;
    }}
    get(@key@) {{
        const @node@ = this.items.get(@key@);
        if (@node@ === undefined) return -1;
{stamp}        return @node@.value;
    }}
    put(@key@, @value@) {{
        if (!this.items.has(@key@) && this.items.size >= this.capacity) {{
            let @oldest@ = null;
            for (const [@k2@, @node@] of this.items) {{
                if (@oldest@ === null || @node@.used {pick} this.items.get(@oldest@).used) @oldest@ = @k2@;
            }}
            this.items.delete(@oldest@);
        }}
        this.items.set(@key@, {{ value: @value@, used: ++this.clock }});
    }}
}}"""
    return defs, _lru_body(rng)


# Observer ─ input: states ─ output states received, comma-separated

def ob_class(bug, rng):
    if bug == 'notify_first':
        set_state = '        this.notify();\n        this.state = @state@;'
    else:
        set_state = '        this.state = @state@;\n        this.notify();'
    defs = f"""class @Subject@ {{
    constructor() {{
        this.observers = [];
        this.state = null;
    }}
    @subscribe@(@observer@) {{
        this.observers.push(@observer@);
    }}
    unsubscribe(@observer@) {{
        this.observers = this.observers.filter((@entryL@) => @entryL@ !== @observer@);
    }}
    setState(@state@) {{
{set_state}
    }}
    notify() {{
        this.observers.forEach((@entryL@) => @entryL@.update(this.state));
    }}
}}"""
    body = """const @subject@ = new @Subject@();
const @received@ = [];
@subject@.@subscribe@({ update: (@state@) => @received@.push(@state@) });
@states@.forEach((@state@) => @subject@.setState(@state@));
__out__(@received@.join(','));"""
    return defs, body


def ob_closure(bug, rng):
    store = '@received@.add(@state@)' if bug == 'dedupes' else '@received@.push(@state@)'
    init = 'new Set()' if bug == 'dedupes' else '[]'
    printed = '[...@received@]' if bug == 'dedupes' else '@received@'
    defs = """function @createSubject@() {
    const @observers@ = new Set();
    let @state@;
    return {
        @subscribe@(@fn@) {
            @observers@.add(@fn@);
            return () => @observers@.delete(@fn@);
        },
        setState(@v@) {
            @state@ = @v@;
            @observers@.forEach((@fn@) => @fn@(@state@));
        },
    };
}"""
    body = f"""const @subject@ = @createSubject@();
const @received@ = {init};
@subject@.@subscribe@((@state@) => {store});
for (const @state@ of @states@) @subject@.setState(@state@);
__out__({printed}.join(','));"""
    return defs, body


def ob_ids(bug, rng):
    order = ('            this.subs.forEach((@fn@) => @fn@(this.state));\n            this.state = @state@;'
             if bug == 'notify_first' else
             '            this.state = @state@;\n            this.subs.forEach((@fn@) => @fn@(this.state));')
    defs = f"""class @Subject@ {{
    constructor() {{
        this.subs = new Map();
        this.nextId = 1;
        this.state = undefined;
    }}
    @subscribe@(@fn@) {{
        const @id@ = this.nextId++;
        this.subs.set(@id@, @fn@);
        return () => this.subs.delete(@id@);
    }}
    setState(@state@) {{
        if (@state@ !== undefined) {{
{order}
        }}
    }}
}}"""
    body = """const @subject@ = new @Subject@();
const @received@ = [];
@subject@.@subscribe@((@state@) => {
    @received@.push(@state@);
});
let @i@ = 0;
while (@i@ < @states@.length) {
    @subject@.setState(@states@[@i@]);
    @i@ += 1;
}
__out__(@received@.join(','));"""
    return defs, body


def ob_callbacks(bug, rng):
    loop = ('        for (const @fn@ of this.observers) @fn@(this.state);\n        this.state = @state@;'
            if bug == 'notify_first' else
            '        this.state = @state@;\n        for (const @fn@ of this.observers) @fn@(this.state);')
    defs = f"""class @Subject@ {{
    observers = [];
    state = null;
    @subscribe@(@fn@) {{
        this.observers.push(@fn@);
        return this;
    }}
    setState(@state@) {{
{loop}
    }}
}}"""
    body = """const @received@ = [];
const @subject@ = new @Subject@().@subscribe@((@state@) => @received@.push(@state@));
@states@.forEach((@state@) => {
    @subject@.setState(@state@);
});
__out__(@received@.join(','));"""
    return defs, body


# Promise.all + timeout ─ input: ms + delays ─ output values or TIMEOUT

def _pt_body(rng):
    make = _pick(rng,
                 'const @list@ = @delays@.map((@d2@, @i@) => new Promise((@res@) => setTimeout(() => @res@(@i@ + 1), @d2@)));',
                 'const @list@ = [];\n@delays@.forEach((@d2@, @i@) => {\n'
                 '    @list@.push(new Promise((@res@) => setTimeout(() => @res@(@i@ + 1), @d2@)));\n});')
    tail = _pick(rng,
                 "@pat@(@list@, @ms@)\n    .then((@vals@) => __out__(@vals@.join(' ')))\n    .catch((@err@) => __out__(@err@.message));",
                 "@pat@(@list@, @ms@).then(\n    (@vals@) => __out__(@vals@.join(' ')),\n    (@err@) => __out__(@err@.message)\n);",
                 "(async () => {\n    try {\n        const @vals@ = await @pat@(@list@, @ms@);\n"
                 "        __out__(@vals@.join(' '));\n    } catch (@err@) {\n        __out__(@err@.message);\n    }\n})();")
    return make + '\n' + tail


def _timeout_msg(bug):
    return "'Timeout'" if bug == 'wrong_message' else "'TIMEOUT'"


def pt_race(bug, rng):
    if bug == 'no_timeout':
        defs = 'function @pat@(@list@, @ms@) {\n    return Promise.all(@list@);\n}'
        return defs, _pt_body(rng)
    defs = f"""function @pat@(@list@, @ms@) {{
    let @timer@;
    const @timeout@ = new Promise((_, @reject@) => {{
        @timer@ = setTimeout(() => @reject@(new Error({_timeout_msg(bug)})), @ms@);
    }});
    return Promise.race([Promise.all(@list@), @timeout@]).finally(() => clearTimeout(@timer@));
}}"""
    return defs, _pt_body(rng)


def pt_manual(bug, rng):
    defs = f"""function @pat@(@list@, @ms@) {{
    return new Promise((@resolve@, @reject@) => {{
        const @results@ = new Array(@list@.length);
        let @left@ = @list@.length;
        const @timer@ = setTimeout(() => @reject@(new Error({_timeout_msg(bug)})), @ms@);
        @list@.forEach((@p@, @i@) => {{
            Promise.resolve(@p@).then((@v@) => {{
                @results@[@i@] = @v@;
                @left@ -= 1;
                if (@left@ === 0) {{
                    clearTimeout(@timer@);
                    @resolve@(@results@);
                }}
            }}, (@err@) => {{
                clearTimeout(@timer@);
                @reject@(@err@);
            }});
        }});
    }});
}}"""
    return defs, _pt_body(rng)


def pt_async(bug, rng):
    arm = ('        setTimeout(@reject@(new Error(\'TIMEOUT\')), @ms@);' if bug == 'rejects_immediately' else
           f'        @timer@ = setTimeout(() => @reject@(new Error({_timeout_msg(bug)})), @ms@);')
    defs = f"""async function @pat@(@list@, @ms@) {{
    let @timer@;
    const @timeout@ = new Promise((_, @reject@) => {{
{arm}
    }});
    try {{
        return await Promise.race([Promise.all(@list@), @timeout@]);
    }} finally {{
        clearTimeout(@timer@);
    }}
}}"""
    return defs, _pt_body(rng)


def pt_flag(bug, rng):
    defs = f"""function @pat@(@list@, @ms@) {{
    return new Promise((@resolve@, @reject@) => {{
        let @timedOut@ = false;
        const @timer@ = setTimeout(() => {{
            @timedOut@ = true;
            @reject@(new Error({_timeout_msg(bug)}));
        }}, @ms@);
        Promise.all(@list@).then((@vals@) => {{
            if (@timedOut@) return;
            clearTimeout(@timer@);
            @resolve@(@vals@);
        }}, @reject@);
    }});
}}"""
    return defs, _pt_body(rng)


def pt_sequential(bug, rng):
    defs = f"""function @pat@(@list@, @ms@) {{
    const @deadline@ = new Promise((_, @reject@) => setTimeout(() => @reject@(new Error({_timeout_msg(bug)})), @ms@));
    const @collectAll@ = (async () => {{
        const @out@ = [];
        for (const @p@ of @list@) @out@.push(await @p@);
        return @out@;
    }})();
    return Promise.race([@collectAll@, @deadline@]);
}}"""
    return defs, _pt_body(rng)


def pt_class(bug, rng):
    defs = f"""class @Deadline@ {{
    constructor(@ms@) {{
        this.ms = @ms@;
        this.timer = null;
    }}
    start() {{
        return new Promise((_, @reject@) => {{
            this.timer = setTimeout(() => @reject@(new Error({_timeout_msg(bug)})), this.ms);
        }});
    }}
    stop() {{
        clearTimeout(this.timer);
    }}
}}
function @pat@(@list@, @ms@) {{
    const @dl@ = new @Deadline@(@ms@);
    return Promise.race([Promise.all(@list@), @dl@.start()]).finally(() => @dl@.stop());
}}"""
    return defs, _pt_body(rng)


# ── problem table ─────────────────────────────────────────────────────────────

PROBLEMS = {
    'two_sum': {'input': 'two_sum', 'cores': {
        'brute': (ts_brute, ['self_pair', 'values']),
        'map': (ts_map, ['insert_first', 'reversed']),
        'object': (ts_object, ['one_based']),
        'two_pass': (ts_two_pass, ['no_self_check']),
        'pointers': (ts_pointers, ['unsorted_output']),
        'while': (ts_while, ['j_from_zero']),
    }},
    'memoize_fib': {'input': 'int', 'cores': {
        'map_json': (mf_map_json, ['base_one']),
        'object': (mf_object, ['ignores_args']),
        'single': (mf_single, ['wrong_recurrence']),
        'array': (mf_array, ['base_swap']),
        'class': (mf_class, ['base_one', 'off_by_one']),
    }},
    'curry_multiply': {'input': 'triple', 'cores': {
        'apply': (cu_apply, ['add']),
        'arrow': (cu_arrow, ['strict_gt']),
        'bind': (cu_bind, ['two_args']),
        'collect': (cu_collect, ['forgets_args']),
        'arguments': (cu_arguments, ['strict_gt']),
        'recursive': (cu_recursive, ['strict_gt']),
        'prototype': (cu_prototype, ['forgets_args']),
        'while': (cu_while, ['off_by_one']),
    }},
    'promise_all': {'input': 'num_list', 'cores': {
        'counter': (pa_counter, ['push_order']),
        'await': (pa_await, ['skips_last']),
        'reduce': (pa_reduce, ['reversed']),
        'done': (pa_done, ['early']),
        'recursive': (pa_recursive, ['reversed']),
    }},
    'debounce': {'input': 'int', 'cores': {
        'apply': (db_apply, ['no_cancel', 'reads_too_early']),
        'later': (db_later, ['no_cancel']),
        'arrow': (db_arrow, ['no_cancel']),
        'timestamp': (db_timestamp, ['no_flag']),
        'class': (db_class, ['no_cancel', 'reads_too_early']),
    }},
    'throttle': {'input': 'int', 'cores': {
        'timestamp': (th_timestamp, ['never_records']),
        'flag': (th_flag, ['never_resets']),
        'next_allowed': (th_next_allowed, ['absolute_time']),
        'class': (th_class, ['never_records']),
    }},
    'flatten_deep': {'input': 'json', 'cores': {
        'reduce_concat': (fl_reduce_concat, ['one_level']),
        'reduce_push': (fl_reduce_push, ['drops_nested']),
        'builtin': (fl_builtin, ['one_level']),
        'stack': (fl_stack, ['no_reverse']),
        'queue': (fl_queue, ['breadth_first']),
        'walk': (fl_walk, ['no_recursion']),
        'generator': (fl_generator, ['yield_generator']),
        'string': (fl_string, ['drops_nested']),
    }},
    # the interview variant forbids Array.prototype.flat
    'flatten_no_builtin': {'input': 'json', 'cores': {
        'reduce_concat': (fl_reduce_concat, ['one_level']),
        'reduce_push': (fl_reduce_push, ['drops_nested']),
        'stack': (fl_stack, ['no_reverse']),
        'queue': (fl_queue, ['breadth_first']),
        'walk': (fl_walk, ['no_recursion']),
        'generator': (fl_generator, ['yield_generator']),
    }},
    'deep_clone': {'input': 'json', 'cores': {
        'recursive': (dc_recursive, ['arrays_only']),
        'json': (dc_json, ['spread_shallow']),
        'structured': (dc_structured, ['assign_shallow']),
        'entries': (dc_entries, ['no_recursion']),
        'keys_reduce': (dc_keys_reduce, ['no_recursion']),
    }},
    'event_emitter': {'input': 'int', 'cores': {
        'object': (ee_object, ['once_is_on', 'off_wrong_fn']),
        'map_records': (ee_map_records, ['clears_all']),
        'set': (ee_set, ['once_is_on']),
        'flag': (ee_flag, ['once_is_on']),
    }},
    'lru_cache': {'input': 'lru', 'cores': {
        'map': (lru_map, ['fifo', 'evicts_newest']),
        'linked': (lru_linked, ['fifo']),
        'array': (lru_array, ['fifo', 'update_no_refresh']),
        'tick': (lru_tick, ['fifo', 'evicts_newest']),
    }},
    'observer': {'input': 'words', 'cores': {
        'class': (ob_class, ['notify_first']),
        'closure': (ob_closure, ['dedupes']),
        'ids': (ob_ids, ['notify_first']),
        'callbacks': (ob_callbacks, ['notify_first']),
    }},
    'promise_all_timeout': {'input': 'timeout', 'cores': {
        'race': (pt_race, ['no_timeout', 'wrong_message']),
        'manual': (pt_manual, ['wrong_message']),
        'async': (pt_async, ['rejects_immediately']),
        'flag': (pt_flag, ['wrong_message']),
        'sequential': (pt_sequential, ['wrong_message']),
        'class': (pt_class, ['wrong_message']),
    }},
}

COMMENT_LINES = [
    '// read input', '// parse the input', '// edge cases first', '// TODO: tidy up',
    '// works for the sample', '// helper', '// main logic', '// print answer',
    '// O(n) approach', '// keep it simple', '// checked with the examples',
]


# Declaration keyword habits. Students learning JS mix const/let/var
# inconsistently, each with their own leaning: every declaration site picks its
# keyword from the author's personal weights. A site written `let` in a
# template is reassigned, so it never becomes const. 'var' students still need
# block scoping where a closure captures a loop index asynchronously; templates
# mark those sites LETK and they always stay `let`.
DECL_HABITS = {
    'modern':     (0.85, 0.15, 0.00),
    'let_lover':  (0.15, 0.85, 0.00),
    'old_school': (0.00, 0.10, 0.90),
    'mixed':      (0.40, 0.30, 0.30),
    'transition': (0.50, 0.00, 0.50),
    'loose':      (0.10, 0.45, 0.45),
}


def _decl_weights(rng):
    base = DECL_HABITS[rng.choice(list(DECL_HABITS))]
    w = [max(0.0, b + rng.uniform(-0.12, 0.12)) for b in base]
    total = sum(w) or 1.0
    return tuple(x / total for x in w)


# Optional extras a student may add around any solution.
EXTRAS = {
    'strict': "'use strict';",
    'debug': ('const @DEBUG@ = false;\n'
              'function @dbg@(...@dargs@) {\n    if (@DEBUG@) console.error(...@dargs@);\n}'),
    'guard': 'if (!@text@ || !@text@.trim()) {\n    process.exit(0);\n}',
    'validate': ('function @check@(@cond@, @msg@) {\n    if (!@cond@) {\n        throw new Error(@msg@);\n    }\n}'),
    'timing': ('const @startedAt@ = Date.now();\n'
               "process.on('exit', () => {\n    console.error(`took ${Date.now() - @startedAt@}ms`);\n});"),
}
NAME_POOLS.update({
    'DEBUG': ['DEBUG', 'VERBOSE', 'TRACE', 'LOGGING'],
    'dbg': ['debug', 'dbg', 'trace', 'note'],
    'dargs': ['parts', 'msg', 'items', 'stuff'],
    'check': ['check', 'assert', 'ensure', 'require_', 'expect'],
    'cond': ['cond', 'ok', 'condition', 'pass'],
    'msg': ['msg', 'message_', 'why', 'text_'],
    'startedAt': ['startedAt', 't0', 'begin', 'startTime'],
})


def _apply_decl_style(code, weights, seed):
    rng = random.Random(seed)
    wc, wl, wv = weights

    def pick(m):
        if m.group(0) == 'const':
            return rng.choices(['const', 'let', 'var'], weights=[wc, wl, wv])[0]
        if wl + wv == 0:
            return 'let'
        return rng.choices(['let', 'var'], weights=[wl, wv])[0]

    code = re.sub(r'\b(?:const|let)\b', pick, code)
    return code.replace('LETK', 'let')


# Function-expression habits: some students write `function (x) { ... }`
# where others write `(x) => { ... }`. Only block-bodied arrows that don't use
# `this` are rewritten, so behaviour is unchanged.
FN_HABITS = {'arrows': 0.05, 'mixed': 0.5, 'functions': 0.9}

_ARROW = re.compile(r'(\((?:[^()]*)\)|@\w+@)\s*=>\s*\{')


def _apply_fn_style(code, p_function, seed):
    rng = random.Random(seed)
    out, i = [], 0
    for m in _ARROW.finditer(code):
        if m.start() < i:
            continue
        # body extent: match braces from the opening '{'
        depth, k = 0, m.end() - 1
        while True:
            ch = code[k]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    break
            k += 1
        body = code[m.end():k]
        convert = 'this' not in body and rng.random() < p_function
        if convert:
            params = m.group(1)
            if not params.startswith('('):
                params = f'({params})'
            out.append(code[i:m.start()])
            out.append(f'function {params} {{')
            i = m.end()
    out.append(code[i:])
    return ''.join(out)


def structures(problem):
    """Every (core, entry, parse) structure a student can write for a problem."""
    spec = PROBLEMS[problem]
    n_parse = len(PARSERS[spec['input']])
    return [(core, entry, parse)
            for core in spec['cores']
            for entry in ENTRIES
            for parse in range(n_parse)]


def bugs_for(problem, core):
    return PROBLEMS[problem]['cores'][core][1]


def build_program(problem, author, bug=None, names_seed=None, printer=None, comment_seed=None):
    """
    Render one program.

    author: dict with core, entry (layout, reader), parse, printer, sub, names,
    comments seeds. bug=None renders the correct program; otherwise one of the
    core's bug ids. names_seed / printer / comment_seed override the author's
    (used to model a renamed, lightly edited copy).
    """
    spec = PROBLEMS[problem]
    core_fn, bug_ids = spec['cores'][author['core']]
    if bug is not None and bug not in bug_ids:
        raise ValueError(f'{problem}/{author["core"]} has no bug {bug!r}')
    defs, body = core_fn(bug, random.Random(author['sub']))
    parse = PARSERS[spec['input']][author['parse']]
    extras = author.get('extras', ())
    if 'guard' in extras:
        parse = EXTRAS['guard'] + '\n' + parse
    if 'validate' in extras:
        parse = "@check@(@text@.length > 0, 'empty input');\n" + parse
    if 'debug' in extras:
        body = "@dbg@('input parsed');\n" + body
    printer = printer or author['printer']
    helper = PRINTERS[printer][0]
    layout, reader = author['entry']
    blocks = _assemble(layout, reader, defs, parse, body, helper)
    if 'debug' in extras:
        blocks.insert(0, EXTRAS['debug'])
    if 'validate' in extras:
        blocks.insert(0, EXTRAS['validate'])
    if 'timing' in extras:
        blocks.insert(0, EXTRAS['timing'])
    if 'strict' in extras:
        blocks.insert(0, EXTRAS['strict'])

    crng = random.Random(author['comments'] if comment_seed is None else comment_seed)
    for _ in range(crng.choice([0, 0, 1, 2])):
        blocks.insert(crng.randrange(len(blocks) + 1), crng.choice(COMMENT_LINES))

    code = _render_out('\n\n'.join(blocks), printer)
    code = _apply_fn_style(code, author['fn'], author['decl_seed'] + 1)
    code = _apply_decl_style(code, author['decl'], author['decl_seed'])
    names = Names(random.Random(author['names'] if names_seed is None else names_seed))
    return _fill(code, names) + '\n'


def make_author(problem, structure, seed):
    """An author = a structure plus the personal choices that ride along with it."""
    rng = random.Random(seed)
    core, entry, parse = structure
    return {
        'core': core, 'entry': entry, 'parse': parse,
        'printer': rng.choice(list(PRINTERS)),
        'decl': _decl_weights(rng),
        'decl_seed': rng.randrange(1 << 30),
        'fn': FN_HABITS[rng.choice(list(FN_HABITS))],
        'extras': tuple(e for e in EXTRAS if rng.random() < 0.35),
        'sub': rng.randrange(1 << 30),
        'names': rng.randrange(1 << 30),
        'comments': rng.randrange(1 << 30),
    }


# ── leaked solutions (circulated by the planted copying cases) ────────────────
#
# Hand-written, in a style no generated author uses, so the copiers match each
# other and nobody else.

LEAKED = {
    'observer': r"""// observer via a small event bus
const bus = {
    handlers: {},
    on(topic, handler) {
        (this.handlers[topic] = this.handlers[topic] || []).push(handler);
    },
    emit(topic, payload) {
        for (const handler of this.handlers[topic] || []) handler(payload);
    },
};
let current = null;
const history = [];
bus.on('change', value => { current = value; });
bus.on('change', value => history.push(value));
const input = require('fs').readFileSync('/dev/stdin', 'utf8');
for (const token of input.split(/\s+/)) {
    if (token.length > 0) bus.emit('change', token);
}
process.stdout.write(history.join(',') + '\n');
""",
    'two_sum': r"""/* two-sum: single pass with a complement table */
var data = require('fs').readFileSync(0, 'utf8').split(/\n/);
var arr = data[1].split(' ').map(function (s) { return parseInt(s, 10); });
var target = parseInt(data[2], 10);
var table = {};
var out = null;
arr.some(function (x, idx) {
    if (Object.prototype.hasOwnProperty.call(table, target - x)) {
        out = [table[target - x], idx];
        return true;
    }
    table[x] = idx;
    return false;
});
process.stdout.write(out.join(' ') + '\n');
""",
    'lru_cache': r"""// LRU using Map insertion order (editorial)
function LRUCache(capacity) {
    this.cap = capacity;
    this.m = new Map();
}
LRUCache.prototype.get = function (key) {
    if (!this.m.has(key)) return -1;
    var v = this.m.get(key);
    this.m.delete(key);
    this.m.set(key, v);
    return v;
};
LRUCache.prototype.put = function (key, value) {
    this.m.delete(key);
    this.m.set(key, value);
    if (this.m.size > this.cap) this.m.delete(this.m.keys().next().value);
};
var lines = require('fs').readFileSync(0, 'utf8').split(/\n/).filter(Boolean);
var c = new LRUCache(+lines[0]);
var printed = [];
lines.slice(1).forEach(function (cmd) {
    var t = cmd.split(' ');
    if (t[0] === 'get') printed.push(c.get(+t[1]));
    else c.put(+t[1], +t[2]);
});
console.log(printed.join(' '));
""",
}
