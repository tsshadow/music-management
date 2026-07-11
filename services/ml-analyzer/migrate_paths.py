from sqlalchemy import text
from analyzer import TrackAnalyzer
from dotenv import load_dotenv

def migrate_paths():
    load_dotenv()
    analyzer = TrackAnalyzer()
    if analyzer.engine is None:
        print('Geen database verbinding.')
        return
    print('Migreren van bestandspaden en interne IDs...')
    migrate_query = '\n        UPDATE library_track_audio_features f\n        JOIN library_media_files m ON f.track_id = m.file_path_hash\n        SET f.file_path = m.file_path,\n            f.internal_track_id = m.track_id\n        WHERE f.file_path IS NULL OR f.internal_track_id IS NULL\n    '
    try:
        with analyzer.engine.begin() as conn:
            result = conn.execute(text(migrate_query))
            print(f'Klaar! {result.rowcount} records bijgewerkt.')
    except Exception as e:
        if 'Unknown column' in str(e):
            print("\nFOUT: De database tabel 'library_track_audio_features' mist kolommen.")
            print('Draai eerst het volgende script om de database bij te werken:')
            print('  python fix_db_schema.py\n')
        else:
            print(f'Fout tijdens migratie: {e}')
if __name__ == '__main__':
    migrate_paths()