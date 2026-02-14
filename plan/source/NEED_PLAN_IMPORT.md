# Plan Import Needed

**Status**: Awaiting source plan document
**Date**: 2025-10-23
**Planner**: Claude Code (Ability Pack planner role)

## Expected Source Documents

Looking for any of:
- `plan/source/ARCADE_ASSISTANT_COMPLETION_PLAN_2025-10-23.md`
- `docs/ARCADE_ASSISTANT_COMPLETION_PLAN_2025-10-23.md`
- `ARCADE_ASSISTANT_COMPLETION_PLAN 10-23-2025.md`

## Current Status

**Search Result**: No matching plan documents found in repository.

**Action Taken**: Retained seed tasks in `plan/por.yaml`:
- P0-01: 501 NOT_CONFIGURED when AI/TTS/STT keys are missing (gateway)
- P0-02: Enforce Preview→Apply→Restore for all writes (backend)
- P1-01: Decide→Plan→Spawn with single-flight lock (launch_orchestrator)

## To Import Full Plan

1. Place the completion plan document in one of the expected locations
2. Re-run the planner agent with the import task
3. The planner will:
   - Parse headings into phases (P0..P7)
   - Generate stable task IDs (Phase-NN format)
   - Extract checkable acceptance criteria
   - Assign module tags
   - Create evidence file stubs
   - Update PLAN.md

## Interim Workflow

Until full plan import:
1. Use seed tasks for immediate work
2. Add new tasks manually to `plan/por.yaml` following the schema
3. Run `python tools/generate_plan_md.py` after edits
4. Follow evidence protocol (JSONL append-only)

## Plan Document Format Expected

```markdown
# Phase Name (maps to P0, P1, etc.)

## Task Title (becomes P#-01, P#-02, etc.)

**Acceptance**:
- Checkable criterion 1
- Checkable criterion 2

**Module**: gateway|backend|lora|etc.
```

---

**Next**: Provide plan document to enable full import, or continue with seed tasks.
