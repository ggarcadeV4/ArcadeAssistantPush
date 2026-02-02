# save as: backend_diag.py
import os, sys, platform, ctypes
from pathlib import Path

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def check_import(name):
    try:
        __import__(name)
        return True, None
    except Exception as e:
        return False, repr(e)

def main():
    print("=== BACKEND DIAGNOSTICS ===")
    print("Python:", sys.version.replace("\n", " "))
    print("Platform:", platform.platform())
    print("Admin:", is_admin())

    aa_drive_root = os.getenv("AA_DRIVE_ROOT")
    print("AA_DRIVE_ROOT env:", aa_drive_root)

    # A: drive basic access
    a_drive = Path("A:/")
    print("A: exists:", a_drive.exists())
    if a_drive.exists():
        test_dir = Path("A:/ArcadeAssistantDiag")
        try:
            test_dir.mkdir(parents=True, exist_ok=True)
            test_file = test_dir / "write_test.txt"
            test_file.write_text("ok", encoding="utf-8")
            print("A: write test: OK ->", str(test_file))
        except Exception as e:
            print("A: write test: FAIL ->", repr(e))

    for pkg in ["fastapi", "uvicorn", "pygame", "pynput"]:
        ok, err = check_import(pkg)
        print(f"Import {pkg}:", "OK" if ok else f"FAIL {err}")

    # pygame joystick snapshot
    try:
        import pygame
        pygame.init()
        pygame.joystick.init()
        count = pygame.joystick.get_count()
        print("pygame joystick count:", count)
        for i in range(count):
            js = pygame.joystick.Joystick(i)
            js.init()
            print(f"  [{i}] name={js.get_name()} axes={js.get_numaxes()} buttons={js.get_numbuttons()} hats={js.get_numhats()}")
            if js.get_numhats() > 0:
                pygame.event.pump()
                print("     hat0=", js.get_hat(0))
    except Exception as e:
        print("pygame init/enumeration FAILED:", repr(e))

if __name__ == "__main__":
    main()
