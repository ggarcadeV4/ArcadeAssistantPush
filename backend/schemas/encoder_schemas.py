from typing import List

from pydantic import BaseModel, Field, model_validator


class ConnectedGamepad(BaseModel):
    vid: str
    pid: str
    product_string: str


class ArcadeCabinetTopology(BaseModel):
    gamepads: List[ConnectedGamepad]

    @model_validator(mode='before')
    @classmethod
    def check_brook_xb1_conflict(cls, values):
        gamepads = values.get('gamepads', [])
        xb1_count = sum(
            1 for g in gamepads
            if (
                g.get('product_string') == "Xbox One Wireless Controller"
                if isinstance(g, dict)
                else getattr(g, 'product_string', None) == "Xbox One Wireless Controller"
            )
        )
        if xb1_count > 1:
            raise ValueError(
                "Multiple Xbox One boards detected. "
                "Windows 10 will drop inputs. "
                "Set Player 2 to Xbox 360 mode."
            )
        return values
from typing import Optional
from enum import Enum
from pydantic import ConfigDict

class IPACMode(str, Enum):
    KEYBOARD = "keyboard"
    DINPUT = "dinput"
    XINPUT = "xinput"

class IPACSwitchRequest(BaseModel):
    target_mode: IPACMode = Field(..., description="The physical mode to force the I-PAC into.")
    config_file_path: str = Field(..., description="Absolute path to the .ipc configuration file.")
    model_config = ConfigDict(strict=True)

class IPACSwitchResponse(BaseModel):
    success: bool = Field(..., description="Whether the subprocess executed successfully.")
    expected_mode: IPACMode = Field(..., description="The mode the board should now be in.")
    message: str = Field(..., description="Actionable status message.")
    error_log: Optional[str] = Field(default=None, description="Captured stderr if the CLI fails.")
