# Pull Request

### Scope
- Tasks: <!-- e.g., P0-01, P1-01 -->
- Modules: <!-- gateway, backend, lora, led, chuck, wizard, etc. -->

### Verify-first (attach evidence)
- [ ] Preflight ran for all listed tasks
- Evidence files updated: <!-- paths to plan/evidence/*.jsonl -->
- `last_verified_sha` updated in `plan/por.yaml` (when verifying)

### Acceptance
- [ ] Acceptance items in `plan/por.yaml` are met
- [ ] Preview→Apply→Restore proven (if writes occur)
- [ ] No direct filesystem writes from UI/gateway
- [ ] All API endpoints handle missing keys gracefully (501 NOT_CONFIGURED)
- [ ] UI shows appropriate offline/degraded state banners

### Testing
- [ ] Manual testing completed
- [ ] Evidence JSONL entries added for each task
- [ ] CI gate passes (plan-gate.yml)

### Breaking Changes
<!-- List any breaking changes and migration steps -->

### Additional Notes
<!-- Any additional context, screenshots, or concerns -->
