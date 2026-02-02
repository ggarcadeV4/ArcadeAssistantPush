// claude_boot.js
const fs = require("fs");
const path = require("path");

const STARTUP_FILES = [
  "docs/PROMETHEA_GUI_STYLE_GUIDE.md",
  "docs/UNIVERSAL_AGENT_RULES.md",
  "agents/CLAUDE_CREW.md",
  "agents/AGENT_CALL_MATRIX.md",
  "docs/CLOUD_STARTUP.md"
];

const LOG_PATH = `logs/agent_boot/claude_boot_${new Date().toISOString().replace(/[:.]/g, '-')}.log`;

function checkRequiredFiles() {
  let passed = true;
  let log = [`Claude Boot Log — ${new Date().toLocaleString()}\n`];

  for (const file of STARTUP_FILES) {
    if (fs.existsSync(file)) {
      log.push(`✔️ Found: ${file}`);
    } else {
      log.push(`❌ MISSING: ${file}`);
      passed = false;
    }
  }

  // Ensure log directory exists
  const logDir = path.dirname(LOG_PATH);
  if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
  }

  // Write boot log
  fs.writeFileSync(LOG_PATH, log.join("\n"), "utf-8");

  if (!passed) {
    console.error("🚨 Claude boot failed — one or more critical startup files missing.");
    console.error(`📋 See log: ${LOG_PATH}`);
    throw new Error("Claude environment validation failed.");
  }

  console.log("✅ Claude environment initialized successfully.");
  console.log(`📋 Boot log: ${LOG_PATH}`);
}

// Additional validation functions for later phases
function validateIndexFiles() {
  // TODO: Validate all index.json files via Lexicon
  // TODO: Check if DebugPanel is registered and rendered
  // TODO: Confirm PanelTemplate is present in all panels
  // TODO: Verify AGENT_CALL_MATRIX.md rules were followed in last PR
}

// Main boot sequence
try {
  checkRequiredFiles();
  // validateIndexFiles(); // Enable in later phases
} catch (error) {
  console.error("❌ Claude boot sequence failed:", error.message);
  process.exit(1);
}

module.exports = { checkRequiredFiles, validateIndexFiles };