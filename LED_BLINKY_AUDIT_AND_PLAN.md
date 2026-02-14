ROLE: Read-only auditor and documentation generator.  
DO NOT modify any code. This document is the authoritative reference for all LED Blinky work.

---

# LED_BLINKY_AUDIT_AND_PLAN

## 1. UI -> Handler -> Backend Route Matrix

### JSON Matrix

```
[
  {
    "tab": "Game Profiles",
    "control_label": "Game Profiles tab button",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:892",
    "handler": "setActiveMode('profiles') (frontend/src/components/LEDBlinkyPanel.jsx:225)",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "Sets local state."
    },
    "status": "active"
  },
  {
    "tab": "Animation Designer",
    "control_label": "Animation Designer tab button",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:892",
    "handler": "setActiveMode('animation') (frontend/src/components/LEDBlinkyPanel.jsx:225)",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "Local state toggle."
    },
    "status": "active"
  },
  {
    "tab": "Real-time Control",
    "control_label": "Real-time Control tab button",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:892",
    "handler": "setActiveMode('realtime') (frontend/src/components/LEDBlinkyPanel.jsx:225)",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "Local state toggle."
    },
    "status": "active"
  },
  {
    "tab": "Hardware",
    "control_label": "Hardware tab button",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:892",
    "handler": "setActiveMode('hardware') (frontend/src/components/LEDBlinkyPanel.jsx:225)",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "Local state toggle."
    },
    "status": "active"
  },
  {
    "tab": "Shared",
    "control_label": "Shared tab (spec-only)",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:892",
    "handler": "N/A (mode list omits shared)",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "Spec references Shared tab but UI omits button."
    },
    "status": "missing"
  },
  {
    "tab": "Shared",
    "control_label": "Arcade Panel Layout buttons (P1- P4, start/select)",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:963",
    "handler": "toggleLED -> LEDWebSocketManager.sendLEDCommand (frontend/src/components/LEDBlinkyPanel.jsx:395 & :151)",
    "api_call": {
      "method": "WebSocket",
      "url": "User-provided ws://... (LEDWebSocketManager.connect)",
      "headers": "Raw WS (no x-scope/x-panel)",
      "through_gateway": false,
      "notes": "Direct hardware commands."
    },
    "status": "active"
  },
  {
    "tab": "Shared",
    "control_label": "Test All (Quick Controls)",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1263",
    "handler": "testAllLEDs + testLED fetch (frontend/src/components/LEDBlinkyPanel.jsx:425 & frontend/src/services/ledBlinkyClient.js:22)",
    "api_call": {
      "method": "POST",
      "url": "/api/local/led/test",
      "headers": "{'Content-Type':'application/json','x-device-id':resolveDeviceId(),'x-panel':'led','x-scope':'local'}",
      "through_gateway": true,
      "notes": "Gateway to FastAPI /led/test plus WebSocket sweep."
    },
    "status": "active"
  },
  {
    "tab": "Shared",
    "control_label": "Clear",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1274",
    "handler": "clearAllLEDs (frontend/src/components/LEDBlinkyPanel.jsx:410)",
    "api_call": {
      "method": "WebSocket",
      "url": "User-provided ws://...",
      "headers": "Raw WS",
      "through_gateway": false,
      "notes": "Bypasses PreviewApply."
    },
    "status": "active"
  },
  {
    "tab": "Shared",
    "control_label": "Random",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1277",
    "handler": "randomPattern (frontend/src/components/LEDBlinkyPanel.jsx:440)",
    "api_call": {
      "method": "WebSocket",
      "url": "User-provided ws://...",
      "headers": "Raw WS",
      "through_gateway": false,
      "notes": "sendPattern('random')."
    },
    "status": "active"
  },
  {
    "tab": "Shared",
    "control_label": "Wave",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1280",
    "handler": "None",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "Dead control."
    },
    "status": "dead"
  },
  {
    "tab": "Shared",
    "control_label": "LED Brightness slider",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1285",
    "handler": "setLedBrightness + wsManagerRef.sendPattern('brightness') (frontend/src/components/LEDBlinkyPanel.jsx:230 & :169)",
    "api_call": {
      "method": "WebSocket",
      "url": "User-provided ws://...",
      "headers": "Raw WS",
      "through_gateway": false,
      "notes": "No gateway enforcement."
    },
    "status": "active"
  },
  {
    "tab": "Shared",
    "control_label": "Save Configuration",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1990",
    "handler": "None",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "Not wired."
    },
    "status": "dead"
  },
  {
    "tab": "Shared",
    "control_label": "Export",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:2002",
    "handler": "None",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "Not wired."
    },
    "status": "dead"
  },
  {
    "tab": "Shared",
    "control_label": "Save Pattern",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:2014",
    "handler": "savePattern (frontend/src/components/LEDBlinkyPanel.jsx:453)",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "LocalStorage only."
    },
    "status": "active"
  },
  {
    "tab": "Shared",
    "control_label": "Load Pattern",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:2033",
    "handler": "loadPattern (frontend/src/components/LEDBlinkyPanel.jsx:468)",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "LocalStorage replay."
    },
    "status": "active"
  },
  {
    "tab": "Game Profiles",
    "control_label": "Game Selection dropdown",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1410",
    "handler": "applyGameProfile (frontend/src/components/LEDBlinkyPanel.jsx:496)",
    "api_call": {
      "method": "WebSocket",
      "url": "User-provided ws://...",
      "headers": "Raw WS",
      "through_gateway": false,
      "notes": "sendPattern('game_profile')."
    },
    "status": "active"
  },
  {
    "tab": "Animation Designer",
    "control_label": "Profile list fetch",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:285",
    "handler": "listLEDProfiles effect",
    "api_call": {
      "method": "GET",
      "url": "/api/local/led/profiles",
      "headers": "{'x-device-id':resolveDeviceId(),'x-panel':'led','x-scope':'local'}",
      "through_gateway": true,
      "notes": "FastAPI /led/profiles."
    },
    "status": "active"
  },
  {
    "tab": "Animation Designer",
    "control_label": "LED Profile Library dropdown",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1618",
    "handler": "handleLoadProfile -> getLEDProfile",
    "api_call": {
      "method": "GET",
      "url": "/api/local/led/profiles/{profile}",
      "headers": "{'x-device-id':resolveDeviceId(),'x-panel':'led','x-scope':'local'}",
      "through_gateway": true,
      "notes": "FastAPI /led/profiles/{name}."
    },
    "status": "active"
  },
  {
    "tab": "Animation Designer",
    "control_label": "Color pickers",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1696",
    "handler": "setButtonColor",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "Local state."
    },
    "status": "active"
  },
  {
    "tab": "Animation Designer",
    "control_label": "Advanced JSON editor",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1805",
    "handler": "setMappingData",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "Local state."
    },
    "status": "active"
  },
  {
    "tab": "Animation Designer",
    "control_label": "Preview Changes",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1917",
    "handler": "handlePreviewMapping -> previewLEDMapping",
    "api_call": {
      "method": "POST",
      "url": "/api/local/led/mapping/preview",
      "headers": "{'Content-Type':'application/json','x-device-id':resolveDeviceId(),'x-panel':'led','x-scope':'local'}",
      "through_gateway": true,
      "notes": "FastAPI /led/mapping/preview diff."
    },
    "status": "active"
  },
  {
    "tab": "Animation Designer",
    "control_label": "Apply Mapping",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1935",
    "handler": "handleApplyMapping -> applyLEDMapping",
    "api_call": {
      "method": "POST",
      "url": "/api/local/led/mapping/apply",
      "headers": "{'Content-Type':'application/json','x-device-id':deviceId,'x-panel':'led-blinky','x-scope':'config'}",
      "through_gateway": true,
      "notes": "FastAPI /led/mapping/apply (backup+log)."
    },
    "status": "active"
  },
  {
    "tab": "Real-time Control",
    "control_label": "Info copy",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1967",
    "handler": "Informational",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "Explains layout usage."
    },
    "status": "informational"
  },
  {
    "tab": "Hardware",
    "control_label": "WebSocket URL input",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1521",
    "handler": "setWebsocketUrl",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "Local state."
    },
    "status": "active"
  },
  {
    "tab": "Hardware",
    "control_label": "Connect / Disconnect",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1504",
    "handler": "toggleWebSocketConnection -> LEDWebSocketManager.connect/disconnect",
    "api_call": {
      "method": "WebSocket",
      "url": "User-provided ws://...",
      "headers": "Raw WS (no x-scope)",
      "through_gateway": false,
      "notes": "Completely bypasses gateway."
    },
    "status": "active"
  },
  {
    "tab": "Hardware",
    "control_label": "Hardware Test - All LEDs On",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1585",
    "handler": "testAllLEDs",
    "api_call": {
      "method": "WebSocket",
      "url": "User-provided ws://...",
      "headers": "Raw WS",
      "through_gateway": false,
      "notes": "Same as Quick Controls."
    },
    "status": "active"
  },
  {
    "tab": "Hardware",
    "control_label": "Hardware Test - All LEDs Off",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1586",
    "handler": "clearAllLEDs",
    "api_call": {
      "method": "WebSocket",
      "url": "User-provided ws://...",
      "headers": "Raw WS",
      "through_gateway": false,
      "notes": "Direct hardware off."
    },
    "status": "active"
  },
  {
    "tab": "Hardware",
    "control_label": "Hardware Test - Chase Pattern",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1587",
    "handler": "None",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "Dead."
    },
    "status": "dead"
  },
  {
    "tab": "Hardware",
    "control_label": "Hardware Test - Rainbow Test",
    "component": "frontend/src/components/LEDBlinkyPanel.jsx:1588",
    "handler": "None",
    "api_call": {
      "method": null,
      "url": null,
      "headers": null,
      "through_gateway": false,
      "notes": "Dead."
    },
    "status": "dead"
  },
  {
    "tab": "Shared",
    "control_label": "LED Assistant Chat send",
    "component": "frontend/src/panels/led-blinky/ChatBox.jsx:18",
    "handler": "useBlinkyChat.send -> aiClient.chat (frontend/src/panels/led-blinky/useBlinkyChat.js:7 & frontend/src/services/aiClient.js:8)",
    "api_call": {
      "method": "POST",
      "url": "/api/ai/chat",
      "headers": "{'content-type':'application/json','x-scope':'state','x-device-id':deviceId}",
      "through_gateway": true,
      "notes": "Gateway AI route (gateway/routes/ai.js:8)."
    },
    "status": "active"
  }
]
```

