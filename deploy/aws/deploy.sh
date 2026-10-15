#!/usr/bin/env bash
# Deploy (or update) the CodeMas grading pipeline: stack codemas-pipeline in ap-southeast-1.
#
# Usage:
#   CODEMAS_API_URL=https://<railway-web-host> deploy/aws/deploy.sh   (first deploy and every re-deploy)
#
# Flags:
#   --yes       skip the "Proceed? [y/N]" confirmation
#   --recreate  if the stack is in ROLLBACK_COMPLETE (a failed first create), delete it and create
#               it again. Without this flag the script stops and prints the commands instead.
#
# Env:
#   EXPECTED_ACCOUNT_ID=<12 digits>  refuse to run against any other account (recommended)
#
# Creates or updates: S3 bucket codemas-artifacts-<account>-ap-southeast-1 (if missing), stack
# codemas-pipeline (SQS codemas-exec + codemas-exec-dlq, Lambda codemas-exec + layer codemas-node22,
# its role and log group, a DLQ alarm, IAM user codemas-relay), and, the first time only, an access
# key for codemas-relay written to deploy/aws/.relay-credentials (mode 600, git-ignored).
#
# The Lambda gets no secret: JOB_SIGNING_SECRET lives only on Railway (web and relay), and each SQS
# message carries a per-job token the relay mints. Deploying this template over a stack that still has
# the old JobSigningSecret parameter removes the parameter and the function's variable.
set -euo pipefail

REGION=ap-southeast-1
STACK=codemas-pipeline
RELAY_USER=codemas-relay
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" AWS_PAGER=""

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$ROOT/build"
CREDS="$ROOT/deploy/aws/.relay-credentials"
CREDS_REL="deploy/aws/.relay-credentials"

die() { echo "deploy: $*" >&2; exit 1; }

ASSUME_YES=0
RECREATE=0
for arg in "$@"; do
  case "$arg" in
    --yes|-y) ASSUME_YES=1 ;;
    --recreate) RECREATE=1 ;;
    -h|--help) sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown argument: $arg (try --help)" ;;
  esac
done

AWS="$(command -v aws || true)"; [[ -z "$AWS" && -x "$HOME/.local/bin/aws" ]] && AWS="$HOME/.local/bin/aws"
[[ -n "$AWS" ]] || die "aws CLI v2 not found"
aws() { "$AWS" "$@"; }

# ---- 1. who, where, what state ----------------------------------------------------------------
identity="$(aws sts get-caller-identity --query '[Account,Arn]' --output text)" \
  || die "aws sts get-caller-identity failed: run 'aws configure' with the admin IAM user first"
ACCOUNT="${identity%%$'\t'*}"
CALLER="${identity#*$'\t'}"
if [[ -n "${EXPECTED_ACCOUNT_ID:-}" && "$ACCOUNT" != "$EXPECTED_ACCOUNT_ID" ]]; then
  die "credentials are for account $ACCOUNT, not EXPECTED_ACCOUNT_ID=$EXPECTED_ACCOUNT_ID; stopping"
fi

: "${CODEMAS_API_URL:?set CODEMAS_API_URL to the public Railway web URL (https://...)}"
CODEMAS_API_URL="${CODEMAS_API_URL%/}"
[[ "$CODEMAS_API_URL" =~ ^https://[^[:space:]]+$ ]] || die "CODEMAS_API_URL must be an https:// URL"
[[ "$CODEMAS_API_URL" != *'"'* && "$CODEMAS_API_URL" != *\\* ]] || die "CODEMAS_API_URL contains quotes or backslashes"

if status_out="$(aws cloudformation describe-stacks --stack-name "$STACK" --query 'Stacks[0].StackStatus' --output text 2>&1)"; then
  STACK_STATUS="$status_out"
elif [[ "$status_out" == *"does not exist"* ]]; then
  STACK_STATUS=NONE
else
  die "could not read the stack status: $status_out"
fi

case "$STACK_STATUS" in
  NONE) MODE=create ;;
  ROLLBACK_COMPLETE)
    if [[ "$RECREATE" != 1 ]]; then
      cat >&2 <<EOF
