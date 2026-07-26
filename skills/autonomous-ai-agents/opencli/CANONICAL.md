# Canonical-source note

This directory is the privacy-sanitized MUSE canonical baseline for the
`opencli` skill.

## Source decision

- Base: Hermes `primary` copy.
- Reason: it is the newer, more compact runtime variant and contains the fuller
  progressive reference set.
- Merge: the useful daemon protocol material from the older `external` copy was
  retained as `references/daemon-cookie-extraction.md`, then rewritten with
  placeholders and explicit credential-handling rules.
- Runtime copies: the Hermes primary and MUSE external copies remain in place.
  This repository change does not delete or overwrite either runtime copy.

## Privacy boundary

The canonical copy intentionally removes deployment-specific domains, profile
IDs, cookie examples, usernames, and absolute home-directory paths. Configure
private sessions and domains locally through environment variables or a local
skill; do not commit them to this repository.

## Maintenance rule

When primary and external diverge again, compare them by file and hash before
copying. Update this canonical directory only after a manual privacy review and
MUSE `refactor-audit` pass.
