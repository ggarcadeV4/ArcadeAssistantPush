# @agent: Lexicon
# @role: Scans folder and creates starter index.json for AI guidance

import os
import json

def deploy_index(folder_path, purpose=""):
    """Generate index.json for a folder with initial file metadata"""
    if not os.path.exists(folder_path):
        print(f"❌ Folder not found: {folder_path}")
        return

    files = os.listdir(folder_path)
    manifest = {
        "folder": os.path.basename(folder_path),
        "purpose": purpose,
        "files": []
    }

    for file in files:
        if file.endswith((".tsx", ".py", ".js", ".ts", ".md")):
            # Skip index.json itself
            if file == "index.json":
                continue

            file_entry = {
                "file": file,
                "role": "TODO",
                "agent": "TODO",
                "tags": [],
                "dependencies": []
            }

            # Add some basic categorization based on file extension
            if file.endswith(".tsx"):
                file_entry["tags"] = ["component", "react"]
            elif file.endswith(".py"):
                file_entry["tags"] = ["service", "python"]
            elif file.endswith((".js", ".ts")):
                file_entry["tags"] = ["javascript", "nodejs"]
            elif file.endswith(".md"):
                file_entry["tags"] = ["documentation"]

            manifest["files"].append(file_entry)

    index_path = os.path.join(folder_path, "index.json")
    with open(index_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"✅ index.json created for {folder_path}")
    print(f"📄 {len(manifest['files'])} files catalogued")

# Example usage:
# deploy_index("panels", "Grid-based visual modules for the Arcade Assistant GUI")
# deploy_index("services", "Background services for hardware, voice, and system monitoring")
# deploy_index("components", "Reusable UI components following design tokens")