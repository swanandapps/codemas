#!/usr/bin/env bash
# End-to-end smoke test of the deployed pipeline, driven through the public API as a student:
#   Django (Railway) -> outbox -> relay -> SQS codemas-exec -> Lambda codemas-exec -> Django
#
# Usage:
#   CODEMAS_API_URL=https://<railway-web-host> SMOKE_USERNAME=<student> SMOKE_PASSWORD=<pw> \
#     deploy/aws/smoke.sh [--probe | --no-probe]
#
# Submits, in the open exam:
#   1. "Find Target in Sorted Array": a correct Python solution      -> must end 'passed'
#   2. "Find Target in Sorted Array": a correct JavaScript solution  -> must end 'passed'
#   With --probe (the default), to "Find First and Last Position":
#   3. an environment-leak probe: a Python program that scans /proc/*/environ and prints only
#      "LEAK <pid> <VARNAME>" for JOB_SIGNING_SECRET, AWS_SECRET_ACCESS_KEY or AWS_SESSION_TOKEN,
#      or "NO_LEAK". It never prints values. The script fails loudly if JOB_SIGNING_SECRET is
#      found (the Lambda must not have it) and warns on AWS_* names (accepted risk R2: Lambda
#      always injects the role's credentials, and that role can receive, delete and hide
#      codemas-exec messages, so student code could claim a classmate's job, read its code and
#      inputs, forge a pass or a fail, or delay others' grading; the fix is the runner split).
#   4. an egress probe, in two steps. socket(AF_INET) refused -> EGRESS_BLOCKED. If it succeeds:
#      EGRESS_FILTER_OFF, then connect(1.1.1.1:443, 3 s) -> EGRESS_OPEN or EGRESS_NOROUTE.
#      Anything else -> "EGRESS_UNKNOWN <errno>". It also prints "UNIX_SOCKETS <n>" (entries in
#      /proc/net/unix; a count only, no paths). The script warns on EGRESS_OPEN, EGRESS_FILTER_OFF
#      and EGRESS_UNKNOWN (accepted risk R1: Lambda refuses the seccomp filter).
#   A probe with no verdict line at all fails the run. Risks R1/R2: docs/superpowers/specs/2026-10-04-lambda-guardrails.md
#   The probes are graded 'failed' (their output isn't the answer).
# Each submission spends one attempt of the smoke student on its question: 2 per question with the
# probes, within the default allowance of 3. A re-run would go over it, so it needs a fresh student.
# The student must be enrolled in the open exam first (trainer: POST /api/exams/<id>/enrollments/).
#
# Optional env: SMOKE_QUESTION_ID / SMOKE_PROBE_QUESTION_ID (skip the lookups), SMOKE_TIMEOUT_S (default 60).
# Then prints the Lambda's CloudWatch log lines for these submissions (needs the aws CLI).
set -euo pipefail

REGION=ap-southeast-1
LOG_GROUP=/aws/lambda/codemas-exec
QUESTION_TITLE='Find Target in Sorted Array'
PROBE_QUESTION_TITLE='Find First and Last Position'   # same open exam; keeps each question within 3 attempts
TIMEOUT_S="${SMOKE_TIMEOUT_S:-60}"
PROBE=1

usage() { sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }
die() { echo "smoke: $*" >&2; exit 1; }

for arg in "$@"; do
  case "$arg" in
    --probe) PROBE=1 ;;
    --no-probe) PROBE=0 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $arg (try --help)" ;;
  esac
done

: "${CODEMAS_API_URL:?set CODEMAS_API_URL to the public web URL, e.g. https://codemas-api.up.railway.app}"
: "${SMOKE_USERNAME:?set SMOKE_USERNAME (a student account)}"
: "${SMOKE_PASSWORD:?set SMOKE_PASSWORD}"
export SMOKE_USERNAME SMOKE_PASSWORD
command -v curl >/dev/null || die "curl is required"
command -v python3 >/dev/null || die "python3 is required (JSON handling)"
API="${CODEMAS_API_URL%/}"

TMP="$(umask 077 && mktemp -d "${TMPDIR:-/tmp}/codemas-smoke.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

