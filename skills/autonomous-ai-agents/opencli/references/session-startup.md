# OpenCLI Session Startup / Persistence

## Problem

Browser sessions created with `opencli browser <session> open <url>` do not persist across system reboots. After restarting the host PC, all sessions are gone and must be re-created.

Since opencli sessions inherit Edge/Chrome cookies (the user is already logged into target sites), re-creating sessions on boot is sufficient to regain authenticated access.

## Solution: Startup Script

A bash script that re-opens all known sessions on boot, using `--window background` to avoid popping up visible tabs:

```bash
#!/bin/bash
# opencli-sessions-init.sh
SESSIONS="${OPENCLI_SESSIONS:-main shop web work}"

# Ensure daemon is running
opencli daemon status &>/dev/null || { opencli daemon start; sleep 3; }

# Parallel session creation
for sess in $SESSIONS; do
  (opencli browser "$sess" open "https://example.com" --window background &>/dev/null) &
done
wait
```

## Windows Auto-Start Setup

1. Create a `.bat` wrapper:
```bat
@echo off
"C:\Program Files\Git\bin\bash.exe" -c "/c/Users/<USER>/hermes-scripts/opencli-sessions-init.sh"
```

2. Place a shortcut to the `.bat` in the Windows Startup folder:
```
C:\Users\<user>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\
```

Created via PowerShell:
```powershell
$WS = New-Object -ComObject WScript.Shell
$SC = $WS.CreateShortcut('C:\Users\<user>\AppData\Roaming\...\Startup\OpenCLI Sessions.lnk')
$SC.TargetPath = 'C:\Users\<user>\hermes-scripts\opencli-sessions-init.bat'
$SC.WindowStyle = 7
$SC.Save()
```

## Verifying Sessions After Reboot

```bash
for sess in ${OPENCLI_SESSIONS:-main shop web work}; do
  echo "[$sess] $(opencli browser "$sess" eval "window.location.href" 2>&1)"
done
```
