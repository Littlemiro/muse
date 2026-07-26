# Advanced OpenCLI: CDP Passthrough & Network Capture

## Raw CDP Passthrough

The daemon routes raw Chrome DevTools Protocol commands:

```bash
curl -s -H 'X-OpenCLI: 1' -H 'Content-Type: application/json' \
  http://127.0.0.1:19825/command \
  -d '{"id":"cdp_1","action":"cdp","session":"<session>","contextId":"<contextId>","cdpMethod":"Network.getAllCookies","cdpParams":{}}'
```

Parameters:
- `cdpMethod` — CDP method name (e.g. `Network.getAllCookies`, `Runtime.evaluate`, `Target.getTargets`)
- `cdpParams` — method params as JSON object

This bypasses opencli's page abstraction entirely — you can call any CDP method: `Target.getTargets`, `Runtime.evaluate`, `Page.navigate`, `DOM.getDocument`, etc.

## Network Capture

Use the `network` command to capture HTTP request headers including cookies:

```bash
# Navigate first
opencli browser main open "https://example.com"

# Capture recent requests
opencli browser main network --all --since 10s

# Get full body of a specific entry
opencli browser main network --detail <key>

# View raw cached data
cat ~/.opencli/cache/browser-network/<session>.json
```

Note: The `network` command may show 0 entries if capture started after page load. Start capture before navigation for best results.

## Security Wrapper

For search-only use cases (shopping, research), wrap opencli with a restricted wrapper that whitelists only `search`/`detail` commands. See `opencli-site-patterns` references for implementation.
