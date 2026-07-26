# Eval + Fetch Patterns

Core philosophy: browser provides real login & TLS fingerprint; eval+fetch bypasses curl blocks.

## Single API call via Browser

```bash
opencli browser <session> open "https://example.com/page"
sleep 3
opencli browser <session> eval "
fetch('https://api.example.com/v1/list')
  .then(r => r.json())
  .then(d => { window.__data = JSON.stringify(d); })
"
sleep 1
opencli browser <session> eval "window.__data"
```

**Critical contrast:** This is NOT the same as `curl` calling the same API. A bare HTTP client gets blocked (412/403), but the same API call routed through eval+fetch works because the browser provides real cookies, UA, TLS fingerprint, and execution environment.

## Cache Large Data to File

Any capture over ~10KB → save to file, not kept in context:

```bash
opencli browser sess eval "window.__data" > ~/web-cache/site_data.json
grep "keyword" ~/web-cache/*.json
```

## Hard Problem: eval Variable Persistence

**Symptom:** Second eval reports `Identifier 'xxx' has already been declared`.

**Root cause:** opencli eval does not destroy scope — `var`/`let`/`const` declarations accumulate.

**Rules (zero exceptions):**
- ✅ Use `window.__xxx` for cross-eval data passing
- ✅ Wrap logic in IIFE `(()=>{...})()`
- ✅ Wrap async logic in `(async()=>{...})()`
- ❌ Never use `var`/`let`/`const` at top level

## Hard Problem: Chinese Characters in Bash

**Any eval with Chinese or complex structure → write to file first:**

```bash
cat > /tmp/eval.js << 'EOFJS'
(async()=>{
  let r = await fetch('https://api.bilibili.com/x/web-interface/search/all/v2?keyword=桌面整理');
  let d = await r.json();
  window.__result = JSON.stringify(d);
})()
EOFJS
opencli browser sess eval "$(cat /tmp/eval.js)"
```

## Multiple Pages with Promise.all

```bash
opencli browser sess eval "
(async()=>{
  let pages = await Promise.all([1,2,3].map(n =>
    fetch('URL?pn='+n).then(r=>r.json())
  ));
  window.__all = JSON.stringify(pages);
})()
"
```
