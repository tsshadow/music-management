from analyzer.matching.normalizer import normalize_text, duration_bucket
from analyzer.matching.uid import make_track_uid


def test_normalize_text_removes_diacritics_and_punctuation():
    assert normalize_text("Beyoncé - Halo (Official Video)") == "beyonce halo official video"


def test_duration_bucket_rounds_with_tolerance():
    assert duration_bucket(183, tolerance=2) == "184"
    assert duration_bucket(None) == "na"


def test_make_track_uid_is_deterministic():
    uid1 = make_track_uid("Artist", "Title", "Album", 200)
    uid2 = make_track_uid("Artist", "Title", "Album", 201)
    assert uid1 == uid2
    assert uid1 == make_track_uid("Artist", "Title", "Album", 200)
