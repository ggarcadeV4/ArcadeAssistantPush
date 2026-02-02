# 📊 Agent Boot Logging Specification

**Status:** Authoritative
**Purpose:** Define standardized logging format for agent initialization
**Location:** /docs/AGENT_BOOT_LOGGING.md
**Log Path:** `/logs/agents/boot-YYYYMMDD.jsonl`

---

## 📁 Log File Structure

### Directory Organization
```
/logs/
├── agents/
│   ├── boot-20251012.jsonl    # Daily boot logs (JSONL format)
│   └── boot-20251013.jsonl
├── agent_calls/
│   ├── 20251012_calls.log     # Task execution logs
│   └── 20251013_calls.log
└── agent_boot/
    ├── claude_boot_*.log       # Legacy boot logs (text format)
    └── ...
```

### File Naming Convention
- **Boot logs:** `boot-YYYYMMDD.jsonl` (one file per day)
- **Call logs:** `YYYYMMDD_calls.log` (one file per day)
- **Rollover:** New file created at midnight UTC

---

## 📝 JSONL Log Format

Each line is a valid JSON object with standardized fields:

### Boot Event Schema
```json
{
  "timestamp": "2025-10-12T14:23:01.234Z",
  "level": "INFO|WARN|ERROR",
  "event": "agent_boot|agent_ready|agent_failed",
  "agent": "Lexicon|Promethea|Hera|...",
  "details": {
    "status": "initialized|ready|failed",
    "files_indexed": 247,
    "guidelines_loaded": true,
    "error": null
  },
  "session_id": "uuid-v4",
  "version": "1.0.0"
}
```

### Field Definitions

**Required Fields:**
- `timestamp` - ISO 8601 timestamp with milliseconds
- `level` - Log level (INFO, WARN, ERROR)
- `event` - Event type identifier
- `agent` - Agent name from CLAUDE_CREW.md

**Optional Fields:**
- `details` - Agent-specific metadata object
- `session_id` - Unique session identifier
- `version` - Agent version number
- `error` - Error message if applicable

---

## 🎯 Event Types

### Boot Sequence Events
```json
{"event": "boot_start", "details": {"required_agents": ["Lexicon", "Promethea", "Hera"]}}
{"event": "agent_boot", "agent": "Lexicon", "details": {"status": "initializing"}}
{"event": "agent_ready", "agent": "Lexicon", "details": {"files_indexed": 247}}
{"event": "boot_complete", "details": {"agents_loaded": 11, "duration_ms": 1234}}
```

### Error Events
```json
{"event": "agent_failed", "agent": "Oracle", "level": "ERROR", "error": "Config file not found"}
{"event": "boot_failed", "level": "ERROR", "error": "Required agents not available"}
```

### Validation Events
```json
{"event": "validation_start", "details": {"checks": ["files", "permissions", "dependencies"]}}
{"event": "validation_passed", "details": {"check": "files", "count": 5}}
{"event": "validation_failed", "details": {"check": "permissions", "error": "Write access denied"}}
```

---

## 💻 Implementation Examples

### Python Logger
```python
import json
import logging
from datetime import datetime
from pathlib import Path

class AgentBootLogger:
    def __init__(self):
        self.log_dir = Path("logs/agents")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, event, agent=None, level="INFO", **details):
        today = datetime.now().strftime("%Y%m%d")
        log_file = self.log_dir / f"boot-{today}.jsonl"

        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "event": event,
            "agent": agent,
            "details": details
        }

        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

# Usage
logger = AgentBootLogger()
logger.log("agent_boot", agent="Lexicon", status="initializing")
logger.log("agent_ready", agent="Lexicon", files_indexed=247)
```

### JavaScript Logger
```javascript
const fs = require('fs');
const path = require('path');

class AgentBootLogger {
    constructor() {
        this.logDir = path.join('logs', 'agents');
        if (!fs.existsSync(this.logDir)) {
            fs.mkdirSync(this.logDir, { recursive: true });
        }
    }

    log(event, agent = null, level = 'INFO', details = {}) {
        const today = new Date().toISOString().split('T')[0].replace(/-/g, '');
        const logFile = path.join(this.logDir, `boot-${today}.jsonl`);

        const entry = {
            timestamp: new Date().toISOString(),
            level,
            event,
            agent,
            details
        };

        fs.appendFileSync(logFile, JSON.stringify(entry) + '\n');
    }
}

// Usage
const logger = new AgentBootLogger();
logger.log('agent_boot', 'Promethea', 'INFO', { status: 'initializing' });
logger.log('agent_ready', 'Promethea', 'INFO', { guidelines_loaded: true });
```

---

## 🔍 Log Analysis

### Query Examples

**Find all errors:**
```bash
grep '"level":"ERROR"' logs/agents/boot-20251012.jsonl | jq
```

**Check specific agent:**
```bash
grep '"agent":"Lexicon"' logs/agents/boot-20251012.jsonl | jq
```

**Get boot duration:**
```bash
grep -E '"event":"boot_(start|complete)"' logs/agents/boot-20251012.jsonl | jq '.timestamp'
```

**Count ready agents:**
```bash
grep '"event":"agent_ready"' logs/agents/boot-20251012.jsonl | wc -l
```

### Log Rotation
- Keep 30 days of logs
- Compress logs older than 7 days
- Archive to `logs/agents/archive/` after 30 days

---

## 📊 Monitoring & Alerts

### Key Metrics
- **Boot Duration:** Time from boot_start to boot_complete
- **Agent Availability:** Count of agent_ready events
- **Error Rate:** ERROR level events per boot
- **Validation Success:** Ratio of passed to failed validations

### Alert Conditions
- Boot duration > 5 seconds
- Any agent_failed event
- Missing required agents
- Validation failures

---

## 🔄 Migration from Legacy Format

### Legacy Format (text)
```
Claude Boot Log — 2025-10-12 14:23:01
✔️ Found: docs/PROMETHEA_GUI_STYLE_GUIDE.md
✔️ Found: agents/CLAUDE_CREW.md
❌ MISSING: docs/CLOUD_STARTUP.md
```

### New Format (JSONL)
```json
{"timestamp": "2025-10-12T14:23:01Z", "event": "boot_start"}
{"timestamp": "2025-10-12T14:23:01Z", "event": "file_check", "details": {"file": "docs/PROMETHEA_GUI_STYLE_GUIDE.md", "found": true}}
{"timestamp": "2025-10-12T14:23:01Z", "event": "file_check", "details": {"file": "agents/CLAUDE_CREW.md", "found": true}}
{"timestamp": "2025-10-12T14:23:01Z", "event": "file_check", "level": "ERROR", "details": {"file": "docs/CLOUD_STARTUP.md", "found": false}}
```

---

## 📚 Related Documentation
- `CLAUDE_CREW.md` - Agent definitions and boundaries
- `AGENT_CALL_MATRIX.md` - Task delegation rules
- `CLOUD_STARTUP.md` - Boot sequence requirements