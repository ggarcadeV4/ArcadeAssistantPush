# Gateway Check — Console Wizard Restore

- The gateway's local proxy (gateway/routes/localProxy.js) forwards /api/local/... calls to FastAPI and preserves the request headers. Header enforcement already requires x-scope for mutating requests, so Console Wizard must send x-scope=config.
- Because the proxy forwards x-device-id and x-panel verbatim, the Console Wizard UI now always supplies x-panel=console-wizard when calling preview/apply/restore.
- No gateway changes were required for this session; documentation captured here simply records the verification of existing behavior.
