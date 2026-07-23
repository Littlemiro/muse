---
name: demo-hello
description: "Create MUSE-compliant demo skills with a ready template"
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [demo, tutorial, hello-world]
    category: productivity
trigger_keywords: [demo, hello, greeting]
inputs:
  name: "string | Name to greet (default: 'World')"
outputs:
  greeting: "string | A friendly greeting message"
---

# Demo Hello Skill

A simple demonstration skill that shows how to create a MUSE-compliant skill.

## Usage

When loaded, this skill provides a simple greeting function:

```
> I am greeted as "Hello, World!"
> I am greeted as "Hello, Alice!"
```

## Implementation Notes

This is a pure-documentation skill — it defines the structure and standards
for MUSE-compliant skills without requiring any executable code.

## Verification Checklist

- [ ] frontmatter has `name`, `description`, `version`, `author`, `license`
- [ ] description is imperative and ≤64 chars
- [ ] description does NOT start with the skill name
- [ ] metadata.hermes.tags defined
- [ ] trigger_keywords defined
