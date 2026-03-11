from pathlib import Path

from backend.services.score_tracking import (
    CanonicalGameEvent,
    ScoreReviewDecision,
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

