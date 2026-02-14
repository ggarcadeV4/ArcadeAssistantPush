#!/usr/bin/env python3
"""Generate PLAN.md from canonical plan/por.yaml"""

import yaml
import pathlib
import sys

def generate_plan_md():
    """Convert por.yaml to human-readable PLAN.md"""
    try:
        por = yaml.safe_load(open("plan/por.yaml", "r", encoding="utf8"))
    except FileNotFoundError:
        print("Error: plan/por.yaml not found", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing plan/por.yaml: {e}", file=sys.stderr)
        sys.exit(1)

    out = [
        "# Arcade Assistant — Completion Plan",
        "",
        f"**Canonical source**: `plan/por.yaml` (version {por.get('version', 'unknown')})",
        f"**Owner**: {por.get('owner', 'Unknown')}",
        "",
        "---",
        ""
    ]

    for phase in por.get("phases", []):
        out.append(f"## {phase['id']} — {phase['name']}")
        out.append("")

        for t in phase.get("tasks", []):
            status = t.get("status", "todo")
            box = "x" if status in ("done", "verified") else " "
            title = t["title"]
            module = t.get("module", "")
            ev = t.get("evidence", "")
            sha = t.get("last_verified_sha", "")

            # Build status indicator
            status_icon = {
                "todo": "⏸️",
                "in_progress": "🔄",
                "done": "✅",
                "verified": "✅🔒"
            }.get(status, "❓")

            out.append(f"- [{box}] **{t['id']}** {title} {status_icon}")
            out.append(f"  - **Module**: `{module}`")
            out.append(f"  - **Status**: `{status}`")
            out.append(f"  - **Evidence**: `{ev}`")
            if sha:
                out.append(f"  - **Last Verified**: `{sha[:8]}`")

            # Add acceptance criteria
            acceptance = t.get("acceptance", [])
            if acceptance:
                out.append(f"  - **Acceptance**:")
                for item in acceptance:
                    out.append(f"    - {item}")

            out.append("")

        out.append("")

    # Add summary section
    total_tasks = sum(len(phase.get("tasks", [])) for phase in por.get("phases", []))
    done_tasks = sum(
        1 for phase in por.get("phases", [])
        for t in phase.get("tasks", [])
        if t.get("status") in ("done", "verified")
    )
    verified_tasks = sum(
        1 for phase in por.get("phases", [])
        for t in phase.get("tasks", [])
        if t.get("status") == "verified"
    )

    out.extend([
        "---",
        "",
        "## Summary",
        "",
        f"- **Total Tasks**: {total_tasks}",
        f"- **Done**: {done_tasks}",
        f"- **Verified**: {verified_tasks}",
        f"- **Completion**: {done_tasks}/{total_tasks} ({int(done_tasks/total_tasks*100) if total_tasks > 0 else 0}%)",
        ""
    ])

    # Write output
    pathlib.Path("PLAN.md").write_text("\n".join(out), encoding="utf8")
    print(f"[OK] Wrote PLAN.md ({len(out)} lines, {total_tasks} tasks)")

if __name__ == "__main__":
    generate_plan_md()
