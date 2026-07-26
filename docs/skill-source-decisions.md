# Skill source decisions

These decisions separate a runtime source from retained comparison material.
They do not delete or mutate copies outside this repository.

## OpenCLI family

| Skill | Runtime canonical | External copy | Decision |
|---|---|---|---|
| `opencli` | Hermes `primary` | Keep for audit and fallback | The MUSE canonical baseline is based on primary; the external daemon material is merged after privacy sanitization. |
| `opencli-cookie-extract` | Hermes `primary` | Keep for audit and fallback | Primary is the long-term runtime choice; external remains a comparison source until a future review. |
| `opencli-site-patterns` | Hermes `primary` | Keep for audit and fallback | Primary is the long-term runtime choice; external remains a comparison source until a future review. |

## Why primary wins

The current comparison shows primary is newer for all three names and is the
fuller or more detailed variant for the `opencli` family. This is a source
selection decision, not a claim that external is useless: external remains
available for backfill, regression comparison, or rollback.

## Reconciliation rule

Do not let two same-name copies be silently loaded as peers. When a change is
needed:

1. compare file lists, hashes, and modification times;
2. choose one canonical runtime source;
3. merge only reviewed differences;
4. run privacy and MUSE audits;
5. record the decision here.
