"""Download MAME catver.ini from progettosnaps or GitHub mirrors."""
import urllib.request
import os
import zipfile
import io

TARGETS = [
    r"A:\Emulators\MAME\catver.ini",
]

URLS = [
    # progettosnaps direct download (zip containing catver.ini)
    "https://www.progettosnaps.net/catver/packs/pS_CatVer_282.zip",
    "https://www.progettosnaps.net/catver/packs/pS_CatVer_285.zip",
    "https://www.progettosnaps.net/catver/packs/pS_CatVer_280.zip",
    # GitHub mirrors
    "https://raw.githubusercontent.com/AntoPISA/MAME_SupportFiles/main/CatVer/catver.ini",
    "https://raw.githubusercontent.com/AntoPISA/MAME_SupportFiles/main/catver/catver.ini",
    "https://raw.githubusercontent.com/AntoPISA/MAME_SupportFiles/main/CatVer.ini",
]

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

for url in URLS:
    try:
        print(f"Trying: {url}")
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=30)
        data = resp.read()
        print(f"  Downloaded: {len(data):,} bytes")

        content = None
        if url.endswith(".zip"):
            # Extract catver.ini from zip
            zf = zipfile.ZipFile(io.BytesIO(data))
            names = zf.namelist()
            print(f"  Zip contents: {names}")
            for name in names:
                if "catver" in name.lower() and name.lower().endswith(".ini"):
                    content = zf.read(name)
                    print(f"  Extracted: {name} ({len(content):,} bytes)")
                    break
            if not content:
                print("  No catver.ini found in zip")
                continue
        else:
            content = data

        # Validate
        text = content.decode("utf-8", errors="ignore")
        lines = text.split("\n")
        entries = [l for l in lines if "=" in l and not l.startswith("[")]
        print(f"  Total lines: {len(lines):,}")
        print(f"  Game entries: {len(entries):,}")

        # Show samples
        for l in entries[:5]:
            print(f"    {l.strip()}")

        # Save
        for target in TARGETS:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(content)
            print(f"  Saved to: {target}")

        print("\nSUCCESS!")
        break

    except Exception as e:
        print(f"  Failed: {e}")
        continue
else:
    print("\nAll URLs failed. Will try alternate approach...")
