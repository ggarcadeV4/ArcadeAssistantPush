// scripts/dev-backend.cjs
// Cross-platform backend starter that keeps the process alive
const { spawn } = require('child_process');
const path = require('path');

const isWindows = process.platform === 'win32';
const pythonCmd = isWindows ? 'python' : 'python3';

// Ensure we're in the project root
process.chdir(path.resolve(__dirname, '..'));

console.log(`Starting backend with ${pythonCmd} on ${process.platform}...`);

const backend = spawn(
  pythonCmd,
  ['-m', 'uvicorn', 'backend.app:app', '--reload', '--host', '127.0.0.1', '--port', '8000'],
  {
    stdio: 'inherit',
    shell: isWindows,
    cwd: process.cwd()
  }
);

backend.on('error', (err) => {
  console.error('Failed to start backend:', err);
  process.exit(1);
});

backend.on('exit', (code) => {
  console.log(`Backend exited with code ${code}`);
  process.exit(code || 0);
});

// Forward signals to cleanly shut down
process.on('SIGINT', () => {
  console.log('Received SIGINT, shutting down backend...');
  backend.kill('SIGINT');
});

process.on('SIGTERM', () => {
  console.log('Received SIGTERM, shutting down backend...');
  backend.kill('SIGTERM');
});
