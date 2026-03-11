from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.services.score_tracking import (
    CanonicalGameEvent,
    ScoreReviewDecision,
    ScoreTrackingService,
    get_score_tracking_service,
)


def test_score_tracking_launch_and_auto_capture(tmp_path):
    service = get_score_tracking_service(tmp_path)
    session = service.record_launch(
        CanonicalGameEvent(
            source='launchbox',
            game_id='game-1',
            title='Street Fighter II',
            platform='Arcade',
            rom_name='sf2',
        )
    )

    service.record_auto_capture(
        session,
        strategy_name='mame_hiscore',
        score=12345,
        confidence=1.0,
        player='AAA',
    )

    coverage = service.coverage_summary()
    assert coverage['attempt_count'] == 1
    assert coverage['tracked_automatically'] == 1
    assert coverage['pending_review'] == 0


def test_score_tracking_review_queue_and_manual_approval(tmp_path):
    service = get_score_tracking_service(tmp_path / 'cabinet-2')
    session = service.record_launch(
        CanonicalGameEvent(
            source='launchbox_plugin',
            game_id='game-2',
            title='Nintendo Land',
            platform='Nintendo Wii U',
        )
    )

    attempt = service.record_pending_review(
        session,
        strategy_name='vision',
        confidence=0.42,
        raw_score=999,
        reason='vision_low_confidence',
    )

    queue = service.list_review_queue(limit=10)
    assert len(queue) == 1
    assert queue[0]['attempt_id'] == attempt.attempt_id

    reviewed = service.review_attempt(
        attempt.attempt_id,
        ScoreReviewDecision(action='edit', score=1500, player='Dad')
    )

    assert reviewed is not None
    assert reviewed.status == 'captured_manual'
    assert reviewed.final_score == 1500
    assert reviewed.player == 'Dad'
def test_score_tracking_reuses_existing_active_session(tmp_path):
    service = get_score_tracking_service(tmp_path / 'cabinet-3')
    first = service.record_launch(
        CanonicalGameEvent(
            source='launchbox_frontend',
            game_id='game-3',
            title='Street Fighter II',
            platform='Arcade',
            rom_name='sf2',
        )
    )

    second = service.record_launch(
        CanonicalGameEvent(
            source='launchbox_router',
            game_id='game-3',
            title='Street Fighter II',
            platform='Arcade',
            rom_name='sf2',
            pid=4321,
            launch_method='policy_primary',
        )
    )

    assert first['session_id'] == second['session_id']
    assert second['pid'] == 4321
    assert len(service._load_active_sessions()) == 1


def test_close_session_is_idempotent(tmp_path):
    service = ScoreTrackingService(tmp_path / "cabinet-4")
    session = service.record_launch(
        CanonicalGameEvent(
            source='launchbox',
            game_id='game-4',
            title='Galaga',
            platform='Arcade',
            rom_name='galaga',
        )
    )

    closed = service.close_session(session_id=session['session_id'])
    duplicate = service.close_session(session_id=session['session_id'])

    assert closed is not None
    assert duplicate is None


def test_stale_session_cleanup_creates_failed_attempt(tmp_path):
    drive_root = tmp_path / 'cabinet-5'
    state_dir = drive_root / '.aa' / 'state' / 'scorekeeper'
    state_dir.mkdir(parents=True, exist_ok=True)
    stale_started_at = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    session_payload = {
        'stale-session': {
            'session_id': 'stale-session',
            'source': 'launchbox',
            'game_id': 'game-5',
            'title': 'Out Run',
            'platform': 'Arcade',
            'emulator': 'mame',
            'pid': 1234,
            'launch_method': 'plugin_event',
            'started_at': stale_started_at,
            'ended_at': None,
            'player': None,
            'rom_name': 'outrun',
            'strategy': {'primary': 'mame_hiscore', 'fallback': 'mame_lua', 'resolution_source': 'default'},
            'metadata': {},
        }
    }
    (state_dir / 'active_score_sessions.json').write_text(__import__('json').dumps(session_payload, indent=2), encoding='utf-8')

    service = ScoreTrackingService(drive_root)

    assert service._load_active_sessions() == {}
    queue = service.list_review_queue(limit=10)
    assert len(queue) == 1
    assert queue[0]['status'] == 'failed'
    assert queue[0]['strategy'] == 'none'
    assert queue[0]['metadata']['reason'] == 'stale_session_cleanup'


