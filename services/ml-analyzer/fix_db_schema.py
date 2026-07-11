from sqlalchemy import text, inspect
from analyzer import TrackAnalyzer
from dotenv import load_dotenv

def fix_schema():
    load_dotenv()
    analyzer = TrackAnalyzer()
    if analyzer.engine is None:
        print('Geen database verbinding.')
        return
    tables_to_fix = {'library_track_audio_features': [('internal_track_id', 'INT'), ('file_path', 'TEXT'), ('artist_name', 'VARCHAR(255)'), ('label_name', 'VARCHAR(255)'), ('release_year', 'INT'), ('source_platform', 'VARCHAR(50)'), ('bpm_tag', 'FLOAT'), ('genre_tag', 'VARCHAR(100)')], 'library_track_ml_labels': [('ml_review_status', "ENUM('unreviewed', 'human_verified', 'borderline', 'do_not_train') DEFAULT 'unreviewed'"), ('approved_for_training', 'BOOLEAN DEFAULT FALSE')]}
    inspector = inspect(analyzer.engine)
    added_count = 0
    with analyzer.engine.begin() as conn:
        for table_name, columns in tables_to_fix.items():
            print(f'\nControleren van tabel: {table_name}')
            if not inspector.has_table(table_name):
                print(f'Tabel {table_name} bestaat nog niet. Sla over (gebruik db_init.sql voor nieuwe installatie).')
                continue
            existing_columns = [c['name'] for c in inspector.get_columns(table_name)]
            for col_name, col_type in columns:
                if col_name not in existing_columns:
                    print(f"Kolom '{col_name}' ontbreekt in {table_name}. Toevoegen...")
                    try:
                        conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}'))
                        added_count += 1
                    except Exception as e:
                        print(f'Fout bij toevoegen van {col_name} aan {table_name}: {e}')
                else:
                    print(f"Kolom '{col_name}' bestaat al.")
    if added_count > 0:
        print(f'\nKlaar! {added_count} kolommen in totaal toegevoegd.')
    else:
        print('Geen wijzigingen nodig.')
if __name__ == '__main__':
    fix_schema()