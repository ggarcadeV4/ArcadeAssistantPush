# Smoke checks

## Verify cache & backend health

- Windows PowerShell
  
  ```pwsh
  scripts\verify-cache.ps1
  ```

  Add `-NoStart` to verify an already running backend:

  ```pwsh
  scripts\verify-cache.ps1 -NoStart
  ```

- Bash / WSL

  ```bash
  bash scripts/verify-cache.sh
  ```

  Set `NOSTART=1` to verify an already running backend:

  ```bash
  NOSTART=1 bash scripts/verify-cache.sh
  ```

GREEN means:

- backend health OK
- LaunchBox XML glob found files
- games_count > 100 on `/api/launchbox/games?limit=200`

## Shortcuts

- Makefile

  ```sh
  make smoke            # auto-detects Windows/WSL/Linux
  make smoke-no-start   # verify without restarting backend
  make smoke-ps         # force PowerShell
  make smoke-sh         # force Bash
  make smoke-gateway    # gateway health + passthrough
  make smoke-gateway-no-start
  ```

- npm scripts

  ```sh
  npm run smoke                 # auto-detect
  npm run smoke:no-start        # verify without restart
  npm run smoke:ps              # PowerShell
  npm run smoke:ps:no-start
  npm run smoke:sh              # Bash
  npm run smoke:sh:no-start
  npm run smoke:gateway         # gateway health + passthrough
  npm run smoke:gateway:no-start
  ```

- VS Code tasks
  - Tasks: Run Task → Smoke (auto)
  - Tasks: Run Task → Smoke (no-start)
  - Tasks: Run Task → Gateway Smoke (start)
  - Tasks: Run Task → Gateway Smoke (no-start)
  - Tasks: Run Task → Stack Smoke (start)
  - Tasks: Run Task → Stack Smoke (no-start)

## To‑Do

See CODEX_CLAUDE_TODO.md for the shared Codex/Claude to‑dos (including the upcoming stack smoke runner acceptance and other polish items).
  - Tasks: Run Task → Smoke (PowerShell)
  - Tasks: Run Task → Smoke (Bash)

## Opt-in pre-commit guard

Install a local pre-commit hook that blocks commits on RED:

```sh
ln -s ../../scripts/pre-commit-smoke.sh .git/hooks/pre-commit
chmod +x scripts/pre-commit-smoke.sh
```

Windows (PowerShell alternative):

```pwsh
Copy-Item scripts\pre-commit-smoke.ps1 .git\hooks\pre-commit.ps1 -Force
```

Remove or rename the hook to disable.

## Git hooks (optional, local)

To enforce smoke before committing backend/scripts changes:

```bash
git config core.hooksPath scripts/githooks
chmod +x scripts/githooks/pre-commit
```

Disable anytime with:

```bash
git config --unset core.hooksPath
```
