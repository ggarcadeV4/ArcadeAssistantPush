import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.routers import dewey as dewey_router
from backend.services.dewey.service import (
    DeweyService,
    ProfileCreate,
    ProfileData,
    ProfilePreferences,
    ProfileUpdate,
)


class StubDeweyService(DeweyService):
    def __init__(self):
        self.created = {}

    def get_profile(self, user_id: str) -> ProfileData:
        return self.created.get(
            user_id,
            ProfileData(user_id=user_id, display_name="User"),
        )

    def create_profile(self, payload: ProfileCreate) -> ProfileData:
        profile = ProfileData(
            user_id=payload.user_id,
            display_name=payload.display_name or "User",
            preferences=payload.preferences or ProfilePreferences(),
        )
        self.created[profile.user_id] = profile
        return profile

    def update_profile(self, user_id: str, payload: ProfileUpdate) -> ProfileData:
        existing = self.created.get(user_id) or ProfileData(user_id=user_id)
        updated = existing.model_copy(
            update={"preferences": payload.preferences or existing.preferences}
        )
        self.created[user_id] = updated
        return updated


app = FastAPI()
app.include_router(dewey_router.router)
client = TestClient(app)


_stub_service = StubDeweyService()


def override_service():
    return _stub_service


dewey_router.get_dewey_service.cache_clear()
app.dependency_overrides[dewey_router.get_dewey_service] = override_service


def setup_function():
    _stub_service.created.clear()
    dewey_router.CREATE_LIMITER._hits.clear()
    dewey_router.UPDATE_LIMITER._hits.clear()


def test_create_and_fetch_profile():
    response = client.post(
        "/api/local/dewey/profiles",
        json={"user_id": "kiddo", "display_name": "Kiddo"},
    )
    assert response.status_code == 201

    response = client.get("/api/local/dewey/profiles/kiddo")
    assert response.status_code == 200
    assert response.json()["display_name"] == "Kiddo"


def test_update_profile_preferences():
    client.post("/api/local/dewey/profiles", json={"user_id": "mom"})

    response = client.put(
        "/api/local/dewey/profiles/mom",
        json={"preferences": {"kid_mode": True}},
    )
    assert response.status_code == 200
    assert response.json()["preferences"]["kid_mode"] is True