deploy: stack $STACK is in ROLLBACK_COMPLETE (its first create failed; see the Events tab in the
deploy: CloudFormation console for why). It can't be updated, only deleted. Either re-run with
deploy: --recreate, or delete it yourself and re-run:
  aws cloudformation delete-stack --stack-name $STACK --region $REGION
  aws cloudformation wait stack-delete-complete --stack-name $STACK --region $REGION
  sleep 60   # SQS won't reuse a deleted queue's name for about 60 s
EOF
      exit 1
    fi
    MODE=recreate ;;
  REVIEW_IN_PROGRESS) MODE=create ;;   # a failed first change set; the CLI treats it as no stack
  *_IN_PROGRESS) die "stack $STACK is $STACK_STATUS; wait for it to finish and re-run" ;;
  CREATE_COMPLETE|UPDATE_COMPLETE|UPDATE_ROLLBACK_COMPLETE|IMPORT_COMPLETE|IMPORT_ROLLBACK_COMPLETE) MODE=update ;;
  *) die "stack $STACK is $STACK_STATUS; fix it in the CloudFormation console first" ;;
esac
[[ "$RECREATE" == 1 && "$MODE" != recreate ]] && die "--recreate only deletes a stack in ROLLBACK_COMPLETE (this one is $STACK_STATUS)"

# ---- 2. show the plan and confirm -------------------------------------------------------------
BUCKET="codemas-artifacts-${ACCOUNT}-${REGION}"
if aws s3api head-bucket --bucket "$BUCKET" --expected-bucket-owner "$ACCOUNT" >/dev/null 2>&1; then
  BUCKET_ACTION="exists, reuse"
else
  BUCKET_ACTION="CREATE (private, public access blocked)"
fi
VERB=$([[ "$MODE" == update ]] && echo "create or update" || echo "CREATE")
if [[ -f "$CREDS" ]]; then KEY_TEXT="keep: $CREDS_REL exists"; else KEY_TEXT="CREATE one access key for $RELAY_USER -> $CREDS_REL (mode 600)"; fi

RECREATE_TEXT=""
[[ "$MODE" == recreate ]] && RECREATE_TEXT="  - DELETE the failed stack $STACK (ROLLBACK_COMPLETE), wait, then wait 60 s for SQS names
"
cat <<EOF
deploy: account   $ACCOUNT
deploy: caller    $CALLER
deploy: region    $REGION
deploy: stack     $STACK  (now: $STACK_STATUS -> $MODE)
deploy: will do:
  - S3 bucket s3://$BUCKET: $BUCKET_ACTION
  - upload build/exec (handler.py, sandbox.py) and build/node-layer.zip (Node $(sed -n 's/^NODE_VERSION=\([^ ]*\).*/\1/p' "$ROOT/deploy/aws/build.sh")) to it
${RECREATE_TEXT}  - $VERB in stack $STACK:
      SQS queue codemas-exec, SQS queue codemas-exec-dlq, Lambda layer codemas-node22,
      log group /aws/lambda/codemas-exec, IAM role (queue + own-log-group access),
      Lambda function codemas-exec, SQS -> Lambda trigger, CloudWatch alarm codemas-exec-dlq-not-empty,
      IAM user $RELAY_USER (sqs:SendMessage on codemas-exec only)
  - Lambda CODEMAS_API_URL = $CODEMAS_API_URL
  - relay key: $KEY_TEXT
EOF
if [[ "$ASSUME_YES" != 1 ]]; then
  [[ -t 0 ]] || die "not a terminal; re-run with --yes to proceed without the prompt"
  read -r -p "Proceed? [y/N] " answer || answer=""
  [[ "$answer" == y || "$answer" == Y || "$answer" == yes ]] || die "stopped; nothing was changed"
fi

# keep build output and the relay key out of git (idempotent; the repo's .gitignore already has them)
for pattern in /build/ "${CREDS_REL}*"; do
  grep -qxF "$pattern" "$ROOT/.gitignore" || printf '%s\n' "$pattern" >> "$ROOT/.gitignore"
done

# ---- 3. build artifacts (no AWS calls) --------------------------------------------------------
bash "$ROOT/deploy/aws/build.sh"

# ---- 4. a failed first create: delete it (only with --recreate) -------------------------------
if [[ "$MODE" == recreate ]]; then
  echo "deploy: deleting stack $STACK (ROLLBACK_COMPLETE)"
  aws cloudformation delete-stack --stack-name "$STACK"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK"
  echo "deploy: waiting 60 s so SQS can reuse the queue names"
  sleep 60
