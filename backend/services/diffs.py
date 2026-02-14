import difflib
from typing import List

def compute_diff(old_text: str, new_text: str, filename: str = "file") -> str:
    """Compute unified diff between old and new text

    Args:
        old_text: Original content
        new_text: Modified content
        filename: Name to use in diff header

    Returns:
        Unified diff as string
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm=""
    )

    return "".join(diff)

def compute_diff_lines(old_text: str, new_text: str, filename: str = "file") -> List[str]:
    """Compute unified diff as list of lines

    Args:
        old_text: Original content
        new_text: Modified content
        filename: Name to use in diff header

    Returns:
        List of diff lines
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff_lines = list(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm=""
    ))

    return diff_lines

def has_changes(old_text: str, new_text: str) -> bool:
    """Check if there are any differences between old and new text

    Args:
        old_text: Original content
        new_text: Modified content

    Returns:
        True if there are differences
    """
    return old_text.strip() != new_text.strip()