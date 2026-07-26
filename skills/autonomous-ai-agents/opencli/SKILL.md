---
name: opencli
description: "jackwener/OpenCLI — browser automation bridge: turn websites into CLI commands via your logged-in Edge/Chrome extension."
version: 1.2.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [opencli, browser-automation, edge, chrome, captcha, geetest]
    category: autonomous-ai-agents
    related_skills: [opencli-site-patterns, opencli-cookie-extract]
trigger_keywords: [opencli, browser, 浏览器自动化, 网页提取, cookie提取]
---

# OpenCLI

[OpenCLI](https://github.com/jackwener/OpenCLI) converts any website into CLI commands via your **already-logged-in browser** extension.

## When to Use

| ✅ Use when | ❌ Don't use when |
|---|---|
| Site requires login (you're already logged in) | You need anonymous access (use `web_extract` / `curl`) |
| SPA pages (Vue/React) need rendering | The task is a single API call (use `curl` / `fetch`) |
| Geetest/CAPTCHA pages block curl | The browser extension is not installed |
| Complex OAuth/OIDC flows | The daemon is unreachable (`extensionConnected: false`) |

## Quick Start

```bash
# Verify installation
opencli doctor

# Open a page in browser session
opencli browser main open "https://example.com"

# Read page content
opencli browser main state

# Execute JavaScript
opencli browser main eval "document.title"
```

## Reference Files (loaded on demand)

|| File | Covers | Load when |
||------|--------|-----------|
| `references/basic-usage.md` | Browse, click, type, scroll, eval, session management | First time using opencli |
| `references/cookie-extraction.md` | Scoped httpOnly cookie extraction via daemon API | Building automation that needs cookies |
| `references/daemon-cookie-extraction.md` | Daemon protocol, status fields, cookie/CDP actions | You need the lower-level daemon API |
| `references/advanced.md` | Raw CDP passthrough, network capture | Debugging or advanced browser control |
| `references/eval-patterns.md` | Eval + Fetch patterns, Chinese escaping, variable persistence | Using eval for data extraction |
| `references/opencli-security-wrapper.md` | Whitelist wrapper for lower-risk shopping actions | Exposing opencli to another agent |
| `references/opencli-shop-wrapper.md` | Wrapper behavior and maintenance notes | Maintaining the shopping wrapper |
| `references/robust-eval-patterns.md` | Defensive eval and extraction patterns | Eval results are unstable |
| `references/session-startup-windows.md` | Auto-initializing sessions on Windows reboot | Setting up startup scripts for session persistence |
| `references/session-startup.md` | Cross-platform session startup | Setting up opencli sessions on boot |
| `references/session-auto-init.md` | Startup script and Windows startup setup | Sessions are lost after reboot |
| `references/session-lifecycle-and-reboot-recovery.md` | Session lifecycle and reconnect behavior | Diagnosing reboot recovery |
| `references/startup-automation.md` | Reboot recovery and session initialization | Rebooted or sessions stuck on a blank page |
| `references/troubleshooting.md` | Extension conflict, daemon not responding, common errors | Commands fail with unexpected errors |
| `references/xiaohongshu-content-extraction.md` | Xiaohongshu extraction patterns | Extracting Xiaohongshu content |
## Related Skills

- `opencli-site-patterns` — Site-specific extraction patterns (小红书/B站/淘宝/PT)
- `opencli-cookie-extract` — Thin wrapper for cookie-only use cases

## Security Boundary

OpenCLI can access logged-in browser state. Treat cookies, CDP output, network
captures, and page content as credentials or private data. Scope cookie requests
to an explicit domain, never print cookie values, and prefer the restricted
wrapper when an agent does not need full browser control.

## Windows Reboot Recovery

After reboot, browser sessions are lost but Edge cookies survive. Reinitialize sessions via a startup script:

```
opencli browser <session> open "<url>" --window background   # Opens without popping up
```

Key facts:
- `about:blank` is blocked — use `https://example.com` as placeholder
- `--window background` opens tabs silently, won't interrupt the user
- Sessions persist until explicitly `close`'d, survive across CLI invocations
- Daemon stays up for days (observed 88h+ uptime on Windows)
- On Windows, use Startup folder shortcuts (.bat wrapper → `bash -c "<script>"`) or Task Scheduler
- Session names are deployment-specific. Keep them in local configuration rather
  than hard-coding private site names in a shared skill.
