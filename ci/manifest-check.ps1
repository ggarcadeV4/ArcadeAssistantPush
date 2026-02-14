Param()
$ErrorActionPreference = "Stop"

Write-Host "[CI] Backend manifest validation"
try {
  python - <<'PY'
import sys
try:
    from backend.policies.manifest_validator import validate_on_startup
except Exception as e:
    print(f"Failed to import backend validator: {e}")
    sys.exit(78)
validate_on_startup(None)
print("Backend manifest validation: OK")
PY
} catch {
  Write-Error "Backend manifest validation failed"
  exit 78
}

Write-Host "[CI] Gateway manifest validation"
try {
  node --input-type=module - <<'JS'
import { loadManifest, validateManifest } from './gateway/policies/manifestValidator.js'
try {
  const m = await loadManifest()
  const errs = validateManifest(m)
  if (errs.length) {
    console.error('Gateway manifest errors:', errs)
    process.exit(78)
  }
  console.log('Gateway manifest validation: OK')
} catch (e) {
  console.error('Failed to load/validate gateway manifest:', e?.message || e)
  process.exit(78)
}
JS
} catch {
  Write-Error "Gateway manifest validation failed"
  exit 78
}

Write-Host "All manifest checks passed"
exit 0
