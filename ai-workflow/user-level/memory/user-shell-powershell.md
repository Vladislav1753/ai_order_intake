---
name: user-shell-powershell
description: "User runs commands in Windows PowerShell 5.1, so commands given to them must not use && chaining"
metadata:
  node_type: memory
  type: user
  modified: 2026-10-23T12:14:01.405Z
---

The user pastes commands into Windows PowerShell 5.1, where `&&` is a parser error.

**Why:** `git add ... && git commit ...` failed for them with "The token '&&' is not a valid statement separator" (2026-10-23).

**How to apply:** Give commands for the user to run in PowerShell 5.1 syntax: one command per line, or chain with `; if ($?) { ... }`. Use ```powershell fences.
