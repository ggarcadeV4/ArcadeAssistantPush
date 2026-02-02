# LaunchBox LoRa Findings (XML vs Plugin)

Date: 2026-01-21

Summary (concise):
- LoRa listings and artwork come from LaunchBox XML, not the plugin.
- Backend parses LaunchBox XML (LaunchBoxParser) and image paths (ImageScanner), served via /api/launchbox/*.
- Frontend LoRa panel calls: /api/launchbox/games, /platforms, /genres, /stats, /image/{id}.
- Launching is handled by backend launcher with policy default "direct_only"; plugin is optional.
- Current diagnostics: plugin_available=false, allow_direct_effective=true, direct_is_healthy=true.
- Live check: /api/launchbox/games returns data even with plugin offline.
- Plugin at 127.0.0.1:9999 is not required for listings; only used for LaunchBox-native launching if enabled.

Evidence:
- docs/launchbox_lora_data_flow.md (data flow, endpoints, XML parsing)
- backend/routers/launchbox.py (launch policy defaults to direct_only)
- backend/services/launchbox_plugin_client.py (plugin at 127.0.0.1:9999)
- frontend/src/panels/launchbox/LaunchBoxPanel.jsx (plugin check is non-blocking)
- Diagnostics endpoint /api/launchbox/diagnostics/dry-run
