# OpenCLI Daemon Cookie Extraction Reference

This is a generic protocol reference for an authorized local OpenCLI setup.
Replace placeholders at runtime; do not commit real domains, profile IDs, or
cookie values.

## Daemon Architecture

```
opencli CLI → local daemon (port 19825) → browser extension → browser CDP
```

The daemon exposes a local HTTP API. Treat it as a credential-bearing control
plane: a caller that can reach it may be able to navigate pages, execute page
JavaScript, capture network traffic, or request cookies.

## GET /status

```bash
curl -s -H 'X-OpenCLI: 1' http://127.0.0.1:19825/status
```

Use the response only to obtain current runtime state:

- `contextId` — active browser profile ID; it can change after reconnects
- `extensionConnected` — must be `true` for browser commands
- `profiles[]` — available profiles and connection state

Never put a real `contextId` in a shared skill or commit it to Git.

## POST /command

```bash
curl -s -H 'X-OpenCLI: 1' -H 'Content-Type: application/json' \
  http://127.0.0.1:19825/command \
  -d '{"id":"<unique-id>","action":"<action>","session":"<session>","contextId":"<contextId>","timeout":120}'
```

Common fields:

- `id` — unique command identifier
- `action` — `cookies`, `cdp`, `exec`, `navigate`, `network-capture`, or another daemon-supported action
- `session` — local OpenCLI session name
- `contextId` — current profile ID from `/status`
- `timeout` — command timeout in seconds

## Scoped Cookie Request

Request cookies for one explicitly authorized domain only:

```bash
curl -s -H 'X-OpenCLI: 1' -H 'Content-Type: application/json' \
  http://127.0.0.1:19825/command \
  -d '{"id":"cookie-1","action":"cookies","session":"<session>","contextId":"<contextId>","domain":"example.invalid"}'
```

An omitted domain should be treated as an error. Do not print, persist, or send
the response to a remote service. If a downstream command needs the value,
transfer it through an OS secret mechanism or an in-memory pipe.

## CDP and Page Execution

CDP and page execution are more powerful than ordinary navigation:

```bash
curl -s -H 'X-OpenCLI: 1' -H 'Content-Type: application/json' \
  http://127.0.0.1:19825/command \
  -d '{"id":"cdp-1","action":"cdp","session":"<session>","contextId":"<contextId>","cdpMethod":"Target.getTargets","cdpParams":{}}'
```

Use `Network.getAllCookies`, `Runtime.evaluate`, and network capture only when
the user has explicitly authorized that scope. Prefer a restricted wrapper for
an agent that only needs search or page reading.

## Failure Handling

- `ECONNREFUSED`: start or diagnose the local daemon.
- `extensionConnected: false`: reconnect the extension and re-check `/status`.
- `profile_disconnected`: fetch a fresh `contextId`.
- Empty network capture: start capture before navigating or generating traffic.
