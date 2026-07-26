# OpenCLI Session Startup on Windows

## Problem

After a Windows reboot, opencli sessions are lost (tabs close). But the Edge browser retains all site cookies. To avoid re-logging into sites, re-initialize sessions at login.

## Solution

Create a startup script that opens all named opencli browser sessions in background tabs:

```bash
#!/bin/bash
# opencli-sessions-init.sh

SESSIONS="${OPENCLI_SESSIONS:-main shop web work}"

# Ensure daemon is running
opencli daemon status &>/dev/null || opencli daemon start
sleep 2

# Open all sessions in parallel
for sess in $SESSIONS; do
  opencli browser "$sess" open "https://example.com" --window background &
done
wait
```

## Windows Startup Setup

1. Create a batch wrapper (`opencli-sessions-init.bat`):
```batch
@echo off
"C:\Program Files\Git\bin\bash.exe" -c "/c/Users/<USER>/hermes-scripts/opencli-sessions-init.sh"
```

2. Create a shortcut in Startup folder via PowerShell:
```powershell
$WS = New-Object -ComObject WScript.Shell
$SC = $WS.CreateShortcut($env:APPDATA + '\Microsoft\Windows\Start Menu\Programs\Startup\OpenCLI Sessions.lnk')
$SC.TargetPath = "$env:USERPROFILE\hermes-scripts\opencli-sessions-init.bat"
$SC.WorkingDirectory = "$env:USERPROFILE\hermes-scripts"
$SC.WindowStyle = 7
$SC.Save()
```

## Key points

- `--window background` opens tabs without popping up and stealing focus
- Edge cookies persist across reboots — sessions don't need to navigate to actual sites, just need to exist
- Sessions stay on `about:blank` or `example.com` until needed; navigate to actual sites on demand
