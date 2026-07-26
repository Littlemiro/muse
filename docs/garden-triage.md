# Garden triage policy

Garden is a decision-support layer, not an automatic deny-list.

## Current policy

- Process high-confidence findings: real credential exposure, malformed or
  missing frontmatter, actual remote execution patterns, and duplicate-source
  topology.
- Treat `needs_review` as a queue for inspection, not a reason to disable a
  skill that the user intentionally needs.
- Treat broad lexical matches such as `format`, `delete`, `network`, or
  `script` as signals. They require context before action.
- Do not mass-edit or archive the Garden based on the current classifier alone.

## Operational consequence

Hermes remains responsible for execution approval and lifecycle management.
MUSE supplies discovery, provenance, comparison, risk tags, and an auditable
maintenance queue. A future calibration round may improve the classifier and
add confidence thresholds; this round intentionally keeps that work separate
from the OpenCLI source decision.