# ---- programs ---------------------------------------------------------------------------------
cat > "$TMP/solution.py" <<'PY'
import sys

data = sys.stdin.read().split()
n = int(data[0])
arr = [int(x) for x in data[1:1 + n]]
target = int(data[1 + n])
lo, hi, ans = 0, n - 1, -1
while lo <= hi:
    mid = (lo + hi) // 2
    if arr[mid] == target:
        ans = mid
        break
    if arr[mid] < target:
        lo = mid + 1
    else:
        hi = mid - 1
print(ans)
PY

cat > "$TMP/solution.js" <<'JS'
const data = require('fs').readFileSync(0, 'utf8').trim().split(/\s+/).map(Number);
const n = data[0];
const arr = data.slice(1, 1 + n);
const target = data[1 + n];
let lo = 0, hi = n - 1, ans = -1;
while (lo <= hi) {
  const mid = (lo + hi) >> 1;
  if (arr[mid] === target) { ans = mid; break; }
  if (arr[mid] < target) lo = mid + 1; else hi = mid - 1;
}
console.log(ans);
JS

cat > "$TMP/probe.py" <<'PY'
# CodeMas smoke: environment-leak probe. Prints variable NAMES only, never values.
import os

NAMES = {'JOB_SIGNING_SECRET', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN'}
found = []
for pid in sorted((p for p in os.listdir('/proc') if p.isdigit()), key=int):
    try:
        with open('/proc/%s/environ' % pid, 'rb') as f:
            raw = f.read()
    except OSError:
        continue
    for entry in raw.split(b'\0'):
        name = entry.split(b'=', 1)[0].decode('ascii', 'replace')
        if name in NAMES and b'=' in entry:
            found.append('LEAK %s %s' % (pid, name))
print('\n'.join(found) if found else 'NO_LEAK')
PY

cat > "$TMP/egress.py" <<'PY'
# CodeMas smoke: egress probe. Prints only fixed verdict lines: no addresses, paths or values.
import errno
import socket

try:  # how many unix sockets this network namespace can see (a count, never the paths)
    with open('/proc/net/unix') as f:
        print('UNIX_SOCKETS %d' % max(0, len(f.read().splitlines()) - 1))
except OSError:
    print('UNIX_SOCKETS unknown')

# Step 1: may we even create an internet socket? The seccomp filter refuses socket(AF_INET).
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
except OSError as e:  # PermissionError is an OSError with EACCES or EPERM
    print('EGRESS_BLOCKED' if e.errno in (errno.EACCES, errno.EPERM) else 'EGRESS_UNKNOWN %s' % e.errno)
except Exception:
    print('EGRESS_UNKNOWN none')
else:
    # Step 2: the filter is off. Does the network let us out?
    print('EGRESS_FILTER_OFF')
    try:
        s.settimeout(3)
        s.connect(('1.1.1.1', 443))
        print('EGRESS_OPEN')
    except OSError:  # includes the 3 s timeout
        print('EGRESS_NOROUTE')
    finally:
        s.close()
PY

# ---- HTTP helpers -----------------------------------------------------------------------------
# api METHOD PATH [BODY_FILE] -> prints the HTTP status; the body is left in $TMP/resp.
# The bearer token is read from a mode-600 header file, so it never appears in argv.
api() {
  local args=(-sS --max-time 20 -o "$TMP/resp" -w '%{http_code}' -X "$1" -H 'Content-Type: application/json')
  [[ -f "$TMP/auth" ]] && args+=(-H "@$TMP/auth")
  [[ -n "${3:-}" ]] && args+=(--data-binary "@$3")
  curl "${args[@]}" "$API$2" || true   # on a network error -w still prints 000
}
resp_field() {  # resp_field KEY -> value of a top-level key in $TMP/resp ('' if absent)
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); v=d.get(sys.argv[2], "") if isinstance(d, dict) else ""; print("" if v is None else v)' "$TMP/resp" "$1" 2>/dev/null || true
}

