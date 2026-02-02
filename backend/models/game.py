"""
LaunchBox game models matching platform XML structure.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class Game(BaseModel):
    """
    LaunchBox game model matching platform XML structure.
    Populated from <Game> elements in Data/Platforms/*.xml files.
    """

    # Core identifiers
    id: str = Field(..., description="LaunchBox game ID (unique)")
    title: str = Field(..., description="Game title")
    platform: str = Field(..., description="Platform name (e.g., Arcade, NES)")

    # Metadata
    genre: Optional[str] = Field(None, description="Primary genre")
    developer: Optional[str] = Field(None, description="Developer name")
    publisher: Optional[str] = Field(None, description="Publisher name")
    year: Optional[int] = Field(None, description="Release year")
    region: Optional[str] = Field(None, description="Release region")

    # File paths
    rom_path: Optional[str] = Field(None, description="Path to ROM file")
    emulator_id: Optional[str] = Field(None, description="Associated emulator ID")
    application_path: Optional[str] = Field(None, description="Direct exe path if standalone")

    # Images
    box_front_path: Optional[str] = Field(None, description="Box art front image")
    screenshot_path: Optional[str] = Field(None, description="Gameplay screenshot")
    clear_logo_path: Optional[str] = Field(None, description="Clear logo image")

    # Categories/Tags (used for routing profiles like light-gun)
    categories: Optional[List[str]] = Field(None, description="List of category tags from LaunchBox")

    # Play stats (future Supabase integration)
    play_count: int = Field(0, description="Number of times played")
    last_played: Optional[datetime] = Field(None, description="Last play timestamp")
    favorite: bool = Field(False, description="User favorite flag")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "12345",
                "title": "Street Fighter II",
                "platform": "Arcade",
                "genre": "Fighting",
                "year": 1991,
                "rom_path": "<DRIVE>\\Roms\\MAME\\sf2.zip"
            }
        }


class LaunchRequest(BaseModel):
    """Request to launch a game with optional method specification."""
    force_method: Optional[str] = Field(
        None,
        description="Force specific launch method: cli_launcher|launchbox|direct"
    )
    profile_hint: Optional[str] = Field(
        None,
        description="Optional profile hint: e.g., 'lightgun' to apply profile-specific flags"
    )


class LaunchResponse(BaseModel):
    """Response from game launch attempt."""
    success: bool
    game_id: str
    method_used: str  # plugin_bridge|cli_launcher|launchbox|direct|none
    message: str
    game_title: Optional[str] = None  # Include game title for confirmation
    command: Optional[str] = None  # Command is optional (not used in plugin method)


class GameCacheStats(BaseModel):
    """Statistics about the in-memory game cache."""
    total_games: int
    platforms_count: int
    genres_count: int
    xml_files_parsed: int
    last_updated: Optional[datetime]
    is_mock_data: bool
    a_drive_status: str
