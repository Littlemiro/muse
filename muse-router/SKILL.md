---
name: muse-router
description: Find and inspect relevant local MUSE skills before solving non-trivial tasks.
version: 1.0.0
metadata:
  hermes:
    category: software-development
    tags: [muse, routing, skill-discovery]
trigger_keywords: [skill, workflow, repair, setup, configure]
---

# MUSE Router

Use this skill for non-trivial tasks that may have a reusable local workflow.
Skip it for greetings, short explanations, and tasks with an obvious direct answer.

## Decision chain

1. Run the configured MUSE console:
   `muse-console.py route "<the user's task>" --json`
2. If there is no match, continue with the normal Hermes workflow.
3. If there is a match, inspect the highest-scoring skill by the returned path
   or skill id. A bare name is also accepted when MUSE can select one source:
   `muse-console.py inspect <path-or-id> --json`
4. Read `ready` skills directly. Read `needs_review` skills with the reported
   warning in mind. For `critical`, show the risk summary before using the
   workflow, but do not treat MUSE as an approval gate. Hermes still controls
   approval of the actual commands and file changes.

MUSE inspection is read-only and does not approve, apply, or execute a skill.
Follow Hermes' own command approval and file-write safety rules when applying
the inspected workflow. Never execute a script merely because it was listed by
MUSE; inspect it and let Hermes approve the resulting command separately.