# ---- 1. log in --------------------------------------------------------------------------------
python3 -c 'import json,os; print(json.dumps({"username": os.environ["SMOKE_USERNAME"], "password": os.environ["SMOKE_PASSWORD"]}))' > "$TMP/login.json"
code="$(api POST /api/auth/login/ "$TMP/login.json")"
[[ "$code" == 200 ]] || die "login failed: HTTP $code $(resp_field error)"
python3 - "$TMP/resp" "$TMP/auth" <<'PY'
import json, os, sys
d = json.load(open(sys.argv[1]))
fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.write(fd, ('Authorization: Bearer %s\n' % d['access']).encode())
os.close(fd)
role = (d.get('user') or {}).get('role')
if role != 'student':
    sys.exit("smoke: %s is a %r account; use a student (submissions are per student)" % (d['user'].get('username'), role))
PY
echo "smoke: logged in as $SMOKE_USERNAME"

# ---- 2. find the questions --------------------------------------------------------------------
question="${SMOKE_QUESTION_ID:-}"
probe_question="${SMOKE_PROBE_QUESTION_ID:-}"
if [[ -z "$question" || ( "$PROBE" == 1 && -z "$probe_question" ) ]]; then
  code="$(api GET /api/exams/)"
  [[ "$code" == 200 ]] || die "listing exams failed: HTTP $code"
  [[ "$(tr -d '[:space:]' < "$TMP/resp")" != '[]' ]] \
    || die "$SMOKE_USERNAME sees no open exam: it is not enrolled. As the trainer, POST /api/exams/<id>/enrollments/ {\"username\": \"$SMOKE_USERNAME\"} (see deploy/aws/README.md, Smoke test)"
  find_question() {  # find_question TITLE -> id of that question in an open exam ('' if none)
    python3 - "$TMP/resp" "$1" <<'PY'
import json, sys
exams, title = json.load(open(sys.argv[1])), sys.argv[2].lower()
for exam in exams:
    if not exam.get('is_active'):
        continue
    for q in exam.get('questions', []):
        if q.get('title', '').strip().lower() == title:
            print(q['id']); sys.exit()
PY
  }
  [[ -n "$question" ]] || question="$(find_question "$QUESTION_TITLE")"
  [[ -n "$question" ]] || die "no open exam has a question titled '$QUESTION_TITLE' (run seed_data, or set SMOKE_QUESTION_ID)"
  if [[ "$PROBE" == 1 && -z "$probe_question" ]]; then
    probe_question="$(find_question "$PROBE_QUESTION_TITLE")"
    [[ -n "$probe_question" ]] || die "no open exam has a question titled '$PROBE_QUESTION_TITLE' (run seed_data, set SMOKE_PROBE_QUESTION_ID, or use --no-probe)"
  fi
fi
echo "smoke: question $question ($QUESTION_TITLE)"
[[ "$PROBE" == 1 ]] && echo "smoke: probe question $probe_question ($PROBE_QUESTION_TITLE)"

# ---- 3. submit --------------------------------------------------------------------------------
submit() {  # submit QUESTION LANGUAGE FILE -> prints the new submission id
  python3 -c 'import json,sys; print(json.dumps({"question": int(sys.argv[1]), "language": sys.argv[2], "code": open(sys.argv[3]).read()}))' \
    "$1" "$2" "$3" > "$TMP/submit.json"
  local code; code="$(api POST /api/submissions/create/ "$TMP/submit.json")"
  if [[ "$code" != 201 ]]; then
    local err; err="$(resp_field error)"
    [[ "$err" == "Max attempts reached" ]] && err="$err - this student has used its attempts; create a fresh smoke student"
    [[ "$code" == 403 && "$err" == *"not enrolled"* ]] \
      && die "$SMOKE_USERNAME is not enrolled in the exam of question $1. As the trainer, POST /api/exams/<id>/enrollments/ {\"username\": \"$SMOKE_USERNAME\"} first (see deploy/aws/README.md, Smoke test)"
    die "submitting $2 to question $1 failed: HTTP $code ${err:-$(head -c 300 "$TMP/resp")}"
  fi
  resp_field id
}

