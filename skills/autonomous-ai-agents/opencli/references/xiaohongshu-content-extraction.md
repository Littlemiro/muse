# Xiaohongshu Content Extraction via OpenCLI

## Problem
`opencli-shop xiaohongshu note <URL>` often times out — Xiaohongshu's anti-scraping blocks the structured note adapter. But the `search` command still works (returns titles, likes, dates, search_result URLs).

## Solution: Direct Browser Extraction

Use raw `opencli browser` to navigate to the Xiaohongshu explore page and extract content via `eval`.

### Step 1: Search
```bash
opencli-shop xiaohongshu search "<keywords>" --limit 15 -f md
```
Returns a markdown table with rank, title, author, likes, date, and a `search_result` URL.

### Step 2: Navigate to explore page
Convert the `search_result/ID` URL to `explore/ID` format (or just use the search_result URL directly — both work):

```bash
opencli browser <session> open "https://www.xiaohongshu.com/explore/<NOTE_ID>?xsec_token=<TOKEN>"
```

### Step 3: Extract content via eval
```bash
sleep 3 && opencli browser <session> eval "document.body.innerText"
```

### Notes
- The browser session can be slow — wait 2-3s after navigation for SPA rendering
- Some pages may show only footer/legal text if blocked (anti-scraping APP scan wall)
- The same page hash (`F6098E8F4EA9EF3A02490183BC6730E3`) appears across navigations — this is Xiaohongshu's SPA behavior, the content still changes
- If you get empty results, try extracting via DOM selectors:
  ```javascript
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
  const texts = [];
  let node;
  while (node = walker.nextNode()) {
    const t = node.textContent.trim();
    if (t && t.length > 0) texts.push(t);
  }
  texts.join(' | ');
  ```
