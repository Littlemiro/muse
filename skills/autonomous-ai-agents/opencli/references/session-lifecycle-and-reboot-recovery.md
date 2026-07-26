# Session Lifecycle & Reboot Recovery

Sessions are ephemeral. They live in the daemon's runtime memory and do not persist across:
- Daemon restarts (`opencli daemon stop` / `start`)
- System reboots
- Profile reconnects

After a reboot, the daemon comes up fine but **every session is gone** (trapped at `about:blank`).

## Why this matters

Most opencli tasks depend on browser cookies for authentication. On this setup (Windows + Edge), the browser profile persists across reboots — cookies survive. The opencli extension reconnects to the daemon automatically, but it has no active tabs/sessions until explicitly opened.

This means: **you don't need to re-login after reboot. You just need to pre-open sessions.**

## Recovery script (run on system startup)

```bash
# Pre-open all tracked sessions so they inherit Edge's persistent cookies
opencli browser main open "about:blank"
opencli browser shop open "about:blank"
opencli browser web open "about:blank"
opencli browser work open "about:blank"
opencli browser xiaohongshu open "about:blank"
opencli browser bilibili open "about:blank"
for sess in ${OPENCLI_SESSIONS:-main shop web work}; do
  opencli browser "$sess" open "https://example.com" --window background
done
```

The daemon + opencli CLI must be in PATH for this to work. Sessions open in background tabs (Edge doesn't steal focus). Each session lands on a blank page — navigate to target URLs when actually needed.

## Session inventory

| Session | Purpose | Login needed? |
|---------|---------|---------------|
| main | General-purpose | No (Edge cookie) |
| shop | Taobao store scans | No (Edge cookie) |
| web | General web tasks | No (Edge cookie) |
| work | General workflow | No (Edge cookie) |
| xiaohongshu | 小红书 search/extract | No (Edge cookie) |
| bilibili | B站 search | No (Edge cookie) |
| private-site-a | User-configured private site | No (Edge cookie) |
| private-site-b | User-configured private site | No (Edge cookie) |
| site-a | Reserved | No (Edge cookie) |

## When sessions go stale

If a site session expires (cookies revoked), you'll see login redirects or 403s on opencli commands. Symptoms:
- `opencli browser <session> state` shows a login page
- eval returns "请登录" / "sign in"
- Extracted data is empty or error-shaped

Fix: manually open that site in Edge once, log in, then re-run the recovery script. The new cookies automatically apply to the next opencli session.

## Alternative: tail -f daemon logs

The daemon logs connection events. If sessions aren't recovering:
```bash
opencli daemon status   # check daemon is running
opencli doctor          # check extension connectivity
# then rerun the recovery script above
```
