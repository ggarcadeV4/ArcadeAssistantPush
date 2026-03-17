from pathlib import Path
import os
import re
import uuid


PLACEHOLDER_DEVICE_ID = "00000000-0000-0000-0000-000000000001"
ENV_KEY = "AA_DEVICE_ID"
ENV_PATTERN = re.compile(r"^\s*AA_DEVICE_ID=(.*)$")


def detect_drive_root() -> Path:
    env_drive_root = (os.getenv("AA_DRIVE_ROOT") or "").strip()
    if env_drive_root:
        return Path(env_drive_root)

    script_drive_root = Path(__file__).resolve().parent.parent
    if script_drive_root.exists():
        return script_drive_root

    return Path("A:/")


def read_env_text(env_path: Path) -> str:
    if not env_path.exists():
        return ""
    return env_path.read_text(encoding="utf-8")


def extract_env_device_id(env_text: str) -> str:
    for line in env_text.splitlines():
        match = ENV_PATTERN.match(line)
        if match:
            return match.group(1).strip()
    return ""


def is_valid_uuid4(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return parsed.version == 4 and str(parsed) == value.lower()


def write_device_id_file(drive_root: Path, device_id: str) -> Path:
    device_id_path = drive_root / ".aa" / "device_id.txt"
    device_id_path.parent.mkdir(parents=True, exist_ok=True)
    device_id_path.write_text(device_id, encoding="utf-8")
    return device_id_path


def update_env_file(env_path: Path, device_id: str) -> None:
    env_text = read_env_text(env_path)
    newline = "\r\n" if "\r\n" in env_text else "\n"
    replacement = f"{ENV_KEY}={device_id}"
    lines = env_text.splitlines(keepends=True)
    updated_lines = []
    replaced = False

    for line in lines:
        if ENV_PATTERN.match(line):
            if line.endswith("\r\n"):
                line_ending = "\r\n"
            elif line.endswith("\n"):
                line_ending = "\n"
            else:
                line_ending = ""
            updated_lines.append(f"{replacement}{line_ending}")
            replaced = True
        else:
            updated_lines.append(line)

    if not replaced:
        if updated_lines and not updated_lines[-1].endswith(("\n", "\r\n")):
            updated_lines[-1] = updated_lines[-1] + newline
        updated_lines.append(f"{replacement}{newline}")

    env_path.write_text("".join(updated_lines), encoding="utf-8")


def write_line(text: str) -> None:
    os.write(1, f"{text}\n".encode("utf-8"))


def main() -> int:
    drive_root = detect_drive_root()
    env_path = drive_root / ".env"
    current_device_id = extract_env_device_id(read_env_text(env_path))

    if current_device_id and current_device_id != PLACEHOLDER_DEVICE_ID and is_valid_uuid4(current_device_id):
        write_line(f"Device ID already set: {current_device_id}")
        return 0

    new_device_id = str(uuid.uuid4())
    write_device_id_file(drive_root, new_device_id)
    update_env_file(env_path, new_device_id)

    write_line(f"\u2705 Device ID generated: {new_device_id}")
    write_line("\u2705 Written to .aa/device_id.txt")
    write_line("\u2705 Updated .env")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
