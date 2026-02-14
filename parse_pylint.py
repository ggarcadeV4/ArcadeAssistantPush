import re
from pathlib import Path
text = Path('pylint_report.txt').read_text(encoding='utf-16')
results = []
for chunk in text.split('************* Module '):
    if not chunk.strip():
        continue
    lines = chunk.splitlines()
    header = lines[0].strip()
    m = re.search(r'Your code has been rated at ([0-9.]+)/10', chunk)
    if m:
        results.append((header, float(m.group(1))))
for module, score in results:
    print(f"{module}\t{score}")
