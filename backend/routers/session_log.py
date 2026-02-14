from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from ..services.backup import create_backup
from ..services.diffs import compute_diff, has_changes
from ..services.policies import require_scope, is_allowed_file

router = APIRouter()

class SessionLogEntry(BaseModel):
    summary: str
    triumphs: List[str]
    mistakes_lessons: List[str]
    next_steps: List[str]
    startup_behavior: Optional[str] = None
    shutdown_behavior: Optional[str] = None

@router.post("/append")
async def append_session_log(request: Request, log_entry: SessionLogEntry):
    """Append a session log entry to README.md with preview -> backup -> apply"""

    try:
        # Validate scope header - docs operations require backup scope
        require_scope(request, "backup")

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        policies = request.app.state.policies

        readme_path = drive_root / "README.md"

        # Validate README.md is allowed by policy
        docs_policy = policies.get("docs", {})
        allowed_files = docs_policy.get("allowed_files", [])

        if "README.md" not in allowed_files:
            raise HTTPException(
                status_code=403,
                detail="README.md modifications not allowed by policy"
            )

        if not docs_policy.get("append_only", False):
            raise HTTPException(
                status_code=403,
                detail="README.md policy does not allow append operations"
            )

        # Read current README content
        if readme_path.exists():
            with open(readme_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
        else:
            # Create initial README structure
            current_content = """📖 Arcade Assistant — Rolling Session Log

This file is the chronological session log of Arcade Assistant development.
Agents and humans must append only; never rewrite or delete past entries.
Each entry is created when the user signals session closure ("this session is coming to a close").

## 📌 Log Format

Every new entry must follow this structure:

## [YYYY-MM-DD HH:MM] — Session Log

### 📝 Summary
(1–3 paragraphs describing what was done this session.)

### ✅ Triumphs
- (List successes)

### ⚠️ Mistakes / Lessons
- (List failures, issues, or insights learned)

### 🎯 Next Steps
- (Action items to be tackled in future sessions)

## 📚 Session History

(Append new logs below this line — most recent at the bottom.)

"""

        # Generate timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Create new log entry
        new_entry = f"""
## [{timestamp}] — Session Log

### 📝 Summary
{log_entry.summary}

### ✅ Triumphs
{chr(10).join(f'- {triumph}' for triumph in log_entry.triumphs)}

### ⚠️ Mistakes / Lessons
{chr(10).join(f'- {lesson}' for lesson in log_entry.mistakes_lessons)}

### 🎯 Next Steps
{chr(10).join(f'- {step}' for step in log_entry.next_steps)}
"""

        # Add optional sections
        if log_entry.startup_behavior:
            new_entry += f"\n### 🚀 Startup Behavior\n{log_entry.startup_behavior}\n"

        if log_entry.shutdown_behavior:
            new_entry += f"\n### 🛑 Shutdown Behavior\n{log_entry.shutdown_behavior}\n"

        # Append to README
        new_content = current_content.rstrip() + new_entry + "\n"

        # Check for changes
        if not has_changes(current_content, new_content):
            return {
                "status": "no_changes",
                "message": "No changes to append"
            }

        # Create backup if file exists
        backup_path = None
        if readme_path.exists() and request.app.state.backup_on_write:
            backup_path = create_backup(readme_path, drive_root)

        # Write new content
        readme_path.parent.mkdir(parents=True, exist_ok=True)
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return {
            "status": "appended",
            "timestamp": timestamp,
            "backup_path": str(backup_path) if backup_path else None,
            "entry_size": len(new_entry)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/preview")
async def preview_session_log(request: Request, log_entry: SessionLogEntry):
    """Preview what would be appended to README.md"""

    try:
        drive_root = request.app.state.drive_root
        readme_path = drive_root / "README.md"

        # Read current README content
        if readme_path.exists():
            with open(readme_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
        else:
            current_content = ""

        # Generate preview entry
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        new_entry = f"""
## [{timestamp}] — Session Log

### 📝 Summary
{log_entry.summary}

### ✅ Triumphs
{chr(10).join(f'- {triumph}' for triumph in log_entry.triumphs)}

### ⚠️ Mistakes / Lessons
{chr(10).join(f'- {lesson}' for lesson in log_entry.mistakes_lessons)}

### 🎯 Next Steps
{chr(10).join(f'- {step}' for step in log_entry.next_steps)}
"""

        if log_entry.startup_behavior:
            new_entry += f"\n### 🚀 Startup Behavior\n{log_entry.startup_behavior}\n"

        if log_entry.shutdown_behavior:
            new_entry += f"\n### 🛑 Shutdown Behavior\n{log_entry.shutdown_behavior}\n"

        new_content = current_content.rstrip() + new_entry + "\n"

        # Generate diff
        diff = compute_diff(current_content, new_content, "README.md")

        return {
            "timestamp": timestamp,
            "diff": diff,
            "entry_preview": new_entry.strip(),
            "has_changes": has_changes(current_content, new_content)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))