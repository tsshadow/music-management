from __future__ import annotations

from backend.app.services.listenbrainz_service import ListenBrainzImportService


def build_listen(**extra):
    listen = {
        "track_metadata": {
            "track_name": "Example",
            "artist_name": "Artist",
            "additional_info": {},
        },
        "listened_at": 1_700_000_000,
    }
    listen.update(extra)
    return listen


def test_extract_genres_collects_from_multiple_sources():
    listen = build_listen(
        track_metadata={
            "track_name": "Example",
            "artist_name": "Artist",
            "genres": ["Indie", "Lo-Fi"],
            "additional_info": {
                "tags": ["Rock", {"name": "synthpop "}],
                "musicbrainz_tags": [{"name": "Electronic"}],
                "artist_tags": [{"value": "indie"}],
                "release_group_tags": ["Alternative"],
            },
        },
        tags=["Rock", "Dream Pop"],
    )

    genres = ListenBrainzImportService._extract_genres(listen)

    assert genres == [
        "Indie",
        "Lo-Fi",
        "Rock",
        "synthpop",
        "Electronic",
        "Alternative",
        "Dream Pop",
    ]


def test_extract_genres_deduplicates_case_insensitive():
    listen = build_listen(
        track_metadata={
            "track_name": "Example",
            "artist_name": "Artist",
            "additional_info": {
                "tags": ["Pop", "pop", " POP "],
            },
        }
    )

    genres = ListenBrainzImportService._extract_genres(listen)

    assert genres == ["Pop"]


def test_extract_genres_handles_tag_dict_keys():
    listen = build_listen(
        track_metadata={
            "track_name": "Example",
            "artist_name": "Artist",
            "additional_info": {
                "artist_genres": [{"genre": "Hip-Hop"}, {"tag": "Rap"}],
            },
        }
    )

    genres = ListenBrainzImportService._extract_genres(listen)

    assert genres == ["Hip-Hop", "Rap"]
