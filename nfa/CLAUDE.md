# CLAUDE.md

See README.md for the project overview and block mapping.

Editing conventions for this directory:
- Source is `nfa/nfa.nms` plus one function per file in `nfa/nfa/<name>.msc`; the `# name.msc` files are standalone scripts bound in-game. Every function file starts with `# <signature>`, then `@using nfa` and `@fast`.
- `processString.msc` and `runTest.msc` implement the same simulator twice; change both together. The same applies to the `*Fast` variants.
- Guard connection records with `parts.length() >= 6 && parts[0] == "connection"` before indexing; do not change the coordinate/face-key string formats without updating every lookup.
- Leave the `String(arcLength)` substring overrides (`"1.00984782"`, `"1.32"`) in `nfaInteractBlock.msc` alone unless rewriting the whole arc-length pass.
