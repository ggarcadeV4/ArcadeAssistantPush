import logging
from pathlib import Path

from fastapi.concurrency import run_in_threadpool

logger = logging.getLogger("controller_chuck.mame_config")


def _build_mapdevice_xml(hardware_id: str, player_index: int) -> str:
    """
    Builds a single MAME <mapdevice> XML entry that anchors a physical
    hardware ID to a specific JOYCODE player slot.
    """
    return (
        f'        <mapdevice device="{hardware_id}" '
        f'controller="JOYCODE_{player_index}" />'
    )


def _build_pacto_cfg(detected_boards: list) -> str:
    """
    Generates the full XML content for mame/ctrlr/pacto.cfg.
    Each detected Pacto board gets a <mapdevice> entry anchoring
    its XInput nodes to sequential JOYCODE slots.
    """
    lines = ['<?xml version="1.0"?>']
    lines.append('<mameconfig version="10">')
    lines.append('    <system name="default">')
    lines.append('        <input>')

    player_index = 1
    for board in detected_boards:
        board_type = board.get("board_type", "Unknown")
        parent_hub = board.get("parent_hub", "")
        node_count = board.get("xinput_nodes", 0)

        if board_type not in ("Pacto_2000T", "Pacto_4000T"):
            continue

        logger.info(
            f"Chuck: Anchoring {board_type} "
            f"(hub={parent_hub}) to JOYCODE_{player_index}"
        )

        for _ in range(node_count):
            hardware_id = (
                f"XInput Player {player_index} "
                f"(VID_045E&PID_028E)"
            )
            lines.append(_build_mapdevice_xml(hardware_id, player_index))
            player_index += 1

    lines.append('        </input>')
    lines.append('    </system>')
    lines.append('</mameconfig>')

    return "\n".join(lines)


def _inject_ctrlr_into_mame_ini(mame_ini_path: Path) -> None:
    """
    Reads mame.ini and ensures 'ctrlr pacto' is set.
    If a ctrlr line already exists, replaces it.
    If not, appends it.
    """
    if not mame_ini_path.exists():
        logger.warning(
            f"Chuck: mame.ini not found at {mame_ini_path} - skipping ctrlr inject."
        )
        return

    lines = mame_ini_path.read_text(encoding="utf-8").splitlines()
    found = False
    new_lines = []

    for line in lines:
        if line.strip().lower().startswith("ctrlr"):
            new_lines.append("ctrlr                     pacto")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append("ctrlr                     pacto")

    mame_ini_path.write_text("\n".join(new_lines), encoding="utf-8")
    logger.info("Chuck: mame.ini ctrlr entry set to pacto.")


async def generate_mame_anchor(
    detected_boards: list,
    mame_dir: Path,
) -> dict:
    """
    Full MAME anchor pipeline:
    1. Generates mame/ctrlr/pacto.cfg from detected Pacto boards
    2. Injects 'ctrlr pacto' into mame.ini
    Returns a result dict with paths written.
    """
    ctrlr_dir = mame_dir / "ctrlr"
    await run_in_threadpool(ctrlr_dir.mkdir, parents=True, exist_ok=True)

    cfg_path = ctrlr_dir / "pacto.cfg"
    cfg_content = _build_pacto_cfg(detected_boards)
    await run_in_threadpool(cfg_path.write_text, cfg_content, encoding="utf-8")
    logger.info(f"Chuck: pacto.cfg written to {cfg_path}")

    mame_ini_path = mame_dir / "mame.ini"
    await run_in_threadpool(_inject_ctrlr_into_mame_ini, mame_ini_path)

    return {
        "pacto_cfg": str(cfg_path),
        "mame_ini": str(mame_ini_path),
        "boards_anchored": [
            b for b in detected_boards
            if b.get("board_type") in ("Pacto_2000T", "Pacto_4000T")
        ],
    }