py_id="$(submit "$question" python "$TMP/solution.py")";   echo "smoke: submitted python       -> submission $py_id"
js_id="$(submit "$question" javascript "$TMP/solution.js")"; echo "smoke: submitted javascript   -> submission $js_id"
probe_id=""; egress_id=""
if [[ "$PROBE" == 1 ]]; then
  probe_id="$(submit "$probe_question" python "$TMP/probe.py")";   echo "smoke: submitted leak probe   -> submission $probe_id"
  egress_id="$(submit "$probe_question" python "$TMP/egress.py")"; echo "smoke: submitted egress probe -> submission $egress_id"
fi

# ---- 4. poll until terminal -------------------------------------------------------------------
ids=("$py_id" "$js_id"); [[ -n "$probe_id" ]] && ids+=("$probe_id" "$egress_id")
declare -a final=()
deadline=$((SECONDS + TIMEOUT_S))
while :; do
  pending=0
  for i in "${!ids[@]}"; do
    [[ -n "${final[$i]:-}" ]] && continue
    code="$(api GET "/api/submissions/${ids[$i]}/status/")"
    if [[ "$code" == 200 && "$(resp_field results_ready)" == True ]]; then
      final[i]="$(resp_field status)"
      echo "smoke: submission ${ids[$i]} -> ${final[$i]}"
    else
      pending=1
    fi
  done
  [[ "$pending" == 0 ]] && break
  if (( SECONDS >= deadline )); then
    for i in "${!ids[@]}"; do
      if [[ -z "${final[$i]:-}" ]]; then
        api GET "/api/submissions/${ids[$i]}/status/" >/dev/null
        echo "smoke: submission ${ids[$i]} not finished after ${TIMEOUT_S}s: $(head -c 300 "$TMP/resp")" >&2
        final[i]="timeout"
      fi
    done
    break
  fi
  sleep 2
done

failed=0
[[ "${final[0]}" == passed ]] || { echo "smoke: FAIL python submission $py_id is '${final[0]}', expected 'passed'" >&2; failed=1; }
[[ "${final[1]}" == passed ]] || { echo "smoke: FAIL javascript submission $js_id is '${final[1]}', expected 'passed'" >&2; failed=1; }

# ---- 5. leak probe verdict --------------------------------------------------------------------
if [[ -n "$probe_id" ]]; then
  code="$(api GET "/api/results/$probe_id/")"
  if [[ "$code" != 200 ]]; then
    echo "smoke: FAIL could not read the leak probe's results: HTTP $code" >&2; failed=1
  else
    # Prints only lines of the exact form "LEAK <pid> <NAME>". Exit: 2 JOB_SIGNING_SECRET found,
    # 4 only AWS_* names found, 0 NO_LEAK, 3 no verdict line at all.
    set +e
    python3 - "$TMP/resp" <<'PY'
import json, re, sys
rows = json.load(open(sys.argv[1]))
line_re = re.compile(r'^LEAK \d+ (JOB_SIGNING_SECRET|AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN)$')
leaks, clean = set(), 0
for r in rows:
    text = '%s\n%s' % (r.get('actual_output') or '', r.get('error_message') or '')
    for line in text.splitlines():
        line = line.strip()
        if line_re.match(line):
            leaks.add(line)
        elif line == 'NO_LEAK':
            clean += 1
for line in sorted(leaks):
    print('smoke:   ' + line)
if any(l.endswith(' JOB_SIGNING_SECRET') for l in leaks):
    sys.exit(2)
sys.exit(4 if leaks else (0 if clean else 3))
PY
    verdict=$?
    set -e
    case "$verdict" in
      0) echo "smoke: leak probe: NO_LEAK (student code could not read the grader's secrets)" ;;
      2) echo "smoke: FAIL !!! LEAK: JOB_SIGNING_SECRET is readable by student code in the Lambda; it must not be there at all. Remove it from the function, rotate it on Railway web and relay, and roll back: railway variable set \"PIPELINE_LANGUAGES=\" -s backend --skip-deploys && railway up -s backend --detach (see Railway deploy rules in deploy/aws/README.md). !!!" >&2; failed=1 ;;
      4) echo "smoke: WARNING leak probe: student code can read the role's AWS credentials (names above). Accepted risk R2 (the role can take, delete and hide codemas-exec messages: student code could claim other students' jobs and forge or delay their grading)." >&2 ;;
      *) echo "smoke: FAIL leak probe inconclusive (status '${final[2]:-?}', no NO_LEAK line in its output)" >&2; failed=1 ;;
    esac
  fi
