#!/usr/bin/env bash
# Print the fingerprint of the builder image sources.
#
# `make builder` stores it as an image label and container-run.sh refuses an
# image whose label differs, so tests and ISO builds never run on a toolchain
# built from older builder/ sources.
set -euo pipefail

cd "$(dirname "$0")/.."
cat builder/Dockerfile builder/entrypoint.sh | sha256sum | cut -d' ' -f1
