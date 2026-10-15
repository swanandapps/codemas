# CodeMas grading pipeline on AWS

One SQS queue, one dead-letter queue and one Lambda function grade Python and JavaScript
submissions. Django on Railway keeps the database. The Lambda holds no database credentials, no
shared secret and no expected outputs, and uses no third-party packages: it claims a job, runs the
tests and reports the outputs over HTTPS. Django compares them with the expected outputs.

Each SQS message carries a **per-job token** that the relay mints:
`HMAC-SHA256(JOB_SIGNING_SECRET, "job:" + job_id)`. The Lambda sends it back on claim, complete and
fail, and Django recomputes it. `JOB_SIGNING_SECRET` lives only on Railway (web and relay). Design
and accepted risks: `docs/superpowers/specs/2026-10-04-lambda-guardrails.md`.

> **Status: live since 2026-10-05.** Python and JavaScript grade through outbox → relay (Railway)
> → SQS `codemas-exec` → Lambda `codemas-exec` (arm64, ap-southeast-1), switched on by
> `PIPELINE_LANGUAGES=python,javascript` on Railway backend. C++ and Java stay on Celery. The
> go-live smoke test graded Python and JS through the pipeline and found no `JOB_SIGNING_SECRET`;
> it still shows R2 (role credentials readable) and R1 (egress open), both accepted (see below).
>
> **Before changing any Railway variable, read [Railway deploy rules](#railway-deploy-rules).**
> A plain variable change silently reverts production to old code.

```
Django web ──outbox row──▶ relay (Railway, run_relay) ──SendMessageBatch──▶ SQS codemas-exec
                                                                              │ batch of 1
Django web ◀──claim / complete / fail (HTTPS + job token)─ Lambda codemas-exec ◀──┘
                                                       (python3.12 + /opt/bin/node layer)
                       after 3 failed receives ──▶ SQS codemas-exec-dlq (kept 14 days)
```

| File | What it does |
|---|---|
| `pipeline.yaml` | CloudFormation for stack `codemas-pipeline`. It defines the queue, the DLQ, the Lambda and its Node layer, role and log group, the SQS trigger, and the IAM user `codemas-relay` |
| `build.sh` | Builds `build/exec/` (holding only `handler.py` and `sandbox.py`) and `build/node-layer.zip` (holding only `bin/node`, from Node 22.23.3 LTS after its SHA256 is checked). It makes no AWS calls |
| `deploy.sh` | Builds, uploads, deploys, prints the stack outputs, and writes the relay access key the first time it runs |
| `smoke.sh` | End-to-end test through the public API: a correct Python submission, a correct JavaScript submission, and probes for an environment leak and for network egress |

## One-time AWS setup

1. Create the AWS account. Enable **MFA on the root user**, then stop using root.
2. Billing → Budgets → create a **zero-spend budget**, or a monthly budget of $5, with an email
   alert.
3. IAM → create **an admin IAM user (this project uses `codemas`)** with `AdministratorAccess` and
   MFA, plus an access key for the CLI.
4. `aws configure` (CLI v2) with that key, region `ap-southeast-1`.
   Check it with `aws sts get-caller-identity`.

## Deploy

Keep secrets out of your shell history: never type a secret on a command line.

```bash
export EXPECTED_ACCOUNT_ID=657661911207
CODEMAS_API_URL=https://<your-railway-web-host> deploy/aws/deploy.sh
```

- **Confirmation.** The script prints the account, the caller ARN, the region, the stack's current
  state and everything it will create or update, then asks `Proceed? [y/N]`. Nothing is created
  before you answer `y`. `--yes` skips the prompt.
- **Wrong account.** If `EXPECTED_ACCOUNT_ID` is set and doesn't match the credentials, it stops.
- **`CODEMAS_API_URL`** is the URL that the **Lambda** calls: the public https URL of Railway web.
- **No secret goes to AWS.** The template has no secret parameter and the function no secret
  variable. Deploying it over a stack created before 2026-10-04 removes the old `JobSigningSecret`
  parameter and the function's `JOB_SIGNING_SECRET` variable.
- **Relay key.** The first run writes `deploy/aws/.relay-credentials` (mode 600, git-ignored). It
  contains the `codemas-relay` access key and the queue URL. Later runs keep that file and create
  no new key. The key goes straight from the CLI into that file; no temp copy is written. If the
  write fails, the script prints the `aws iam delete-access-key` command for the orphaned key.
- **Re-running is safe.** An unchanged stack is a no-op, and the layer zip is byte-identical, so it
  is not uploaded again.
- **A failed first create.** The stack is left in `ROLLBACK_COMPLETE` and can't be updated. The
  script stops and prints the `delete-stack` and `wait stack-delete-complete` commands. Or run it
  with `--recreate`, which deletes that failed stack itself. `--recreate` never deletes a healthy
  stack.
- **Queue names.** After a queue is deleted, SQS needs **about 60 s** before the same queue name can
  be created again. Wait that long after a delete before re-deploying. `--recreate` waits for you.

What a deploy creates in `ap-southeast-1`:

| Resource | Name | Notes |
|---|---|---|
| S3 bucket | `codemas-artifacts-<account>-ap-southeast-1` | Created by `deploy.sh`, outside the stack, with public access blocked. Holds the uploaded code zip and layer zip |
| SQS queue | `codemas-exec` | Visibility timeout 540 s. After 3 receives a message goes to the DLQ. SSE (SQS-managed keys) |
| SQS queue | `codemas-exec-dlq` | Messages are kept 14 days. SSE (SQS-managed keys) |
| Lambda layer | `codemas-node22` | `/opt/bin/node`, Node v22.23.3 (LTS), linux-arm64 |
| Lambda function | `codemas-exec` | python3.12 on **arm64 (Graviton)**, 1024 MB, 90 s timeout, handler `handler.handler`. Environment: `CODEMAS_API_URL` and `PATH` only. The sandbox's seccomp egress filter is proven natively on arm64 in Docker, but **real Lambda refuses it** (`egress_blocked=false`): see accepted risk R1 below. |
| Event source mapping | SQS → `codemas-exec` | Batch size 1, `ReportBatchItemFailures`, maximum concurrency 5 |
| Log group | `/aws/lambda/codemas-exec` | Kept 14 days |
| IAM role | generated name | Exactly: `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` and `sqs:ChangeMessageVisibility` on `codemas-exec` only; `logs:CreateLogStream` and `logs:PutLogEvents` on `/aws/lambda/codemas-exec` only. It has no `logs:CreateLogGroup` and no managed policies |
| CloudWatch alarm | `codemas-exec-dlq-not-empty` | `ApproximateNumberOfMessagesVisible` > 0 on the DLQ (5-minute maximum). It has no SNS action and is only a console indicator. It fits within the free 10 alarms |
| IAM user | `codemas-relay` | `sqs:SendMessage` on `codemas-exec` only (this also authorizes `SendMessageBatch`). Has one access key |

## Railway deploy rules

> **Railway is CLI-upload only.** On 2026-10-05 the four services (backend, worker, frontend,
> relay) were disconnected from GitHub; `railway up` from the repo root is the only way code
> reaches production. Before that, they were connected to branch `feature/ai-features` (head
> `902417d`, the old pre-pipeline code), and a variable change without `--skip-deploys` deployed
> that commit and silently reverted production — twice. Now a variable change just restarts the
> last upload; the rules below still apply so code and variables go live together.

The only safe procedure for **any** variable change, run from the repo root:

```bash
railway variable set KEY=VALUE -s <service> --skip-deploys
railway up -s <service> --detach
```

- **No `--path-as-root`.** The services use root directory `/backend` or `/frontend`, so upload the
  repo root.
- **No `railway redeploy`**, and no dashboard Deploy/Redeploy button. Redeploy reuses the previous
  deployment's config, so a pre-deploy command or variable added later doesn't take effect.
- **Check what is live:** `railway deployment list -s <svc> --json`. The active deployment's `meta`
  must have `cliMessage` set, not `commitHash`. A `commitHash` would mean someone reconnected GitHub and old code is live.

**Rollback** (Python and JS back to Celery, no code change):

```bash
railway variable set "PIPELINE_LANGUAGES=" -s backend --skip-deploys && railway up -s backend --detach
```

Set it to empty; **never delete the variable**. Unset, it defaults to `python,javascript`.

## After deploy (Task 9, done 2026-10-05): Railway

> This is the go-live record. Every variable change below must now follow
> [Railway deploy rules](#railway-deploy-rules).

> **Hazard: do step 0 before this branch reaches Railway.** The Railway image is built from
> `backend/` and does **not** contain `lambda/exec`. `PIPELINE_LANGUAGES` defaults to
> `python,javascript`. Without the relay running on `JOB_TRANSPORT=sqs`, Python and JS
> submissions sit `pending` in production. And with `DEBUG` off, a missing, default or short
> (< 32 characters) `JOB_SIGNING_SECRET` fails system check `jobs.E001`: `migrate` refuses to run,
> so the web deploy never reaches gunicorn (`run_relay` refuses too).

0. **Before pushing this branch**, on Railway **web**:
   - Set `JOB_SIGNING_SECRET`: generate it with `openssl rand -hex 32` and keep it in your password
     manager. Only Railway web and the relay get it; the Lambda never does.
   - Set `PIPELINE_LANGUAGES=` (empty). Every language then stays on the existing Celery path.
   - Check `DEBUG` is unset or not `True`.

   Migration `submissions.0008` adds a unique `(student, question, attempt_number)` constraint. It
   first renumbers any duplicate attempts left by the old unlocked create view (by submission time,
   only in the affected student/question groups), so it can't fail `migrate` on existing data.
1. Run `deploy/aws/deploy.sh`, as described above.
2. Set `CODEMAS_API_URL` on Railway **web**: the web's own public https URL, the one the Lambda
   uses. (`JOB_SIGNING_SECRET` is already set from step 0.)
3. Create a Railway **relay** service from the same repo and image:
   - Root directory `backend` (the same Dockerfile as web).
   - Start command: `python manage.py run_relay`. It overrides the image's `CMD`, so the relay never
     runs `migrate` or gunicorn.
   - No public domain. One replica is enough (more are safe: the relay uses `SKIP LOCKED`).
   - Database and `SECRET_KEY` variables: the same as web, because the relay reads the outbox.
   - Paste these values from `deploy/aws/.relay-credentials`: `JOB_TRANSPORT=sqs` (required: with
     the default `local` the relay crash-loops, because the image has no `lambda/exec`),
     `JOB_QUEUE_URL`, `AWS_REGION`, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.
   - Also set `JOB_SIGNING_SECRET` and `CODEMAS_API_URL`, with the same values as web (set the secret as
     the reference `${{backend.JOB_SIGNING_SECRET}}`, not a pasted copy). The relay
     needs the secret to mint each message's job token (and `run_relay` runs the same `jobs.E001`
     check). A relay with a different value than web makes every claim fail with 401.
4. Flip the switch only when everything else is green. While `PIPELINE_LANGUAGES` is empty,
   nothing reaches SQS, so the smoke test can only run after the flip:
   - Make sure the stack is deployed and the relay service is running. Its logs show
     `relay: transport=sqs`.
   - Set `PIPELINE_LANGUAGES=python,javascript` on web (with `--skip-deploys`, then `railway up`).
   - Run `smoke.sh` straight away.
   - If the smoke test fails, run the [rollback](#railway-deploy-rules) (empty, never deleted, with
     `--skip-deploys` then `railway up`). Jobs already in the outbox or SQS stay there and are
     graded once the pipeline works.

## Smoke test

**Enroll the throwaway student in the open exam first.** Students only see and submit to exams
they are enrolled in, so a fresh student sees no open exam and every submit is refused with
`403 {"error": "You're not enrolled in this exam."}`. As the trainer, use the enrollment endpoint
(`<exam-id>` is the open exam's id, from `GET /api/exams/` as the trainer):

```bash
read -rs TRAINER_TOKEN; export TRAINER_TOKEN       # paste the trainer's access token (from POST /api/auth/login/)
curl -sS -X POST "https://<your-railway-web-host>/api/exams/<exam-id>/enrollments/" \
  -H @<(printf 'Authorization: Bearer %s\n' "$TRAINER_TOKEN") -H 'Content-Type: application/json' \
  -d '{"username": "<the throwaway student>"}'      # expect 201 {"enrolled": "<the throwaway student>"}
unset TRAINER_TOKEN
```

Then run the smoke test as that student:

```bash
read -rs SMOKE_PASSWORD; export SMOKE_PASSWORD     # type the password; it is not echoed or kept in history
CODEMAS_API_URL=https://<your-railway-web-host> SMOKE_USERNAME=<a throwaway student> \
  deploy/aws/smoke.sh            # --no-probe skips the environment-leak and egress probes
unset SMOKE_PASSWORD
```

- **Needs the current seed.** Prod data is still the old seed (open exam "CodeMas Live Demo —
  Always Open"), so the question lookups below fail until the owner re-seeds: see "Re-seed" in
  `docs/demo-runbook.md`. The open exam must be "Python Binary Search Exam".
- It logs in as a **student** and finds "Find Target in Sorted Array" in the open exam. It submits a
  correct Python solution and a correct JavaScript solution, and fails unless both end `passed`
  within 60 s (`SMOKE_TIMEOUT_S`).
- **The 60 s window only covers success on the first try.** If the first delivery hits an
  infrastructure failure, for example a Lambda crash or timeout, SQS re-delivers only after the
  540 s visibility timeout. A grader error goes through `/fail/` and is republished at once. So a
  smoke timeout means "check the logs", not necessarily "broken".
- **The leak probe (`--probe`, on by default)** submits a Python program that reads every
  `/proc/<pid>/environ` it can open. For each of `JOB_SIGNING_SECRET`, `AWS_SECRET_ACCESS_KEY` and
  `AWS_SESSION_TOKEN` that it finds, it prints only `LEAK <pid> <NAME>`. If it finds none, it prints
  `NO_LEAK`. It never prints values. That submission is graded `failed` (expected). The script
  **fails loudly if `JOB_SIGNING_SECRET` is found** (the Lambda must not have it), **warns on the
  `AWS_*` names** (accepted risk R2), and fails when the output has neither a `LEAK` nor a
  `NO_LEAK` line.
- **The egress probe (also behind `--probe`)** submits a Python program that works in two steps:
  1. It creates `socket.socket(AF_INET)`. A refusal with EACCES/EPERM (the sandbox's seccomp
     filter) prints `EGRESS_BLOCKED`.
  2. If the socket was created, the filter is off. It prints `EGRESS_FILTER_OFF`, then tries
     `connect(('1.1.1.1', 443))` with a 3 s timeout and prints `EGRESS_OPEN` or `EGRESS_NOROUTE`.

  Any other failure prints `EGRESS_UNKNOWN <errno>`. The probe also prints `UNIX_SOCKETS <n>`: the
  number of entries in `/proc/net/unix`, a count with no paths.

  The script reads only lines of those exact forms. It **warns on `EGRESS_FILTER_OFF`,
  `EGRESS_OPEN` and `EGRESS_UNKNOWN`** (accepted risk R1), and fails if there is no verdict line at
  all. It also prints the Lambda's `{"event": "sandbox_selfcheck", "egress_blocked": …}` lines,
  logged once per cold start.
- The two probes go to the open exam's other question, "Find First and Last Position"
  (`SMOKE_PROBE_QUESTION_ID` skips the lookup). Each submission **spends one attempt** of the smoke
  student on its question: 2 on each question, within the default allowance of 3. A re-run would
  need a 3rd and 4th attempt on the same questions, so it needs a fresh student. A trainer can
  create one under Account management, then must enroll it in the open exam (above): the script
  stops with "not enrolled" otherwise. **Never use the demo student**: the probe submissions stay
  on the open exam graded `failed`, show up in trainer dashboards and feed plagiarism when the exam
  closes.
- Finally it prints the `codemas-exec` CloudWatch lines for those submission ids. This needs the
  `aws` CLI.

If `JOB_SIGNING_SECRET` is reported: run the [rollback](#railway-deploy-rules), check the function's
environment (Configuration → Environment variables must list only `CODEMAS_API_URL` and `PATH`;
re-run `deploy.sh`), rotate `JOB_SIGNING_SECRET` on Railway web and relay, and investigate before
re-enabling.

### Accepted risks (owner decision, 2026-10-04)

The first production smoke test showed that real Lambda refuses the seccomp filter and exposes the
runtime's environment to student code. With one function, two things stay possible and are
**accepted, not fixed**:

- **R1, egress.** Student code can open internet connections from the Lambda (`EGRESS_OPEN`).
  Abuse is bounded by CPU time per test, maximum concurrency 5, 3 attempts per question and the
  submission throttle.
- **R2, role credentials.** Lambda always injects the role's credentials, and student code can read
  them. The trigger role can `sqs:ReceiveMessage`, `sqs:DeleteMessage` and
  `sqs:ChangeMessageVisibility` on `codemas-exec`. So a determined student with a working solution
  could take a classmate's queued message (job id and token), claim that job first, read the
  classmate's code and test inputs, and post outputs that forge a pass or a fail. The classmate's
  real delivery then gets 409 `done`, so nothing looks wrong. They can also delete or hide queued
  messages, delaying other students' grading until the 30-minute sweep. Exposure is highest under an
  exam-deadline backlog (concurrency 5), when every queued message waits longest.

What the guardrails do guarantee: the signing secret and the expected outputs never enter the
Lambda, and a student can't pass their own submission without correct output. The real fix for R1
and R2 is **future work**: the two-function split, the standard pattern for online judges. A runner
Lambda with a zero-permission role, in a VPC with no NAT or internet gateway and a security group
with no outbound rules, is invoked by the grader, which reads its return value.

**After the 2026-10-04 smoke test** the old `JOB_SIGNING_SECRET` was readable by student code in the
Lambda. It was rotated at the 2026-10-05 cutover, and the go-live probe found no secret.

### Rotating `JOB_SIGNING_SECRET` (cutover)

- **Never run the new backend code with the old secret.** With per-job tokens, the old (exposed)
  secret plus any job id mints a valid token. Ship the new secret in the same deploy as the new code.
- The relay must use the reference `${{backend.JOB_SIGNING_SECRET}}`, not a pasted value.
- Railway resolves a reference when a deployment is created, so **deploy the relay explicitly**
  after changing web's secret: `railway up -s relay --detach` (not `railway redeploy`; see
  [Railway deploy rules](#railway-deploy-rules)).
- A mismatch shows as `"claim": 401` in the Lambda logs (and the DLQ alarm); jobs recover through the
  sweep once the relay holds the same secret as web.

## Operating it

- Logs: `aws logs tail /aws/lambda/codemas-exec --follow --region ap-southeast-1`
- DLQ at a glance: CloudWatch → Alarms → `codemas-exec-dlq-not-empty`. In alarm means the DLQ is
  not empty.
- DLQ depth:
  `aws sqs get-queue-attributes --queue-url <DlqUrl> --attribute-names ApproximateNumberOfMessages --region ap-southeast-1`.
  A message reaches the DLQ only after Lambda failed it 3 times, for example because Django was
  unreachable or the job token was refused (401: web and relay hold different secrets). The Django side has its own retry/dead accounting.
- Rotate the relay key:
  - `aws iam create-access-key --user-name codemas-relay`
  - Update Railway with the new key (relay; `--skip-deploys`, then `railway up -s relay --detach`).
  - `aws iam delete-access-key --user-name codemas-relay --access-key-id <old>`
  - Update `deploy/aws/.relay-credentials`.
- Rotate `JOB_SIGNING_SECRET`: on Railway only, web and relay together (order and checks under
  "Rotating `JOB_SIGNING_SECRET`" above); no AWS change. Messages
  already queued carry tokens from the old secret and get 401 until they reach the DLQ; the relay's
  sweep republishes those jobs with fresh tokens after 30 minutes.

## Teardown

```bash
aws iam list-access-keys --user-name codemas-relay --region ap-southeast-1   # delete each key first:
aws iam delete-access-key --user-name codemas-relay --access-key-id <id>
aws cloudformation delete-stack --stack-name codemas-pipeline --region ap-southeast-1
aws cloudformation wait stack-delete-complete --stack-name codemas-pipeline --region ap-southeast-1
aws s3 rb s3://codemas-artifacts-657661911207-ap-southeast-1 --force      # not in the stack: by hand
rm deploy/aws/.relay-credentials
```

Notes:
- Run the [rollback](#railway-deploy-rules) on Railway backend first, and stop the relay.
- **Log group:** the stack deletes `/aws/lambda/codemas-exec`. An invocation still running during
  the delete can leave it behind, outside the stack and with no retention. The role has no
  `logs:CreateLogGroup`, so this should be rare. If
  `aws logs describe-log-groups --log-group-name-prefix /aws/lambda/codemas-exec` still lists it,
  delete it by hand: `aws logs delete-log-group --log-group-name /aws/lambda/codemas-exec`.
- **Queue names:** wait about 60 s after the delete before creating the stack again, so SQS can
  reuse the names.
- **S3 artifact bucket:** it is not part of the stack, so delete it by hand (the `s3 rb` line
  above).

## Cost

At demo scale the cost is about **$0/month**:

- **Lambda:** 1M requests and 400,000 GB-seconds are always free. A thousand 2-second gradings at
  1 GB use about 2,000 GB-s.
- **arm64 (Graviton)** is about 20% cheaper per GB-second than x86_64, past the free tier. It was
  chosen because the egress filter is proven natively there.
- **SQS:** 1M requests a month are always free. The idle trigger long-polls the queue, with at most
  about 650k empty receives a month at 5 pollers.
- **CloudWatch Logs:** 5 GB a month free, and the logs are kept only 14 days.
- **CloudWatch alarm:** the one DLQ alarm is within the 10 free alarms.
- **Lambda environment encryption:** uses the AWS-managed KMS key, which is free (only
  `CODEMAS_API_URL` and `PATH` are stored).
- **IAM and CloudFormation:** free.
- **S3:** the artifacts are about 44 MB, which is under 1 cent a month.
