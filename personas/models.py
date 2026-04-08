"""Data models for the Arcade OS persona system."""
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Persona:
    """Full persona row from the database."""
    id: Optional[int] = None
    name: str = ""
    role: str = ""
    avatar: str = "🤖"
    description: str = ""
    system_prompt: str = ""
    model: Optional[str] = None
    voice_id: Optional[str] = None
    color: str = "#00c896"
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to JSON-safe dictionary."""
        d = asdict(self)
        d["is_active"] = bool(d["is_active"])
        return d


@dataclass
class PersonaCreate:
    """Input schema for creating a new persona."""
    name: str
    role: str
    system_prompt: str
    avatar: str = "🤖"
    description: str = ""
    model: Optional[str] = None
    voice_id: Optional[str] = None
    color: str = "#00c896"


@dataclass
class PersonaUpdate:
    """Partial update schema — only non-None fields are applied."""
    name: Optional[str] = None
    role: Optional[str] = None
    avatar: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    voice_id: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None
