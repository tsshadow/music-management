from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tools.db_url import database_url

load_dotenv()


def check():
    engine = create_engine(database_url())

    with engine.connect() as conn:
        print("--- Integriteits Check ---")

        # 1. Koppeling Media Files -> Tracks
        linked_media = conn.execute(
            text("SELECT count(*) FROM library_media_files WHERE track_id IS NOT NULL")
        ).fetchone()[0]
        total_media = conn.execute(text("SELECT count(*) FROM library_media_files")).fetchone()[0]
        print(f"Media files gekoppeld aan tracks: {linked_media} van de {total_media}")

        # 2. Koppeling Audio Features -> Tracks
        linked_features = conn.execute(
            text("SELECT count(*) FROM library_track_audio_features WHERE internal_track_id IS NOT NULL")
        ).fetchone()[0]
        total_features = conn.execute(text("SELECT count(*) FROM library_track_audio_features")).fetchone()[0]
        print(f"Audio features gekoppeld aan tracks: {linked_features} van de {total_features}")

        # 3. Zijn er tracks zonder media files?
        tracks_no_media = conn.execute(
            text(
                "SELECT count(*) FROM library_tracks t WHERE NOT EXISTS (SELECT 1 FROM library_media_files m WHERE m.track_id = t.id)"
            )
        ).fetchone()[0]
        total_tracks = conn.execute(text("SELECT count(*) FROM library_tracks")).fetchone()[0]
        print(f"Tracks zonder media files: {tracks_no_media} van de {total_tracks}")


if __name__ == "__main__":
    check()
