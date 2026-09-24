#!/usr/bin/env bash
# purpose: Check that release manifest mismatches name the affected file.
# adr: ADR-0622
# maintainer: HybridOps.Tech

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/common.sh"
# shellcheck source=/dev/null
source "${HYOPS_REPO_ROOT}/pkg/lib/common.sh"

hyops_ci::require_cmd python3
hyops_ci::require_cmd mktemp

WORK_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${WORK_DIR}"
}
trap cleanup EXIT

write_checksum_manifest() {
  local root="$1"
  python3 - "${root}" <<'PY'
from hashlib import sha256
from pathlib import Path
import sys

root = Path(sys.argv[1])
manifest = root / "pkg" / "release-files.sha256"
lines = []
for path in sorted(item for item in root.rglob("*") if item.is_file() and item != manifest):
    digest = sha256(path.read_bytes()).hexdigest()
    lines.append(f"{digest}  {path.relative_to(root).as_posix()}")
manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

expect_failure() {
  local root="$1"
  local needle="$2"
  local output=""
  local status=0

  set +e
  output="$(hyops_release_verify_checksum_manifest "${root}" "fixture" 2>&1)"
  status=$?
  set -e
  if [[ "${status}" -eq 0 ]]; then
    echo "ERR: fixture accepted a manifest mismatch (${needle})" >&2
    exit 1
  fi
  if ! grep -F "${needle}" <<<"${output}" >/dev/null; then
    echo "ERR: fixture mismatch did not name ${needle}" >&2
    printf '%s\n' "${output}" >&2
    exit 1
  fi
}

VALID_ROOT="${WORK_DIR}/valid"
mkdir -p "${VALID_ROOT}/pkg"
printf 'kept\n' >"${VALID_ROOT}/kept.txt"
write_checksum_manifest "${VALID_ROOT}"
hyops_release_verify_checksum_manifest "${VALID_ROOT}" "fixture"

MISSING_ROOT="${WORK_DIR}/missing"
mkdir -p "${MISSING_ROOT}/pkg"
cp "${VALID_ROOT}/kept.txt" "${MISSING_ROOT}/kept.txt"
write_checksum_manifest "${MISSING_ROOT}"
rm -f "${MISSING_ROOT}/kept.txt"
expect_failure "${MISSING_ROOT}" "missing: kept.txt"

UNEXPECTED_ROOT="${WORK_DIR}/unexpected"
mkdir -p "${UNEXPECTED_ROOT}/pkg"
printf 'kept\n' >"${UNEXPECTED_ROOT}/kept.txt"
write_checksum_manifest "${UNEXPECTED_ROOT}"
printf 'extra\n' >"${UNEXPECTED_ROOT}/extra.txt"
expect_failure "${UNEXPECTED_ROOT}" "unexpected: extra.txt"

MISMATCH_ROOT="${WORK_DIR}/mismatch"
mkdir -p "${MISMATCH_ROOT}/pkg"
printf 'kept\n' >"${MISMATCH_ROOT}/kept.txt"
write_checksum_manifest "${MISMATCH_ROOT}"
printf 'changed\n' >"${MISMATCH_ROOT}/kept.txt"
expect_failure "${MISMATCH_ROOT}" "mismatch: kept.txt"
