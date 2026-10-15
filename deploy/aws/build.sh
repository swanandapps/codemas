#!/usr/bin/env bash
# Build the two Lambda artifacts that deploy/aws/pipeline.yaml points at. Makes no AWS calls.
#
#   build/exec/            handler.py + sandbox.py only (no tests, Dockerfile.test, __pycache__)
#   build/node-layer.zip   bin/node from the pinned Node.js Linux arm64 release (-> /opt/bin/node)
#
# The function runs on arm64 (Graviton): the architecture the sandbox's seccomp egress filter
# is proven on natively.
#
# The Node tarball is checked against the SHA256 pinned below AND against nodejs.org's
# SHASUMS256.txt for that release; either mismatch aborts. It is cached in build/.
set -euo pipefail

NODE_VERSION=v22.23.3   # current Node 22 LTS ("Jod")
NODE_SHA256=a44aeb94849a299b22df10b9e622ec2f605c2183501bc40590705131de7c740f   # node-v22.23.3-linux-arm64.tar.xz
NODE_DIST="node-${NODE_VERSION}-linux-arm64"
LAMBDA_GLIBC_MINOR=34   # the python3.12 runtime is Amazon Linux 2023: glibc 2.34
NODE_URL="https://nodejs.org/dist/${NODE_VERSION}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$ROOT/lambda/exec"
BUILD="$ROOT/build"
FIXED_MTIME=202001010000   # fixed timestamps -> byte-identical zips -> no re-upload when unchanged

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

mkdir -p "$BUILD"

# 1. function code: an explicit allowlist, so nothing else in lambda/exec/ can reach Lambda
rm -rf "$BUILD/exec"
mkdir -p "$BUILD/exec"
cp "$SRC/handler.py" "$SRC/sandbox.py" "$BUILD/exec/"
chmod 644 "$BUILD/exec/"*.py
touch -t "$FIXED_MTIME" "$BUILD/exec" "$BUILD/exec/"*.py
echo "build: build/exec/ -> $(cd "$BUILD/exec" && echo *)"

# 2. Node layer
tarball="$BUILD/${NODE_DIST}.tar.xz"
if [[ ! -f "$tarball" || "$(sha256 "$tarball")" != "$NODE_SHA256" ]]; then
  echo "build: downloading ${NODE_DIST}.tar.xz from nodejs.org"
  curl -fsSL --retry 3 -o "$tarball.part" "$NODE_URL/${NODE_DIST}.tar.xz"
  mv "$tarball.part" "$tarball"
fi
published="$(curl -fsSL --retry 3 "$NODE_URL/SHASUMS256.txt" | awk -v f="${NODE_DIST}.tar.xz" '$2 == f {print $1}')"
actual="$(sha256 "$tarball")"
if [[ "$published" != "$NODE_SHA256" ]]; then
  echo "build: SHASUMS256.txt lists '${published:-nothing}' for ${NODE_DIST}.tar.xz, expected the pinned $NODE_SHA256" >&2
  exit 1
fi
if [[ "$actual" != "$NODE_SHA256" ]]; then
  rm -f "$tarball"
  echo "build: ${NODE_DIST}.tar.xz SHA256 is $actual, expected $NODE_SHA256 (deleted it)" >&2
  exit 1
fi
echo "build: ${NODE_DIST}.tar.xz SHA256 verified (pinned + SHASUMS256.txt)"

rm -rf "$BUILD/layer" "$BUILD/node-layer.zip"
mkdir -p "$BUILD/layer/bin"
tar -xJf "$tarball" -C "$BUILD/layer/bin" --strip-components 2 "${NODE_DIST}/bin/node"
chmod 755 "$BUILD/layer/bin/node"
# glibc check: the newest GLIBC_2.x symbol version the binary needs must exist on Lambda
# (the official arm64 build needs 2.28; Amazon Linux 2023 has 2.34).
need="$(LC_ALL=C grep -aoE 'GLIBC_2\.[0-9]+' "$BUILD/layer/bin/node" | cut -d. -f2 | sort -n | tail -1)"
[[ -n "$need" ]] || { echo "build: could not read the glibc versions bin/node needs" >&2; exit 1; }
if (( need > LAMBDA_GLIBC_MINOR )); then
  echo "build: bin/node needs glibc 2.$need; Lambda python3.12 (AL2023) has 2.$LAMBDA_GLIBC_MINOR" >&2
  exit 1
fi
echo "build: bin/node needs glibc >= 2.$need (Lambda has 2.$LAMBDA_GLIBC_MINOR)"
touch -t "$FIXED_MTIME" "$BUILD/layer/bin" "$BUILD/layer/bin/node"
(cd "$BUILD/layer" && zip -X -q -r "$BUILD/node-layer.zip" bin)
echo "build: build/node-layer.zip -> bin/node ($(du -h "$BUILD/node-layer.zip" | cut -f1 | tr -d ' '))"
