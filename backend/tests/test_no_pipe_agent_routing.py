from unittest.mock import Mock, patch

from backend.services.launcher import GameLauncher


def test_run_adapter_process_routes_redream_no_pipe_through_agent():
    with patch("backend.services.launcher._launch_via_agent", return_value={"ok": True, "pid": 4242}) as launch_via_agent:
        with patch("backend.services.launcher.subprocess.Popen") as popen:
            GameLauncher._run_adapter_process(
                exe=r"W:\Arcade Assistant Master Build\LaunchBox\Emulators\redream.x86_64-windows-v1.5.0\redream.exe",
                args=[r"W:\Arcade Assistant Master Build\Console ROMs\Sega Dreamcast\roms\Capcom vs. SNK (USA).chd"],
                cwd=r"W:\Arcade Assistant Master Build\LaunchBox\Emulators\redream.x86_64-windows-v1.5.0",
                on_exit=None,
                no_pipe=True,
                skip_agent=True,
            )

    launch_via_agent.assert_called_once()
    popen.assert_not_called()


def test_run_adapter_process_routes_supermodel_no_pipe_through_agent():
    with patch("backend.services.launcher._launch_via_agent", return_value={"ok": True, "pid": 5151}) as launch_via_agent:
        with patch("backend.services.launcher.subprocess.Popen") as popen:
            GameLauncher._run_adapter_process(
                exe=r"W:\Arcade Assistant Master Build\Emulators\Super Model\Supermodel.exe",
                args=[r"W:\Arcade Assistant Master Build\Roms\MODEL3\skichamp.zip"],
                cwd=r"W:\Arcade Assistant Master Build\Emulators\Super Model",
                on_exit=None,
                no_pipe=True,
                skip_agent=True,
            )

    launch_via_agent.assert_called_once()
    popen.assert_not_called()
