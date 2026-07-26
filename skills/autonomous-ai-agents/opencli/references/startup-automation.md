# Startup Automation: OpenCLI Session Persistence Across Reboots

## Problem

OpenCLI browser sessions do not survive a daemon restart. After a system reboot, all browser sessions are gone — even though Edge/Chrome cookies persist in the browser profile. Each session must be re-created before you can navigate to any URL.

## Solution: Startup Script

Create a script that re-initializes all needed sessions on boot, then register it to run at user login.

### Script Template

```bash
#!/bin/bash
# opencli-sessions-init.sh
# Initialize all browser sessions on boot (parallel open, background tabs)

SESSIONS="${OPENCLI_SESSIONS:-main shop web work}"

# Ensure daemon is running (wait up to 3s)
opencli daemon status &>/dev/null
if [ $? -ne 0 ]; then
  opencli daemon start 2>/dev/null
  sleep 3
fi

# Parallel init for speed
for sess in $SESSIONS; do
  (opencli browser "$sess" open "https://example.com" --window background &>/dev/null) &
done
wait
```

### Key Points

- **`--window background`** — opens tabs without stealing focus or popping up windows
- **`https://example.com`** — lightweight placeholder; actual sites navigated on demand
- **Parallel execution** — all sessions initialize concurrently
- **Session names** — keep private site/session names in `OPENCLI_SESSIONS`, not in a shared skill

### Windows Startup Registration

**Startup Folder (simplest):**
Create a .bat wrapper calling the script via bash, put shortcut in:
`C:\Users\<USER>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\`

### What This Does NOT Do

- Does **not** log into any site — relies on existing browser cookies
- Does **not** navigate to specific pages — sessions sit on example.com ready for use

### Verification After Reboot

```bash
for sess in main shop web; do
  echo "[$sess] $(opencli browser "$sess" eval 'window.location.href' 2>&1)"
done
# Expect all to show https://example.com/
```
