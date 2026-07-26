# OpenCLI Session Auto-Init (Startup)

## Problem

After PC reboot, opencli daemon may restart but all browser sessions are lost.
Even though Edge cookies persist (user stays logged in on sites like 小红书, B站,
淘宝, PT sites), the sessions need to be re-created before I can navigate them.

## Solution

A startup script that opens all sessions in background tabs, inheriting Edge cookies.

### Script: `~/hermes-scripts/opencli-sessions-init.sh`

```bash
#!/bin/bash
SESSIONS="${OPENCLI_SESSIONS:-main shop web work}"

# Ensure daemon is running (retry 3x)
for i in 1 2 3; do
  opencli daemon status &>/dev/null && break
  sleep 1
done

# Open all sessions in parallel (background tabs)
for sess in $SESSIONS; do
  opencli browser "$sess" open "https://example.com" --window background &>/dev/null &
done

wait  # Wait for all to finish
```

### Windows Startup

A `.bat` wrapper at a user-owned scripts directory:
```batch
"C:\Program Files\Git\bin\bash.exe" -c "/c/Users/<USER>/hermes-scripts/opencli-sessions-init.sh"
```

A shortcut in Windows Startup folder:
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\OpenCLI Sessions.lnk`

Created via PowerShell:
```powershell
$WS = New-Object -ComObject WScript.Shell
$SC = $WS.CreateShortcut('...\Startup\OpenCLI Sessions.lnk')
$SC.TargetPath = 'C:\Users\<USER>\hermes-scripts\opencli-sessions-init.bat'
$SC.WindowStyle = 7
$SC.Save()
```

### Example Sessions

| Session | Purpose |
|---------|---------|
| `main` | General purpose |
| `shop` | Taobao shopping scans |
| `web` | General web tasks |
| `work` | General purpose |
| `xiaohongshu` | 小红书 search/notes |
| `bilibili` | B站 search |
| `private-site-a` | User-configured private site |
| `private-site-b` | User-configured private site |
| `site-a` | Reserved/placeholder |

### Notes

- `--window background` opens tabs silently without popping up
- All sessions init to `https://example.com` as placeholder
- Navigate to actual sites on demand: `opencli browser <session> open "https://target.site"`
- Edge cookies carry over because opencli shares the same browser profile
