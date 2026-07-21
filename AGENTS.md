# AGENTS.md

Authoritative safety and working contract for agents and humans changing this
repository. Where this file names a value, the machine-readable source of
truth is `contracts/runtime-contract.json` / `contracts/release-contract.json`
(see `docs/documentation-map.md`); this file defines the boundaries that must
never drift.

Restructured 2026-07-21 (Stage F-02). Implementation history: git log of this
file.

## 1. Safety invariants

**Mission.** This repository builds an amd64 Debian 13 (trixie) live-build
kiosk image whose only purpose is displaying the official Sushi-da website
full-screen in unmodified Debian Chromium under Cage (Wayland), restarted by
systemd, on a read-only live system. Default URL `https://sushida.net/play.html`,
configurable only via `/etc/sushida-os/config.env` and validated against the
fixed origin allowlist.

**Content and legal.** Never copy, mirror, scrape, inject into, automate, or
redistribute Sushi-da content; never modify its DOM, traffic, ads, or scores.
The offline page only explains that the network is unavailable and must not
imitate Sushi-da.

**Kiosk escape prevention** is the primary security goal, layered as: Chromium
managed policy (developer tools, guest/incognito, sign-in, autofill, printing,
downloads, URL allow/blocklist), kiosk command-line options (never
`--no-sandbox`, never `--disable-gpu`), Cage/console lockdown (no getty, no
VT login, no terminal emulator, no SSH/remote shell, no login screen), and the
unprivileged `kiosk` account (no password login, no sudo, no admin groups, no
persistent home). Gameplay input (letters, digits, punctuation, Space, Enter,
Backspace) must keep working; escape shortcuts must not, and a killed session
must restart within five seconds. Never restrict shortcuts by injecting
scripts into the website.

**Network surface.** Wired DHCP automatic; offline fallback with low-frequency
connectivity checks only. Wi-Fi provisioning is the narrowly constrained,
loopback-only page served by the unprivileged `wifi-setup` account: scan,
submit one credential to the fixed NetworkManager profile, show status.
A general-purpose Wi-Fi settings GUI is prohibited; the page must never expose
arbitrary NetworkManager settings, files, commands, URLs, or a route to a
shell. Credentials embedded in an ISO are extractable by anyone with the ISO —
say so in docs, and never commit real credentials (redacted template:
`local/wifi.nmconnection.example`).

**State.** All mutable runtime state lives in tmpfs/`/run`; the system returns
to a known-good state after power loss. Secrets and machine-local files live
only under `local/` (git-ignored); generated output only under `build/` and
`artifacts/`.

**Honesty.** Never claim a test passed without running it; never claim
stronger security than implemented; report verified and unverified behavior
separately. The image alone cannot resist a physical attacker — deployment
docs cover UEFI passwords and disabling external/removable boot.

## 2. Allowed operations

- Implementing and testing inside this repository, in WSL/Linux, with the
  podman/docker builder container (`make builder`); `make iso` only via the
  privileged builder container.
- One task = one commit, made by the implementing agent with the task's
  commit message and Co-Authored-By trailer (working agreement:
  `docs/refactoring-work-order.md` §1.2).
- QEMU testing (`make test-qemu*`) where KVM exists; reading logs and
  artifacts; updating docs together with the change.
- Behavior-preserving refactors only when a work-order task authorizes them,
  with the behavioral test suite unchanged as evidence
  (`docs/refactoring-work-order.md` §2.2, principles P1–P5).

## 3. Prohibited operations

- `git push / merge / rebase / reset / stash / clean / restore`, history
  rewriting. Pushing is the user's action.
- Running `dd`/`mkfs`/partitioning against real devices, flashing real media,
  modifying host GRUB/UEFI/Secure Boot/disks/network/`/etc`/accounts,
  rebooting the host. The guarded `scripts/flash.sh` is never executed by an
  agent against a real device; `--yes` must never bypass system-disk
  protection.
