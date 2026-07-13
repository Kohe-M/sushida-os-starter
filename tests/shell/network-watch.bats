#!/usr/bin/env bats

@test "starter repository contains AGENTS.md" {
  [ -f "AGENTS.md" ]
}
