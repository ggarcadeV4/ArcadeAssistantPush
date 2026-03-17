from backend.services.led_blinky_translator import (
    GENRE_ANIMATION_CODES,
    normalize_genre,
    resolve_animation_code,
    resolve_genre_key,
)


def test_normalize_genre_variants():
    assert normalize_genre("FIGHTING") == "fighting"
    assert normalize_genre("Beat 'Em Up") == "fighting"
    assert normalize_genre("beat-em-up") == "fighting"
    assert normalize_genre("Driving/Racing") == "racing"
    assert normalize_genre("Shoot 'Em Up") == "shooter"
    assert normalize_genre("Shmup") == "shooter"


def test_resolve_genre_key_prefers_explicit_genre():
    assert (
        resolve_genre_key(
            "Racing",
            tags=["LED:FIGHTING", "Beat 'Em Up"],
            cinema_tag="LED:FIGHTING",
        )
        == "racing"
    )


def test_resolve_animation_code_uses_tags_and_cinema_tag():
    assert resolve_animation_code(tags=["LED:FIGHTING"]) == GENRE_ANIMATION_CODES["fighting"]
    assert resolve_animation_code(cinema_tag="LED:RACING") == GENRE_ANIMATION_CODES["racing"]
    assert resolve_animation_code(tags=["Shooter / Flying Vertical"]) == GENRE_ANIMATION_CODES["shooter"]


def test_resolve_animation_code_defaults_to_static_on():
    assert resolve_animation_code() == GENRE_ANIMATION_CODES["default"]
    assert resolve_animation_code("Unknown Genre") == GENRE_ANIMATION_CODES["default"]