fi

# ---- 5. artifact bucket -----------------------------------------------------------------------
if [[ "$BUCKET_ACTION" == CREATE* ]]; then
  echo "deploy: creating artifact bucket s3://$BUCKET"
  aws s3api create-bucket --bucket "$BUCKET" --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null
  aws s3api wait bucket-exists --bucket "$BUCKET" --expected-bucket-owner "$ACCOUNT"
fi
aws s3api put-public-access-block --bucket "$BUCKET" --expected-bucket-owner "$ACCOUNT" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# ---- 6. package: upload build/exec (zipped) and build/node-layer.zip ---------------------------
aws cloudformation package --template-file "$ROOT/deploy/aws/pipeline.yaml" --s3-bucket "$BUCKET" \
  --s3-prefix "$STACK" --output-template-file "$BUILD/packaged.yaml" >/dev/null
echo "deploy: packaged -> build/packaged.yaml"

# ---- 7. deploy --------------------------------------------------------------------------------
echo "deploy: deploying stack $STACK (a first create takes a few minutes)"
aws cloudformation deploy --stack-name "$STACK" --template-file "$BUILD/packaged.yaml" \
  --capabilities CAPABILITY_NAMED_IAM --no-fail-on-empty-changeset \
  --parameter-overrides "CodemasApiUrl=$CODEMAS_API_URL" \
  --tags project=codemas component=grading-pipeline

# ---- 8. outputs and the relay key -------------------------------------------------------------
echo "deploy: stack outputs"
aws cloudformation describe-stacks --stack-name "$STACK" \
  --query 'Stacks[0].Outputs[].[OutputKey,OutputValue]' --output table
QUEUE_URL="$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='QueueUrl'].OutputValue" --output text)"

if [[ -f "$CREDS" ]]; then
  echo "deploy: $CREDS_REL already exists; not creating another access key"
else
  keys="$(aws iam list-access-keys --user-name "$RELAY_USER" --query 'length(AccessKeyMetadata)' --output text)"
  if (( keys >= 2 )); then
    die "$RELAY_USER already has 2 access keys (the IAM maximum). Delete the unused one(s) with 'aws iam delete-access-key --user-name $RELAY_USER --access-key-id <id>' and re-run."
  fi
  (( keys == 0 )) || echo "deploy: note: $RELAY_USER already has $keys access key; adding a second (delete the old one once Railway uses the new one)"
  git -C "$ROOT" check-ignore -q "$CREDS_REL" || die "$CREDS_REL is not git-ignored; refusing to write a secret there"

  # The key goes straight from the CLI into shell variables; no temp file anywhere.
  key_id="" key_secret=""
  read -r key_id key_secret < <(aws iam create-access-key --user-name "$RELAY_USER" \
    --query '[AccessKey.AccessKeyId,AccessKey.SecretAccessKey]' --output text) || true
  if [[ -z "$key_id" ]]; then
    die "create-access-key returned nothing. Check 'aws iam list-access-keys --user-name $RELAY_USER' and delete any key you can't account for."
  fi
  cleanup_hint="aws iam delete-access-key --user-name $RELAY_USER --access-key-id $key_id --region $REGION"
  [[ -n "$key_secret" ]] || die "create-access-key returned no secret. Delete the key: $cleanup_hint"
  if ! (
    umask 077
    {
      echo "# codemas-relay: environment for the Railway relay service. Never commit or share this file."
      echo "JOB_TRANSPORT=sqs"
      echo "JOB_QUEUE_URL=$QUEUE_URL"
      echo "AWS_REGION=$REGION"
      echo "AWS_ACCESS_KEY_ID=$key_id"
      echo "AWS_SECRET_ACCESS_KEY=$key_secret"
    } > "$CREDS" && chmod 600 "$CREDS"
  ); then
    unset key_secret
    rm -f "$CREDS"
    die "could not write $CREDS_REL. The key exists but its secret is lost; delete it with: $cleanup_hint"
  fi
  unset key_secret
  echo "deploy: relay access key $key_id written to $CREDS_REL (mode 600). Paste its values into Railway yourself."
fi

echo "deploy: done. Next: the 'After deploy (Task 9)' section of deploy/aws/README.md, then deploy/aws/smoke.sh"
