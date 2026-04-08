"""
Push specific files to GitHub via the REST API (Git Data API).
Creates a single atomic commit with all three files.

Usage:
    python scripts/git_push_api.py
"""

import requests
import base64
import json
import os
import sys

# --- Config ---
REPO = "ggarcadeV4/ArcadeAssistantPush"
BRANCH = "master"
COMMIT_MSG = "Fix: Route Nintendo GameCube to standalone Dolphin (fixes black screen)\n\n- dolphin_adapter.py: Add 'nintendo gamecube' to can_handle() - routes GameCube to Dolphin.exe instead of broken dolphin_libretro\n- launcher_registry.py: Make Dolphin adapter always-enabled (handles Wii + GameCube)\n- retroarch_adapter.py: Remove Nintendo GameCube from INSTANCE_REGISTRY (dolphin_libretro = black screen with audio)"

# Files to push (local path -> repo path)
FILES = {
    "backend/services/adapters/dolphin_adapter.py": "backend/services/adapters/dolphin_adapter.py",
    "backend/services/launcher_registry.py": "backend/services/launcher_registry.py",
    "backend/services/adapters/retroarch_adapter.py": "backend/services/adapters/retroarch_adapter.py",
}

API = "https://api.github.com"

def get_token():
    """Try to get GitHub token from environment."""
    for var in ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT"):
        token = os.environ.get(var)
        if token:
            return token
    # Try gh CLI
    try:
        import subprocess
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def main():
    token = get_token()
    if not token:
        print("ERROR: No GitHub token found.")
        print("Set GITHUB_TOKEN env var or ensure `gh auth login` is configured.")
        sys.exit(1)

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # 1. Get the current commit SHA for the branch
    print(f"[1/5] Getting HEAD of {BRANCH}...")
    ref_resp = requests.get(f"{API}/repos/{REPO}/git/ref/heads/{BRANCH}", headers=headers)
    ref_resp.raise_for_status()
    head_sha = ref_resp.json()["object"]["sha"]
    print(f"  HEAD: {head_sha}")

    # 2. Get the tree SHA of the current commit
    print(f"[2/5] Getting tree for commit {head_sha[:8]}...")
    commit_resp = requests.get(f"{API}/repos/{REPO}/git/commits/{head_sha}", headers=headers)
    commit_resp.raise_for_status()
    base_tree_sha = commit_resp.json()["tree"]["sha"]
    print(f"  Base tree: {base_tree_sha}")

    # 3. Create blobs for each file
    print(f"[3/5] Creating blobs for {len(FILES)} files...")
    tree_entries = []
    
    # Get the repo root directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    
    for local_rel, repo_path in FILES.items():
        local_full = os.path.join(repo_root, local_rel)
        print(f"  Reading: {local_rel}")
        
        with open(local_full, "rb") as f:
            content = f.read()
        
        encoded = base64.b64encode(content).decode("ascii")
        blob_resp = requests.post(
            f"{API}/repos/{REPO}/git/blobs",
            headers=headers,
            json={"content": encoded, "encoding": "base64"},
        )
        blob_resp.raise_for_status()
        blob_sha = blob_resp.json()["sha"]
        print(f"    Blob: {blob_sha}")

        tree_entries.append({
            "path": repo_path,
            "mode": "100644",
            "type": "blob",
            "sha": blob_sha,
        })

    # 4. Create a new tree
    print(f"[4/5] Creating new tree...")
    tree_resp = requests.post(
        f"{API}/repos/{REPO}/git/trees",
        headers=headers,
        json={"base_tree": base_tree_sha, "tree": tree_entries},
    )
    tree_resp.raise_for_status()
    new_tree_sha = tree_resp.json()["sha"]
    print(f"  New tree: {new_tree_sha}")

    # 5. Create the commit
    print(f"[5/5] Creating commit...")
    commit_create_resp = requests.post(
        f"{API}/repos/{REPO}/git/commits",
        headers=headers,
        json={
            "message": COMMIT_MSG,
            "tree": new_tree_sha,
            "parents": [head_sha],
        },
    )
    commit_create_resp.raise_for_status()
    new_commit_sha = commit_create_resp.json()["sha"]
    print(f"  New commit: {new_commit_sha}")

    # 6. Update the branch ref to point to the new commit
    print(f"Updating {BRANCH} to {new_commit_sha[:8]}...")
    update_resp = requests.patch(
        f"{API}/repos/{REPO}/git/refs/heads/{BRANCH}",
        headers=headers,
        json={"sha": new_commit_sha},
    )
    update_resp.raise_for_status()
    print(f"\n✅ Pushed to {BRANCH}: {new_commit_sha[:8]}")
    print(f"   Message: {COMMIT_MSG}")
    print(f"   URL: https://github.com/{REPO}/commit/{new_commit_sha}")

    # 7. Show recent log
    print(f"\nRecent commits:")
    log_resp = requests.get(
        f"{API}/repos/{REPO}/commits",
        headers=headers,
        params={"sha": BRANCH, "per_page": 5},
    )
    log_resp.raise_for_status()
    for c in log_resp.json():
        sha_short = c["sha"][:7]
        msg = c["commit"]["message"].split("\n")[0]
        print(f"  {sha_short} {msg}")


if __name__ == "__main__":
    main()
