(Migrated from opencli-browser-interaction skill — eval variable persistence, Chinese encoding, XHS extraction patterns, and robustness patterns.

Key patterns:
1. Always use window.__xxx + IIFE for cross-eval data
2. Save eval scripts to file when containing CJK characters
3. browser eval + fetch() bypasses curl-level API blocks
4. Cache data >10KB to ~/web-cache/ to save context
5. SPA sites return same page hash — this is NORMAL, don't skip eval)
