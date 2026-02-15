# Open Questions Before Build

## Product
1. Should `repo` input accept only `owner/repo` or also full GitHub URL?
2. Should default `ref` resolve to default branch each call or be pinned after first resolution?
3. Minimum snippet length and max result count defaults?

## Technical
4. Preferred snapshot strategy for search:
   - REST recursive tree + blob fetch
   - archive ZIP download + selective parse
5. Cache backend for v1:
   - in-memory only
   - optional disk cache
6. Search engine implementation:
   - simple regex/substring scoring
   - lightweight inverted index

## Reliability
7. Retry policy: attempts and backoff defaults?
8. Hard limits: max file size, max indexed files, max aggregate bytes?
9. How to expose rate-limit status in response metadata?

## Future
10. Private repos timeline and auth model (env token only)?
11. Multi-host expansion (GitLab/Bitbucket) required or not?
12. Should tool names be GitHub-specific forever or host-agnostic later?
