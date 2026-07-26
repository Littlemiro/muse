# OpenCLI Basic Usage

## Prerequisites & Setup

```bash
npm install -g @jackwener/opencli
opencli doctor                     # Should show "Everything looks good!"
opencli profile list               # See connected browser profiles
```

## Session Management

```bash
opencli browser <session> open <url>          # Navigate
opencli browser <session> bind                # Bind to existing tab
opencli browser <session> state               # Page snapshot (text)
opencli browser <session> close               # Release session
opencli daemon stop                           # Shutdown daemon
```

## Page Interaction

```bash
opencli browser <session> eval <js>           # Execute JS in page
opencli browser <session> click <ref>         # Click element
opencli browser <session> type <ref> <text>   # Fill input
opencli browser <session> keys "Enter"        # Keyboard
opencli browser <session> scroll down         # Scroll (human-like intervals)
```

## Quick Recipes

### Read page content
```bash
opencli browser main open "https://example.com"
sleep 2
opencli browser main state
```

### Search and extract
```bash
opencli browser main open "https://search.example.com"
sleep 2
opencli browser main type @search-input "keyword"
opencli browser main keys "Enter"
sleep 2
opencli browser main eval "document.body.innerText.slice(0, 5000)"
```

### Check login status
```bash
opencli browser <session> state | grep -iE "欢迎|退出|登录|sign in|logout|welcome"
```

## Session Persistence Note

opencli browser sessions persist until explicitly closed. You can open a session, do multiple operations, and close it at the end. Sessions survive across CLI invocations — the daemon keeps them alive.