### Summary (Readable)
- Tabs are local-state toggles.
- All mapping/profile CRUD uses /api/local/led/* via ledBlinkyClient.
- Real-time LED control, brightness, and hardware tests bypass the gateway through a raw WebSocket.
- Several UI buttons (Wave, Save Configuration, Export, Hardware Chase/Rainbow, spec'd Shared tab) lack handlers.

---

## 2. Unsafe or Violating Behavior (Callouts)

| Type | File:Line | Description |
| --- | --- | --- |
| Raw WebSocket bypass (no headers, no preview/apply) | rontend/src/components/LEDBlinkyPanel.jsx:35-197 | LEDWebSocketManager.connect, .sendLEDCommand, .sendPattern send direct hardware frames with no x-scope, x-panel, x-device-id. |
| Raw WebSocket bypass from Arcade Layout | rontend/src/components/LEDBlinkyPanel.jsx:395-408 | 	oggleLED sends hardware commands outside gateway. |
| Raw WebSocket bypass from Clear/Test/Random | rontend/src/components/LEDBlinkyPanel.jsx:410-451 | clearAllLEDs, 	estAllLEDs, 
andomPattern use WebSocket only (no PreviewApply). |
| Raw WebSocket bypass from brightness slider | rontend/src/components/LEDBlinkyPanel.jsx:1285-1325 | input[type=range] calls wsManagerRef.current?.sendPattern('brightness', ...). |
| Raw WebSocket bypass from Game Profiles | rontend/src/components/LEDBlinkyPanel.jsx:496-520 | pplyGameProfile dispatches sendPattern('game_profile'). |
| Raw WebSocket bypass from Hardware tab | rontend/src/components/LEDBlinkyPanel.jsx:1504-1588 | Connect/Disconnect, All LEDs On/Off use WebSocket only. |
| Missing mandatory headers | rontend/src/components/LEDBlinkyPanel.jsx:35-197 | All WebSocket requests miss x-scope, x-device-id, x-panel. |
| PreviewApplyBackupLog violated | rontend/src/components/LEDBlinkyPanel.jsx:453-494 | savePattern/loadPattern write localStorage and alter LEDs with no backend preview/apply. |
| Direct http://localhost:8000 calls | None detected inside LED Blinky codepath (all HTTP uses /api/local/...). |
| Physical pin/channel references | None detected; all LED identifiers are logical player-button. |

---

## 3. Chuck LED Cascade Enforcement Notes

- config/mappings/controls.json (Chuck) is the sole writer for logical-to-physical mappings; LED Blinky must treat it as read-only.  
- LED Blinky UI and backend must only reference logical button names (player.button).  
- A dedicated LEDMappingService must resolve logical controls to physical pins internally; UI must never reference pins.  
- Any attempt to modify wiring, pin assignments, or bypass controls.json is a structural bug.  
- All LED profile data (configs/ledblinky/profiles/*.json) must store logical keys only (no device/pin metadata).  
- Violations must trigger an audit note and block merges until resolved.

---

## 4. LED Mapping Service Requirements (Session 2 Prerequisites)

Before Session 2 coding starts, ensure:

1. **Backend service file:** ackend/services/led_mapping_service.py housing:
   - class LEDMappingService with methods preview(mapping: LEDMapping) and pply(mapping: LEDMapping, request: Request).
   - Access to Chuck's logical mapping + physical wiring table (read-only).
2. **Preview endpoint behavior:**
   - /api/local/led/mapping/preview uses the service to merge logical mapping, load existing JSON, generate diffs via compute_diff, and return has_changes, 	arget_file, diff, resolved logical mapping.
   - Default dry-run (no writes).
3. **Apply endpoint behavior:**
   - /api/local/led/mapping/apply enforces 
equire_scope(..., 'config'), calls LEDMappingService.apply, writes to sanctioned path, creates backup via create_backup, logs to /logs/changes.jsonl.
4. **Sanctioned paths:** Validate against manifest["sanctioned_paths"] before writing to configs/ledblinky/profiles.
5. **Dry-run default:** Unless x-preview: false (future), operations should preview first; apply must prove previewed diff matches.
6. **Pydantic models:** Extend with typed responses such as LEDPreviewResponse and LEDApplyResponse to capture 	arget_file, diff, ackup_path.

---

## 5. Required Gateway Proxy Additions

Add explicit routes under /api/local/led/* (via gateway/routes/localProxy.js or a dedicated router) to ensure audit headers and manifest checks:

| Route | Behavior |
| --- | --- |
| POST /api/local/led/profile/preview | Proxy to FastAPI /led/profile/preview. |
| POST /api/local/led/profile/apply | Proxy to /led/profile/apply, enforcing x-scope=config. |
| POST /api/local/led/test | Already proxied but middleware must inject x-panel=led-blinky. |
| GET /api/local/led/devices | List LED hardware info (new FastAPI endpoint). |
| GET /api/local/led/status | Return LED service health and connection log. |
| GET/POST /api/local/led/ws | Gateway-managed WebSocket endpoint that enforces headers and proxies to hardware. |

All new routes must pass x-scope, x-device-id, x-panel, x-corr-id and rely on the preview/apply pipeline.

---

## 6. Required Frontend Refactors

- Remove direct WebSocket URLs: replace user-entered ws:// with gateway-managed wss://localhost:8787/api/local/led/ws?device=<id>.
- Centralize API usage: use ledBlinkyClient (and new helpers) for all Quick Controls, Game Profiles, and Hardware interactions.
- Headers: ensure x-scope=local for reads, x-scope=config for mapping writes, and x-scope=state for AI/chat operations.
- Hide or disable UI controls until backend support exists (Shared tab button, Wave, Save Configuration, Export, Hardware Chase/Rainbow).
- Preview vs Apply: disable Apply until a successful preview response; hardware/pattern actions should also go through preview endpoints where possible.
- Pattern Save/Load should call backend endpoints instead of localStorage once they exist.

---

## 7. Hardware Tab Requirements

1. Connect button must request a gateway-issued WebSocket URL/token (via /api/local/led/status) and open the socket only through the gateway so headers are enforced.
2. Hardware activity logs should be returned by /api/local/led/status or an SSE stream; the UI should render that data instead of WebSocket console logs.
3. Hardware tests (All On/Off, Chase, Rainbow) must call REST endpoints (POST /api/local/led/test, /api/local/led/pattern/run, etc.) so that PreviewApplyBackupLog rules record every action.
4. When the panel unmounts or the user disconnects, call a gateway endpoint to close the socket and update the log (no orphan connections).

---

## 8. SESSION 2 IMPLEMENTATION PLAN FOR CODEX

**Backend tasks**
1. Create ackend/services/led_mapping_service.py with:
   `python
   class LEDMappingService:
       def __init__(self, drive_root: Path, manifest: dict):
           ...
       def preview(self, mapping: LEDMapping) -> LEDPreviewResponse:
           ...
       def apply(self, request: Request, mapping: LEDMapping) -> LEDApplyResponse:
           ...
   `
2. Update ackend/routers/led_blinky.py to use the service for /mapping/preview, /mapping/apply, and add /profile/preview, /profile/apply, /devices, /status, plus a WebSocket route (or integration with an existing hardware daemon).
3. Enforce 
equire_scope, sanctioned path checks, backups, and /logs/changes.jsonl logging for every mutation.
4. Add unit tests under 	ests/backend/led_blinky/test_led_mapping_service.py covering preview/apply (including dry-run, missing game handling, backup creation, log content).

**Gateway tasks**
1. Register new /api/local/led/* routes with middleware that validates x-scope, x-panel, and x-device-id before proxying to FastAPI.
2. Implement a WebSocket proxy under /api/local/led/ws that hands out signed URLs, injects headers, forwards messages, and records connect/disconnect events.

**Frontend tasks**
1. Refactor rontend/src/components/LEDBlinkyPanel.jsx to remove direct WebSocket usage; rely on a new hardware client that talks to the gateway endpoints.
2. Extend rontend/src/services/ledBlinkyClient.js with helpers such as previewLEDProfile, pplyLEDProfile, listLEDDevices, getLEDStatus, 
unLEDTest, and connectHardwareSocket.
3. Update Quick Controls, Game Profiles, Animation Designer, and Hardware tab controls to call the new helpers and respect preview-before-apply rules.
4. Update Save/Load Pattern buttons to call backend APIs (disable until available).

**Acceptance tests**
- Backend: pytest -q backend/tests/led_blinky verifying preview/apply diff output, backup path creation, and logs.
- Gateway: integration test ensuring /api/local/led/mapping/preview refuses requests missing headers, and /api/local/led/ws rejects missing x-panel.
- Frontend: Jest/Cypress checks that Apply Mapping stays disabled until Preview succeeds and that Quick Controls use the REST client.
- Manual hardware test: confirm WebSocket connections now originate from wss://localhost:8787/api/local/led/ws and appear in /logs/changes.jsonl.

**Safety requirements**
- No writes outside sanctioned manifest paths.
- Every mutation must log to /logs/changes.jsonl with x-device-id, x-panel, and backup info.
- WebSocket connections must be mediated through the gateway; direct ws://localhost:8080 connections are prohibited.
- Preview endpoints must be idempotent and never write to disk.

---

## 9. Session 1 Evidence Appendix

- rontend/src/components/LEDBlinkyPanel.jsx lines 1-2072 (entire UI)
- rontend/src/panels/led-blinky/ChatBox.jsx lines 1-60
- rontend/src/panels/led-blinky/useBlinkyChat.js lines 1-33
- rontend/src/services/ledBlinkyClient.js lines 1-76
- ackend/routers/led_blinky.py lines 1-372
- gateway/routes/localProxy.js lines 1-113
- Additional references: Quick Controls (lines 1253-1336), Mapping handlers (lines 579-661), Mode switcher (lines 892-919), Hardware tab (lines 1460-1589)

These references underpin all findings and ensure nothing from Session 1 is omitted.

---

## 10. Session 5 Implementation Notes (Backend LED Mapping Hardening)

- **Service ownership:** `backend/services/led_mapping_service.py` now wraps the entire Chuck → LED cascade. It loads `config/mappings/controls.json` via `MappingDictionaryService`, resolves logical buttons to `LedChannel` lists, emits unified diffs, and enforces sanctioned write targets under `configs/ledblinky/profiles/`. Preview is read-only; apply respects `dry_run`, runs `create_backup(...)`, and writes JSON containing only logical button settings + metadata (no device/channel).
- **Router integration:** `/api/local/led/profile/*` (`backend/routers/led.py`) and `/api/local/led/mapping/*` (`backend/routers/led_blinky.py`) instantiate `LEDMappingService` from `request.app.state.drive_root/manifest`. Both preview routes surface resolved channels for UI debugging, while apply routes require `x-scope: config`, honor dry-run defaults, and append audit entries to `logs/changes.jsonl` with the gateway-provided headers plus `{target_file, status, backup_path}`.
- **Safety proof points:** Stored profile files now serialize `buttons`, `metadata`, and optional `animation`/`game` fields—physical pin metadata never persists. Because the service always reads Chuck’s dictionary before resolving, updating `controls.json` automatically shifts which physical LEDs fire on the very next preview/apply without touching profile JSON.
- **Tests:** `backend/tests/test_led_mapping_service.py` exercises the service + FastAPI wiring. Coverage includes logical→physical resolution (verifying a resolved channel index from sample controls), dry-run vs. write semantics, backup/log creation, and confirmation that stored profiles remain logical-only. Run with `python -m pytest backend/tests/test_led_mapping_service.py`.