fi

# ---- 6. egress probe verdict ------------------------------------------------------------------
if [[ -n "$egress_id" ]]; then
  code="$(api GET "/api/results/$egress_id/")"
  if [[ "$code" != 200 ]]; then
    echo "smoke: FAIL could not read the egress probe's results: HTTP $code" >&2; failed=1
  else
    # Considers only lines of the exact probe forms and prints only those (no other output).
    # Exit: 2 EGRESS_OPEN, 5 EGRESS_FILTER_OFF (socket allowed, no route), 4 only UNKNOWN,
    # 0 EGRESS_BLOCKED, 3 no verdict line at all. Only 3 fails the run (R1 is an accepted risk).
    set +e
    python3 - "$TMP/resp" <<'PY'
import json, re, sys
rows = json.load(open(sys.argv[1]))
line_re = re.compile(r'^(EGRESS_BLOCKED|EGRESS_FILTER_OFF|EGRESS_OPEN|EGRESS_NOROUTE'
                     r'|EGRESS_UNKNOWN (-?\d+|None|none)|UNIX_SOCKETS (\d+|unknown))$')
seen = set()
for r in rows:
    for line in (r.get('actual_output') or '').splitlines():
        line = line.strip()
        if line_re.match(line):
            seen.add(line)
for line in sorted(seen):
    print('smoke:   ' + line)
if 'EGRESS_OPEN' in seen:
    sys.exit(2)
if 'EGRESS_FILTER_OFF' in seen:
    sys.exit(5)
if any(l.startswith('EGRESS_UNKNOWN') for l in seen):
    sys.exit(4)
sys.exit(0 if 'EGRESS_BLOCKED' in seen else 3)
PY
    verdict=$?
    set -e
    case "$verdict" in
      0) echo "smoke: egress probe: EGRESS_BLOCKED (student code cannot create internet sockets)" ;;
      2) echo "smoke: WARNING egress probe: EGRESS_OPEN: student code reached 1.1.1.1:443 from the Lambda (seccomp filter not active). Accepted risk R1." >&2 ;;
      5) echo "smoke: WARNING egress probe: EGRESS_FILTER_OFF: student code could create an internet socket (seccomp filter not active; the connect had no route). Accepted risk R1." >&2 ;;
      4) echo "smoke: WARNING egress probe inconclusive (EGRESS_UNKNOWN above): socket() failed for another reason; check the sandbox_selfcheck log line" >&2 ;;
      *) echo "smoke: FAIL egress probe inconclusive (status '${final[3]:-?}', no EGRESS_* line in its output)" >&2; failed=1 ;;
    esac
  fi
fi

# ---- 7. Lambda logs ---------------------------------------------------------------------------
AWS="$(command -v aws || true)"; [[ -z "$AWS" && -x "$HOME/.local/bin/aws" ]] && AWS="$HOME/.local/bin/aws"
if [[ -n "$AWS" ]]; then
  pattern="\"submission_id\": ($(IFS='|'; echo "${ids[*]}"))[,}]"
  echo "smoke: $LOG_GROUP lines for submissions ${ids[*]}:"
  if "$AWS" logs tail "$LOG_GROUP" --since 5m --filter-pattern '?"submission_id" ?"sandbox_selfcheck"' --region "$REGION" \
       --format short > "$TMP/logs" 2> "$TMP/logs.err"; then
    grep -E "$pattern" "$TMP/logs" || echo "smoke:   (none yet; CloudWatch can lag by a few seconds)"
    echo "smoke: sandbox self-checks (one per cold start in the last 5 min):"
    grep -F '"sandbox_selfcheck"' "$TMP/logs" || echo "smoke:   (none: no cold start in the window)"
  else
    echo "smoke: could not read $LOG_GROUP: $(tr -s '\n' ' ' < "$TMP/logs.err" | head -c 300)"
  fi
else
  echo "smoke: aws CLI not found; skipped the CloudWatch log lines"
fi

if [[ "$failed" != 0 ]]; then
  echo "smoke: FAILED" >&2
  exit 1
fi
echo "smoke: OK"