- Committing secrets, private keys, tokens, machine identifiers, or real
  Wi-Fi credentials; printing or logging secret material.
- Changing production runtime behavior, contract values, or the security
  boundaries in §1 without an explicit authorized task. Weakening or skipping
  verification (tests, checker, verify-iso.sh) to make work pass.
- Writing outside the repository except normal container-engine storage and
  the session scratch area.

## 4. Runtime and release contracts

- `contracts/runtime-contract.json`: URLs, runtime paths, timeouts, routes,
  navigation allow/blocklist, service names. `tools/check-contracts.py`
  cross-checks every value against the production sources; a contract or
  source move must keep the checker green in the same commit (P1).
- `contracts/release-contract.json`: the artifact manifest — artifact set,
  required ISO paths, source→image mappings with modes and verification
  levels, required packages/services, metadata schema. `scripts/build.sh`,
  `scripts/verify-iso.sh`, and `scripts/clean.sh` all read it; names are not
  repeated per script.
- New shipped production files require the three-point registration in the
  same commit: release contract, image validation hook, contract-test fixture
  (P3).
- On-disk protocol changes are introduced dual-write with the legacy file
  authoritative until an explicit switchover task (P4). Reason/enum fields
  never carry URLs, SSIDs, or secrets (P5).

## 5. Test requirements

- Static + contract tests: `.venv/bin/python -m pytest tests/static/ tests/contracts/ -q`
  (or `make test-static test-contracts`).
- Shell tests: `make container-shell CONTAINER_ENGINE=podman` (bats +
  ShellCheck; not available on the host).
- Checker: `python3 tools/check-contracts.py` must exit 0.
- Structure index: `make check-structure` (STRUCTURE.txt is generated by
  `tools/gen-structure.py`; never hand-edited).
- CI is `make ci` (test + check-contracts + check-structure + diff check);
  the target list is authoritative in `make help`.
- Behavioral tests (characterization, bats) are the evidence for
  behavior-preserving changes and their assertions are not edited to make a
  refactor pass; only source-pattern checks and loaders may track moved code,
  recorded as a deviation (P2).
- Every commit stands green on its own (P1). A failing check stops the task
  (§8), it is never worked around.

## 6. Artifact requirements

- `make iso` (privileged builder only) requires a clean worktree and produces
  the artifact set declared in the release contract, published only after
  `scripts/verify-iso.sh` passes against the staging directory.
- Verification is manifest-driven: existence, checksums, metadata
  cross-checks (ISO SHA ↔ SHA256SUMS ↔ clean HEAD ↔ contract hash ↔ package
  manifest hash), partition layout, required ISO/squashfs paths, and
  byte-exact comparison with declared mode/owner for every mapping marked
  `exact`.
- Deterministic inputs (SOURCE_DATE_EPOCH from the commit date, fixed
  locale/TZ/umask) are controlled per `docs/reproducible-builds.md`; package
  versions are recorded, never pinned.
- Stale or tampered artifacts must fail verification — fixture proof lives in
  `tests/shell/verify-stale.bats`.

## 7. Final report format

For each completed task report, separately and honestly:

1. Summary of the change and files touched.
2. Contracts/invariants relied on and preserved.
3. Tests added or updated.
4. Commands executed with exit codes (only those actually run).
5. Items not executed (environment limits), stated as not executed.
6. Remaining risks / follow-ups (backlog IDs where applicable).

Definition-of-done for the whole project: `docs/refactoring-work-order.md` §8;
acceptance evidence: `docs/acceptance-tests.md`.

## 8. Stop conditions

Stop and report instead of proceeding when:

- Unexplained working-tree differences or unexplainable test failures appear.
- The task cannot be completed without changing production behavior or a
  contract value.
- Anything that looks like a secret is found.
- A required verification cannot be run and the task's outcome depends on it.
- An instruction conflicts with this file — this file wins until the user
  explicitly changes it.
