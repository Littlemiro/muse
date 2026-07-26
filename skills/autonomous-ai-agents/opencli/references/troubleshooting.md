# OpenCLI Troubleshooting

## Extension Conflict on Injected Pages

**Symptom:** `state`/`get`/`click`/`screenshot` commands fail with:
```
attach failed: Cannot access a chrome-extension:// URL of different extension
```

**Cause:** Chrome/Edge debugger API refuses to attach when OTHER extensions inject content scripts. Common triggers: Microsoft Brand Extension, SciSpace, Password Managers.

**Workaround — use `eval` for all page interaction:**

```bash
# eval DOES work even when other commands fail
opencli browser main eval "document.title"

# Click a button via eval
opencli browser main eval "
document.querySelectorAll('button').forEach(b => {
    if (b.textContent.includes('签到')) b.click();
});
"

# Read all visible text
opencli browser main eval "
const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
const texts = [];
let node;
while (node = walker.nextNode()) {
    const t = node.textContent.trim();
    if (t && t.length > 0) texts.push(t);
}
texts.join(' | ');
"
```

## Daemon Not Responding

```bash
# Check if daemon is alive
curl -s http://127.0.0.1:19825/status
# → ECONNREFUSED → daemon not running

# Start daemon (it auto-launches on first browser command)
opencli browser x open "https://example.com" --window background

# Kill and restart
opencli daemon stop
opencli browser main open "https://example.com"
```

## `extensionConnected: false`

Daemon is online but no Chrome extension connected.
1. Check if Chrome/Edge is running with the OpenCLI extension enabled
2. Run `opencli doctor` to verify setup
3. In cron/headless environments, check `extensionConnected` before running any daemon command

## Common Error Codes

| Error | Cause | Fix |
|-------|-------|-----|
| `profile_disconnected` | contextId expired | Re-fetch from `/status` |
| `Cookie scope required` | No domain param | Add `"domain":"..."` |
| `Cannot access chrome-extension://...` | Extension conflict | Use `eval` instead of `state`/`click` |
| Exit code 124 (timeout) | `extensionConnected: false` | Start Chrome with extension first |

## General Debug Flow

1. `opencli doctor` — check installation
2. `curl http://127.0.0.1:19825/status` — check daemon
3. `opencli browser <session> state` — check page loaded
4. `opencli browser <session> eval "document.title"` — eval fallback
5. If all fail → close and reopen browser session
