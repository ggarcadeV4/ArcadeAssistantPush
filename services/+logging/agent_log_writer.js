// @service: agent_log_writer
// @role: Appends structured log lines to agent_calls log file

const fs = require('fs');
const path = require('path');

const LOG_DIR = "logs/agent_calls";

// Ensure log directory exists
if (!fs.existsSync(LOG_DIR)) {
  fs.mkdirSync(LOG_DIR, { recursive: true });
}

function logAgentEvent(message) {
  const now = new Date();
  const timestamp = now.toISOString().split('T')[0]; // YYYY-MM-DD
  const time = now.toTimeString().split(' ')[0].substring(0, 5); // HH:MM
  const logFile = path.join(LOG_DIR, `${timestamp}_agent_calls.log`);

  const entry = `[${time}] ${message}\n`;
  fs.appendFileSync(logFile, entry, 'utf8');
}

// Example usage:
// logAgentEvent("ClaudeCode called: Hera → panels/A1_GameTipsPanel");

module.exports = { logAgentEvent };