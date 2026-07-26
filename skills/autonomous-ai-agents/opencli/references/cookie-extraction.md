# Cookie Extraction via OpenCLI Daemon

## When to Use This

Use this only when a site requires an httpOnly cookie and browser navigation
alone cannot complete the task. `document.cookie` cannot read httpOnly cookies;
the OpenCLI daemon can request them from the browser extension.

Cookie values are credentials. Keep the domain explicit, avoid printing the
response, and prefer a short-lived local secret store over plain-text files.

## Architecture

```
opencli CLI → daemon (port 19825) → Chrome Extension → Cookie API (including httpOnly)
```

## Step 1: Check Daemon Status

```bash
curl -s -H 'X-OpenCLI: 1' http://127.0.0.1:19825/status
```

Important fields:

- `contextId` — current browser profile ID; obtain it at runtime
- `extensionConnected` — must be `true` before issuing commands

## Step 2: Ensure Browser Session Is Logged In

```bash
opencli browser <session> open <url>
opencli browser <session> state
```

Confirm the page is the intended site and profile before requesting cookies.

## Step 3: Request Cookies for One Domain

```bash
curl -s -H 'X-OpenCLI: 1' -H 'Content-Type: application/json' \
  http://127.0.0.1:19825/command \
  -d '{"id":"get_cookies","action":"cookies","session":"<session>","contextId":"<contextId>","domain":"<target-domain>"}'
```

Parameters:

- `session` — the OpenCLI browser session name
- `contextId` — read from `/status`; do not hard-code it
- `domain` — the exact target domain; never omit it

Do not pipe the response to a terminal, chat transcript, or diagnostic log.
If automation needs the value, pass it directly to a protected local process or
secret store and clear it after use.

## Safer Alternative: Browser Navigation

When possible, operate through the logged-in browser so OpenCLI carries the
session without extracting the cookie:

```bash
opencli browser <session> open "https://<target-domain>/<path>"
opencli browser <session> click <ref>
```

## Important Pitfalls

1. **`profile_disconnected`** — refresh `/status` and use the current `contextId`.
2. **`Cookie scope required`** — provide an explicit `domain` or URL.
3. **`extensionConnected: false`** — reconnect the browser extension before retrying.
4. **Cookie expired** — re-authenticate in the browser; do not copy a cookie from logs.
5. **Cross-machine use** — do not sync browser cookies through ordinary file copy or chat.

## Raw CDP Method

The CDP method can return all cookies and therefore has a larger blast radius.
Use it only for a narrowly scoped, explicitly authorized debugging task:

```bash
curl -s -H 'X-OpenCLI: 1' -H 'Content-Type: application/json' \
  http://127.0.0.1:19825/command \
  -d '{"id":"cdp1","action":"cdp","session":"<session>","contextId":"<contextId>","cdpMethod":"Network.getAllCookies","cdpParams":{}}'
```
