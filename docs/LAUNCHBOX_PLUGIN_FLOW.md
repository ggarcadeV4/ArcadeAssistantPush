# LaunchBox Plugin Flow Diagrams

## Launch Request Flow - Success Path

```
┌─────────────────────────────────────────────────────────────────────┐
│ USER clicks "Launch Game" in Frontend Panel                          │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ FRONTEND: Check cached plugin health (30s TTL)                       │
│ - If expired, fetch fresh health status                              │
│ - Block launch if plugin offline and no fallback                    │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ GATEWAY (8787): Route /api/launchbox/launch                         │
│ - Add device ID header                                              │
│ - Add timeout wrapper (5s)                                          │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ BACKEND (8888): LaunchManager.launch_game()                         │
│ - Step 1: Check plugin health                                       │
│ - Step 2: Attempt plugin launch                                     │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PLUGIN (31337): POST /launch                                        │
│ - Validate game ID format                                           │
│ - Lookup game in LaunchBox database                                 │
│ - Call PluginHelper.LaunchBoxMainViewModel.LaunchGame()            │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ LAUNCHBOX: Native launch sequence                                   │
│ - Load emulator configuration                                       │
│ - Verify ROM exists                                                 │
│ - Start emulator process with ROM                                   │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PLUGIN: Return success response                                     │
│ {                                                                    │
│   "launched": true,                                                 │
│   "method": "launchbox_native",                                     │
│   "process": { "pid": 12345, "started_at": "..." }                 │
│ }                                                                    │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ BACKEND → GATEWAY → FRONTEND                                        │
│ - Log metrics                                                       │
│ - Update UI state                                                   │
│ - Show success notification                                         │
└─────────────────────────────────────────────────────────────────────┘
```

## Fallback Chain - Plugin Offline

```
┌─────────────────────────────────────────────────────────────────────┐
│ BACKEND: Plugin health check FAILS                                  │
│ - Connection refused on 127.0.0.1:31337                            │
│ - OR timeout after 5 seconds                                       │
│ - OR unhealthy response                                            │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Decision: Is fallback_allowed = true?                               │
└───────────┬───────────────────────────────────┬─────────────────────┘
            ▼ NO                                ▼ YES
┌───────────────────────────┐      ┌─────────────────────────────────┐
│ Return 503 Service        │      │ Try WSL Interop Launch          │
│ Unavailable               │      │ - Check WSL availability        │
│ "Plugin required"         │      │ - Build interop command         │
└───────────────────────────┘      └───────────┬─────────────────────┘
                                               ▼
                                   ┌─────────────────────────────────┐
                                   │ WSL: /mnt/c/LaunchBox/          │
                                   │      LaunchBox.exe -play {id}   │
                                   └───────────┬─────────────────────┘
                                               ▼
                            ┌──────────────────┴──────────────────┐
                            ▼ SUCCESS                            ▼ FAIL
                ┌─────────────────────────┐        ┌─────────────────────┐
                │ Return with warning:    │        │ Return detailed     │
                │ "Launched via WSL -     │        │ error with          │
                │ some features limited"  │        │ troubleshooting     │
                └─────────────────────────┘        └─────────────────────┘
```

## Error Recovery Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ ERROR DETECTED at any stage                                         │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Classify Error Type:                                                │
│ - plugin_offline    → Suggest starting LaunchBox                    │
│ - game_not_found   → Show game browser                             │
│ - rom_missing      → Display ROM path and check instructions       │
│ - emulator_missing → Link to LaunchBox emulator setup              │
│ - permission_denied → Suggest running as administrator             │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Log Structured Error:                                               │
│ - Timestamp                                                         │
│ - Error type                                                        │
│ - Game ID attempted                                                 │
│ - Method attempted (plugin/wsl/direct)                              │
│ - Full error details                                                │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Frontend Error Display:                                             │
│ ┌─────────────────────────────────────────────┐                    │
│ │ ⚠️ Launch Failed                              │                    │
│ │                                               │                    │
│ │ Game could not be started.                   │                    │
│ │                                               │                    │
│ │ Reason: LaunchBox plugin not responding      │                    │
│ │                                               │                    │
│ │ Solutions:                                    │                    │
│ │ • Ensure LaunchBox is running                │                    │
│ │ • Check plugin installed in Plugins folder   │                    │
│ │ • Restart LaunchBox and try again           │                    │
│ │                                               │                    │
│ │ [Try Again] [Use Fallback] [Cancel]          │                    │
│ └─────────────────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────────┘
```

## Health Check Sequence

```
┌─────────────────────────────────────────────────────────────────────┐
│ Frontend Panel Mount OR 30-second interval                          │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ GET /api/launchbox/plugin/health                                    │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Backend: PluginHTTPClient.health_check()                            │
│                                                                      │
│ for attempt in range(3):  # Retry logic                            │
│     try:                                                            │
│         response = GET http://127.0.0.1:31337/health               │
│         if response.status == 200:                                 │
│             return response.json()                                 │
│     except:                                                        │
│         sleep(1)  # Wait before retry                              │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
                ┌───────────┴───────────┐
                ▼                       ▼
    ┌─────────────────────┐   ┌─────────────────────┐
    │ Plugin Responds     │   │ Plugin Timeout      │
    │ Status: ONLINE      │   │ Status: OFFLINE     │
    │ Cache for 30s       │   │ Cache for 5s        │
    └─────────────────────┘   └─────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Update Frontend Status Indicator:                                   │
