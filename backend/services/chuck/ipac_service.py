import asyncio
import os
import logging
from backend.schemas.encoder_schemas import IPACMode, IPACSwitchRequest, IPACSwitchResponse

logger = logging.getLogger("controller_chuck.ipac_service")


class IPACManagerService:
    """
    Service responsible for interacting with the WinIPAC CLI utility.
    Executes commands asynchronously to protect the FastAPI event loop.
    Mode switching causes a physical USB disconnect/reconnect on the host OS.
    """

    def __init__(
        self,
        winipac_exe_path: str = "C:\\Program Files\\WinIPACV2\\WinIPAC.exe"
    ):
        self.winipac_exe_path = winipac_exe_path

    async def apply_hardware_mode(
        self, request: IPACSwitchRequest
    ) -> IPACSwitchResponse:
        """
        Executes the WinIPAC CLI to push a new .ipc profile to the board.
        Enforces a 2.5 second async sleep after success to allow the OS
        to complete the USB handshake before returning to the caller.
        """
        if not os.path.exists(self.winipac_exe_path):
            return IPACSwitchResponse(
                success=False,
                expected_mode=request.target_mode,
                message="WinIPAC.exe not found. Is the utility installed?",
            )

        if not os.path.exists(request.config_file_path):
            return IPACSwitchResponse(
                success=False,
                expected_mode=request.target_mode,
                message=f"Configuration file missing: {request.config_file_path}",
            )

        logger.info(
            f"Chuck: Initiating physical mode switch to {request.target_mode.value}"
        )

        try:
            process = await asyncio.create_subprocess_exec(
                self.winipac_exe_path,
                request.config_file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode().strip() or "Unknown CLI failure."
                logger.error(f"Chuck: Hardware switch failed. {error_msg}")
                return IPACSwitchResponse(
                    success=False,
                    expected_mode=request.target_mode,
                    message="Firmware configuration rejected by the board.",
                    error_log=error_msg,
                )

            await asyncio.sleep(2.5)

            return IPACSwitchResponse(
                success=True,
                expected_mode=request.target_mode,
                message=(
                    f"I-PAC successfully switched to "
                    f"{request.target_mode.value} mode."
                ),
            )

        except Exception as e:
            logger.exception(
                "Chuck: Exception occurred during I-PAC mode switch."
            )
            return IPACSwitchResponse(
                success=False,
                expected_mode=request.target_mode,
                message="Internal server error during subprocess execution.",
                error_log=str(e),
            )


_ipac_service_instance: IPACManagerService | None = None


def get_ipac_service() -> IPACManagerService:
    """Returns the singleton IPACManagerService instance."""
    global _ipac_service_instance
    if _ipac_service_instance is None:
        _ipac_service_instance = IPACManagerService()
    return _ipac_service_instance
