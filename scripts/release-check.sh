#!/usr/bin/env bash
# Run the release gate in the builder container and summarize the evidence.
#
#   iso -> verify -> qemu-boot -> qemu-smoke   (stops at the first failure)
#
# Each step's full output goes to <out>/<step>.log.  <out>/summary.txt holds
# what an acceptance-registry row needs -- commit, ISO SHA-256, per-step
# outcome, and the QEMU assessors' PASS/FAIL counts -- so rows are copied
# from measured output instead of being retyped.
# Usage: CONTAINER_ENGINE=docker|podman ./scripts/release-check.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
OUT_DIR="${SUSHIDA_RELEASE_CHECK_DIR:-$PROJECT_ROOT/build/release-check}"
STEPS=(iso verify qemu-boot qemu-smoke)

[ ! -L "$OUT_DIR" ] || { echo "ERROR: refusing symlinked output dir: $OUT_DIR" >&2; exit 1; }
mkdir -p "$OUT_DIR"
SUMMARY="$OUT_DIR/summary.txt"

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
head_at_start="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
lines=()
overall=PASS

for step in "${STEPS[@]}"; do
    if [ "$overall" = FAIL ]; then
        lines+=("step $step=SKIPPED")
        continue
    fi
    log="$OUT_DIR/$step.log"
    echo "==> $step (log: $log)"
    status=0
    "$SCRIPT_DIR/container-run.sh" "$step" > "$log" 2>&1 || status=$?
    outcome=PASS
    detail="exit $status"
    [ "$status" -eq 0 ] || outcome=FAIL
    case "$step" in
        qemu-*)
            # An assessor that printed nothing proves nothing: require at
            # least one PASS and no FAIL in addition to exit status 0.
            passed="$(grep -c '^AUTOMATED: .*: PASS$' "$log" || true)"
            failed="$(grep -c '^AUTOMATED: .*: FAIL' "$log" || true)"
            detail="$detail, AUTOMATED $passed PASS / $failed FAIL"
            if [ "$passed" -eq 0 ] || [ "$failed" -ne 0 ]; then
                outcome=FAIL
            fi
            ;;
    esac
    lines+=("step $step=$outcome ($detail)")
    echo "    $outcome ($detail)"
    [ "$outcome" = PASS ] || overall=FAIL
done

head_at_end="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
head_stable=yes
if [ "$head_at_end" != "$head_at_start" ]; then
    # Evidence would be bound to a commit other than the one recorded.
    head_stable=no
    overall=FAIL
fi

iso_sha256="$(awk '$2 == "sushida-os-amd64.iso" { print $1 }' \
    "$PROJECT_ROOT/artifacts/SHA256SUMS" 2>/dev/null || true)"
build_commit="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["git_commit"])' \
    "$PROJECT_ROOT/artifacts/build-info.json" 2>/dev/null || true)"

{
    echo "release-check summary"
    echo "started_at=$started_at"
    echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "git_head=$head_at_start"
    echo "head_stable=$head_stable"
    echo "container_engine=${CONTAINER_ENGINE:-docker}"
    echo "builder_hash=$("$SCRIPT_DIR/builder-hash.sh")"
    echo "iso_sha256=${iso_sha256:-unknown}"
    echo "build_info_git_commit=${build_commit:-unknown}"
    printf '%s\n' "${lines[@]}"
    echo "result=$overall"
} > "$SUMMARY"

echo
cat "$SUMMARY"
[ "$overall" = PASS ]
