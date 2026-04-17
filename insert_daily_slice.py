"""
Insert 2026-04-11 session entry into README.md and ROLLING_LOG.md.

Usage: python insert_daily_slice.py
"""
import os, sys

REPO = os.path.dirname(os.path.abspath(__file__))

def read_file(path):
    for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']:
        try:
            with open(path, 'r', encoding=enc) as f:
                return f.read(), enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise RuntimeError(f"Could not read {path}")

def write_file(path, content, enc):
    with open(path, 'w', encoding=enc, newline='') as f:
        f.write(content)

def update_rolling_log():
    log_path = os.path.join(REPO, "ROLLING_LOG.md")
    insert_path = os.path.join(REPO, "ROLLING_LOG_2026-04-11_INSERT.md")
    
    if not os.path.exists(insert_path):
        print(f"SKIP: {insert_path} not found")
        return False
    
    content, enc = read_file(log_path)
    insert, _ = read_file(insert_path)
    print(f"ROLLING_LOG: read {len(content)} chars ({enc})")
    
    # Find first "## 2026-04-10" or first "## " after title
    marker = "## 2026-04-10"
    idx = content.find(marker)
    if idx < 0:
        # Fallback: find any ## after position 10
        idx = content.find("\n## ", 10)
        if idx >= 0:
            idx += 1  # skip the newline
    
    if idx < 0:
        print("ERROR: No insertion point found")
        return False
    
    new_content = content[:idx] + insert + content[idx:]
    write_file(log_path, new_content, enc)
    os.remove(insert_path)
    print(f"ROLLING_LOG: DONE ({len(new_content)} chars)")
    return True

def update_readme():
    readme_path = os.path.join(REPO, "README.md")
    insert_path = os.path.join(REPO, "README_2026-04-11_INSERT.md")
    
    if not os.path.exists(insert_path):
        print(f"SKIP: {insert_path} not found")
        return False
    
    content, enc = read_file(readme_path)
    insert, _ = read_file(insert_path)
    print(f"README: read {len(content)} chars ({enc})")
    
    marker = "## 2026-04-10"
    idx = content.find(marker)
    if idx < 0:
        print("ERROR: '## 2026-04-10' not found in README")
        return False
    
    new_content = content[:idx] + insert + content[idx:]
    write_file(readme_path, new_content, enc)
    os.remove(insert_path)
    print(f"README: DONE ({len(new_content)} chars)")
    return True

if __name__ == '__main__':
    ok1 = update_rolling_log()
    ok2 = update_readme()
    
    if ok1 and ok2:
        print("\nBoth files updated. You can delete this script.")
    else:
        print("\nCheck output above for errors.")
    
    # Self-cleanup
    try:
        os.remove(os.path.join(REPO, ".tmp_insert_log.py"))
    except:
        pass
    try:
        os.remove(os.path.join(REPO, ".tmp_rolling_log_insert.md"))
    except:
        pass