│ 🟢 Online - Ready to launch                                         │
│ 🔴 Offline - LaunchBox plugin not available                        │
│ 🟡 Checking - Verifying connection...                              │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

```
┌─────────────────────────────────────────────────────────────────────┐
│                        COMPONENT MATRIX                              │
├─────────────────┬────────────────────────────────────────────────────┤
│ Frontend Panel  │ • Display launch button with status               │
│                 │ • Show plugin health indicator                    │
│                 │ • Cache health status (30s)                       │
│                 │ • Display errors with solutions                   │
│                 │ • Block launch when plugin required              │
├─────────────────┼────────────────────────────────────────────────────┤
│ Gateway         │ • Route requests to backend                        │
│                 │ • Add security headers                             │
│                 │ • Implement request timeout                        │
│                 │ • Log all launch attempts                         │
├─────────────────┼────────────────────────────────────────────────────┤
│ Backend         │ • Manage plugin client connection                  │
│                 │ • Implement retry logic                            │
│                 │ • Execute fallback chain                           │
│                 │ • Format error messages                            │
│                 │ • Track metrics and performance                    │
├─────────────────┼────────────────────────────────────────────────────┤
│ Plugin          │ • Listen on 127.0.0.1:31337                       │
│                 │ • Validate game IDs                                │
│                 │ • Interface with LaunchBox API                     │
│                 │ • Return structured responses                      │
│                 │ • Handle concurrent requests                       │
├─────────────────┼────────────────────────────────────────────────────┤
│ LaunchBox       │ • Maintain game database                           │
│                 │ • Configure emulators                              │
│                 │ • Launch game processes                            │
│                 │ • Manage ROM paths                                  │
└─────────────────┴────────────────────────────────────────────────────┤
```

## State Transitions

```
     ┌─────────┐
     │ IDLE    │
     └────┬────┘
          │ User clicks launch
          ▼
     ┌─────────┐
     │CHECKING │ ← Health check in progress
     └────┬────┘
          │
    ┌─────┴─────┐
    ▼           ▼
┌─────────┐ ┌─────────┐
│ READY   │ │DEGRADED │
│         │ │         │
│ Plugin  │ │ Plugin  │
│ Online  │ │ Offline │
└────┬────┘ └────┬────┘
     │           │
     │ Launch    │ Launch with
     │ via       │ fallback
     │ plugin    │
     ▼           ▼
┌─────────┐ ┌─────────┐
│LAUNCHING│ │WARNING  │
└────┬────┘ └────┬────┘
     │           │
     ▼           ▼
┌─────────┐ ┌─────────┐
│SUCCESS  │ │ ERROR   │
│         │ │         │
│ Game    │ │ Show    │
│ Running │ │ Details │
└─────────┘ └─────────┘
```

## Performance Timeline

```
Time (ms)    Action
---------    ------
0            User clicks launch button
10           Frontend checks cached health (hit/miss)
15           [MISS] Request health from gateway
50           Backend queries plugin health
55           Plugin responds with status
60           Health status returned to frontend
65           Frontend validates can launch
70           Frontend sends launch request
75           Gateway routes to backend
80           Backend sends to plugin
100          Plugin validates game ID
120          Plugin calls LaunchBox API
150          LaunchBox starts emulator
200          Plugin returns success
210          Backend logs metrics
220          Gateway returns to frontend
230          Frontend shows success state
250          Frontend updates recent games

Total: ~250ms optimal path
Timeout: 5000ms maximum wait
```