import os
import sys
import librosa
import numpy as np
import torch
import torchaudio
import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from sqlalchemy import create_engine
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tqdm import tqdm

load_dotenv()

class TrackAnalyzer:
    def __init__(self, max_workers=4):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Using device: {self.device}")
        self.engine = self._get_db_engine()
        self.max_workers = max_workers
        self.verbose = True

    def _get_db_engine(self):
        host = os.getenv("DB_HOST", "db")
        port = os.getenv("DB_PORT", "3306")
        user = os.getenv("DB_USER", "music-management")
        password = os.getenv("DB_PASS", "")
        db_name = os.getenv("DB_DB", "music-management")
        
        if not password:
            return None
            
        url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db_name}"
        return create_engine(url)

    def load_audio(self, file_path):
        """Laad audio bestand in."""
        if self.verbose:
            print(f"Loading track: {file_path}")
        try:
            # Librosa voor basis analyse
            y, sr = librosa.load(file_path, sr=None)
            return y, sr
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
            return None, None

    def extract_audio_features(self, y, sr):
        """Extraheer muzikale audio kenmerken."""
        if y is None:
            return None

        if self.verbose:
            print("Extracting features...")
        # Gebruik een hogere start_bpm (150 ipv default 120) omdat veel muziek in deze collectie 
        # sneller is (Hardcore/Uptempo). Dit helpt bij het voorkomen van 'half-tempo' fouten.
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, start_bpm=150)
        
        # Spectrale kenmerken
        spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
        spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
        spectral_contrast = librosa.feature.spectral_contrast(y=y, sr=sr)[0]
        
        # Tijdsdomein kenmerken
        rms = librosa.feature.rms(y=y)[0]
        zcr = librosa.feature.zero_crossing_rate(y=y)[0]
        
        # Timbre (MFCCs) - breiden uit naar 13 voor meer detail
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        
        # Harmonische inhoud (Chroma)
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        
        features = {
            "tempo": float(np.mean(tempo)),
            "duration": float(librosa.get_duration(y=y, sr=sr)),
            "mean_spectral_centroid": float(np.mean(spectral_centroids)),
            "std_spectral_centroid": float(np.std(spectral_centroids)),
            "mean_spectral_bandwidth": float(np.mean(spectral_bandwidth)),
            "std_spectral_bandwidth": float(np.std(spectral_bandwidth)),
            "mean_spectral_rolloff": float(np.mean(spectral_rolloff)),
            "std_spectral_rolloff": float(np.std(spectral_rolloff)),
            "mean_rms": float(np.mean(rms)),
            "std_rms": float(np.std(rms)),
            "mean_zcr": float(np.mean(zcr)),
            "std_zcr": float(np.std(zcr)),
            "mean_spectral_contrast": float(np.mean(spectral_contrast)),
            "std_spectral_contrast": float(np.std(spectral_contrast)),
            "mean_chroma": float(np.mean(chroma)),
            "std_chroma": float(np.std(chroma))
        }
        
        # Voeg MFCC's toe (1 t/m 13, mean en std)
        for i in range(13):
            features[f"mfcc_{i+1}"] = float(np.mean(mfccs[i]))
            features[f"std_mfcc_{i+1}"] = float(np.std(mfccs[i]))
        
        return features

    def extract_metadata(self, file_path):
        """Extraheer metadata (tags) uit het audiobestand."""
        metadata = {
            "artist_name": None,
            "label_name": None,
            "genre_tag": None,
            "release_year": None,
            "bpm_tag": None,
            "source_platform": None
        }
        
        # Bepaal source_platform op basis van het pad
        path_parts = Path(file_path).parts
        for platform in ['Soundcloud', 'Youtube', 'Telegram']:
            if platform in path_parts:
                metadata["source_platform"] = platform
                break
        
        # Als we in de 'EPs' map zitten, is de volgende map vaak het label
        if 'EPs' in path_parts:
            try:
                idx = path_parts.index('EPs')
                if len(path_parts) > idx + 1:
                    metadata["label_name"] = path_parts[idx + 1]
            except (ValueError, IndexError):
                pass

        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.mp3':
                tags = EasyID3(file_path)
                metadata["artist_name"] = tags.get('artist', [None])[0]
                metadata["genre_tag"] = tags.get('genre', [None])[0]
                metadata["label_name"] = metadata["label_name"] or tags.get('publisher', [None])[0]
                date = tags.get('date', [None])[0]
                if date and len(date) >= 4:
                    try:
                        metadata["release_year"] = int(date[:4])
                    except ValueError:
                        pass
                bpm = tags.get('bpm', [None])[0]
                if bpm:
                    try:
                        metadata["bpm_tag"] = float(bpm)
                    except ValueError:
                        pass
            elif ext == '.flac':
                tags = FLAC(file_path)
                metadata["artist_name"] = tags.get('artist', [None])[0]
                metadata["genre_tag"] = tags.get('genre', [None])[0]
                metadata["label_name"] = metadata["label_name"] or tags.get('publisher', [None])[0]
                date = tags.get('date', [None])[0]
                if date and len(date) >= 4:
                    try:
                        metadata["release_year"] = int(date[:4])
                    except ValueError:
                        pass
            elif ext == '.m4a':
                tags = MP4(file_path)
                # MP4 tags zijn anders
                metadata["artist_name"] = tags.get('\xa9ART', [None])[0]
                metadata["genre_tag"] = tags.get('\xa9gen', [None])[0]
                metadata["label_name"] = metadata["label_name"] or tags.get('----:com.apple.iTunes:PUBLISHER', [None])[0]
                date = tags.get('\xa9day', [None])[0]
                if date and len(date) >= 4:
                    try:
                        metadata["release_year"] = int(date[:4])
                    except ValueError:
                        pass
        except Exception as e:
            if self.verbose:
                print(f"Error reading tags from {file_path}: {e}")
                
        return metadata

    def save_features(self, track_id, features=None, internal_track_id=None, metadata=None, file_path=None):
        """Sla de geëxtraheerde features en metadata op in de database."""
        if self.engine is None:
            if self.verbose:
                print("Geen database verbinding beschikbaar om features op te slaan.")
            return False

        from sqlalchemy import Table, MetaData, Column, Float, String, Integer, Text, Boolean, text
        from sqlalchemy.dialects.mysql import insert

        md = MetaData()
        # Handmatige definitie voor robuustheid (overeenkomstig met db_init.sql)
        library_track_audio_features = Table(
            'library_track_audio_features', md,
            Column('track_id', String(255), primary_key=True),
            Column('internal_track_id', Integer),
            Column('file_path', Text),
            Column('tempo', Float),
            Column('duration', Float),
            Column('mean_spectral_centroid', Float),
            Column('std_spectral_centroid', Float),
            Column('mean_spectral_bandwidth', Float),
            Column('std_spectral_bandwidth', Float),
            Column('mean_spectral_rolloff', Float),
            Column('std_spectral_rolloff', Float),
            Column('mean_rms', Float),
            Column('std_rms', Float),
            Column('mean_zcr', Float),
            Column('std_zcr', Float),
            Column('mean_spectral_contrast', Float),
            Column('std_spectral_contrast', Float),
            Column('mfcc_1', Float),
            Column('mfcc_2', Float),
            Column('mfcc_3', Float),
            Column('mfcc_4', Float),
            Column('mfcc_5', Float),
            Column('mfcc_6', Float),
            Column('mfcc_7', Float),
            Column('mfcc_8', Float),
            Column('mfcc_9', Float),
            Column('mfcc_10', Float),
            Column('mfcc_11', Float),
            Column('mfcc_12', Float),
            Column('mfcc_13', Float),
            Column('std_mfcc_1', Float),
            Column('std_mfcc_2', Float),
            Column('std_mfcc_3', Float),
            Column('std_mfcc_4', Float),
            Column('std_mfcc_5', Float),
            Column('std_mfcc_6', Float),
            Column('std_mfcc_7', Float),
            Column('std_mfcc_8', Float),
            Column('std_mfcc_9', Float),
            Column('std_mfcc_10', Float),
            Column('std_mfcc_11', Float),
            Column('std_mfcc_12', Float),
            Column('std_mfcc_13', Float),
            Column('mean_chroma', Float),
            Column('std_chroma', Float),
            Column('artist_name', String(255)),
            Column('label_name', String(255)),
            Column('release_year', Integer),
            Column('source_platform', String(50)),
            Column('bpm_tag', Float),
            Column('genre_tag', String(100)),
            extend_existing=True
        )

        library_track_ml_labels = Table(
            'library_track_ml_labels', md,
            Column('track_id', String(255), primary_key=True),
            Column('ml_genre', String(100)),
            Column('ml_review_status', String(20)),
            Column('approved_for_training', Boolean),
            extend_existing=True
        )

        values = {
            'track_id': track_id,
            'internal_track_id': internal_track_id,
            'file_path': file_path
        }
        
        if features:
            values.update({
                'tempo': features['tempo'],
                'duration': features['duration'],
                'mean_spectral_centroid': features['mean_spectral_centroid'],
                'std_spectral_centroid': features.get('std_spectral_centroid'),
                'mean_spectral_bandwidth': features.get('mean_spectral_bandwidth'),
                'std_spectral_bandwidth': features.get('std_spectral_bandwidth'),
                'mean_spectral_rolloff': features['mean_spectral_rolloff'],
                'std_spectral_rolloff': features.get('std_spectral_rolloff'),
                'mean_rms': features['mean_rms'],
                'std_rms': features.get('std_rms'),
                'mean_zcr': features['mean_zcr'],
                'std_zcr': features.get('std_zcr'),
                'mean_spectral_contrast': features.get('mean_spectral_contrast'),
                'std_spectral_contrast': features.get('std_spectral_contrast'),
                'mean_chroma': features['mean_chroma'],
                'std_chroma': features.get('std_chroma')
            })
            
            # Voeg MFCC's toe
            for i in range(1, 14):
                if f"mfcc_{i}" in features:
                    values[f"mfcc_{i}"] = features[f"mfcc_{i}"]
                if f"std_mfcc_{i}" in features:
                    values[f"std_mfcc_{i}"] = features[f"std_mfcc_{i}"]
        
        if metadata:
            values.update({
                'artist_name': metadata.get('artist_name'),
                'label_name': metadata.get('label_name'),
                'release_year': metadata.get('release_year'),
                'source_platform': metadata.get('source_platform'),
                'bpm_tag': metadata.get('bpm_tag'),
                'genre_tag': metadata.get('genre_tag')
            })

        with self.engine.begin() as conn:
            # Sla audio features op
            stmt = insert(library_track_audio_features).values(**values)
            update_dict = {k: v for k, v in values.items() if k != 'track_id'}
            on_duplicate_stmt = stmt.on_duplicate_key_update(**update_dict)
            conn.execute(on_duplicate_stmt)
            
            # Vul ook library_track_ml_labels in als we een genre_tag hebben
            genre_tag = metadata.get('genre_tag') if metadata else None
            if genre_tag:
                label_values = {
                    'track_id': track_id,
                    'ml_genre': genre_tag,
                    'ml_review_status': 'unreviewed',
                    'approved_for_training': False
                }
                label_stmt = insert(library_track_ml_labels).values(**label_values)
                # We updaten het genre NIET als het al bestaat, om handmatige correcties te behouden
                # tenzij het nog 'unreviewed' is? 
                # Laten we voor nu alleen inserten als het er niet is, of alleen de status/approved behouden.
                # De gebruiker wil het vullen zodat hij het later kan approven.
                on_duplicate_label = label_stmt.on_duplicate_key_update(
                    ml_genre=label_stmt.inserted.ml_genre
                )
                conn.execute(on_duplicate_label)
            
        if self.verbose:
            print(f"Features en metadata opgeslagen voor track_id: {track_id}")
        return True

    def is_already_analyzed(self, track_id):
        """Check of een track al geanalyseerd is."""
        if self.engine is None:
            return False
            
        from sqlalchemy import text
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT 1 FROM library_track_audio_features WHERE track_id = :id"),
                    {"id": track_id}
                ).fetchone()
                return result is not None
        except Exception:
            return False

    def get_track_info(self, file_path):
        """Probeer track informatie (internal_id en legacy hash) te vinden."""
        import hashlib
        path_hash = hashlib.sha256(file_path.encode()).hexdigest()
        
        if self.engine is None:
            return path_hash, None

        from sqlalchemy import text
        try:
            with self.engine.connect() as conn:
                # 1. Zoek in library_media_files
                result = conn.execute(
                    text("SELECT track_id, id FROM library_media_files WHERE file_path_hash = :hash OR file_path = :path"),
                    {"hash": path_hash, "path": file_path}
                ).fetchone()
                
                if result:
                    internal_track_id = result[0]
                    media_file_id = result[1]
                    
                    # Als er geen track_id is, maak er een aan
                    if internal_track_id is None:
                        # Probeer een titel te extraheren uit het pad voor de library_tracks tabel
                        title = Path(file_path).stem
                        res = conn.execute(
                            text("INSERT INTO library_tracks (title, track_uid) VALUES (:title, :uid)"),
                            {"title": title, "uid": path_hash}
                        )
                        # internal_track_id = res.lastrowid # Afhankelijk van driver
                        # Veiligere manier:
                        internal_track_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()
                        
                        # Update library_media_files koppeling
                        conn.execute(
                            text("UPDATE library_media_files SET track_id = :tid WHERE id = :mid"),
                            {"tid": internal_track_id, "mid": media_file_id}
                        )
                        conn.commit()
                        
                    return path_hash, internal_track_id
                else:
                    # Bestand onbekend in library_media_files, voeg toe
                    title = Path(file_path).stem
                    # Maak track aan
                    conn.execute(
                        text("INSERT INTO library_tracks (title, track_uid) VALUES (:title, :uid)"),
                        {"title": title, "uid": path_hash}
                    )
                    internal_track_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()
                    
                    # Voeg media_file toe
                    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                    file_mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else 0
                    
                    conn.execute(
                        text("INSERT INTO library_media_files (file_path, file_path_hash, track_id, file_size, file_mtime) VALUES (:path, :hash, :tid, :size, :mtime)"),
                        {"path": file_path, "hash": path_hash, "tid": internal_track_id, "size": file_size, "mtime": file_mtime}
                    )
                    conn.commit()
                    return path_hash, internal_track_id
                    
        except Exception as e:
            if self.verbose:
                print(f"Fout bij opzoeken/aanmaken track info: {e}")
            
        return path_hash, None

    def analyze_track(self, file_path, save=False, skip_existing=False, tags_only=False):
        """Voer volledige analyse uit op een track."""
        track_hash, internal_id = self.get_track_info(file_path)
        
        # Gebruik de internal_id als hoofd-ID voor checks als die er is, anders de hash
        id_for_check = str(internal_id) if internal_id else track_hash
        
        if skip_existing and not tags_only and self.is_already_analyzed(id_for_check):
            if self.verbose:
                print(f"Skipping already analyzed track: {file_path}")
            return None

        metadata = self.extract_metadata(file_path)
        features = None
        
        if not tags_only:
            y, sr = self.load_audio(file_path)
            if y is not None:
                features = self.extract_audio_features(y, sr)
        
        if save:
            self.save_features(track_hash, features, internal_track_id=internal_id, metadata=metadata, file_path=file_path)
            
        return {**(features or {}), **metadata}

    def analyze_folder(self, folder_path, save=False, parallel=False, skip_existing=True, tags_only=False):
        """Analyseer alle ondersteunde audiobestanden in een map."""
        supported_extensions = ('.mp3', '.flac', '.wav', '.m4a', '.ogg')
        files_to_analyze = []
        
        print(f"Zoeken naar bestanden in {folder_path}...")
        for root, dirs, files in os.walk(folder_path):
            # Skip @eaDir (Synology metadata)
            if '@eaDir' in root:
                continue
            for file in files:
                if file.lower().endswith(supported_extensions):
                    files_to_analyze.append(os.path.join(root, file))
            
            # Feedback tijdens scannen
            if len(files_to_analyze) > 0 and len(files_to_analyze) % 500 == 0:
                print(f"  ... {len(files_to_analyze)} bestanden gevonden ...", end='\r', flush=True)

        if not files_to_analyze:
            print(f"Geen ondersteunde bestanden gevonden in {folder_path}")
            return

        print(f"\nGevonden: {len(files_to_analyze)} bestanden in {folder_path}")
        
        # Zet verbose uit als we tqdm gebruiken om output clean te houden
        original_verbose = self.verbose
        self.verbose = not (parallel or len(files_to_analyze) > 10)

        if parallel and len(files_to_analyze) > 1:
            print(f"Start parallelle analyse met {self.max_workers} workers...")
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(self.analyze_track, f, save, skip_existing, tags_only): f for f in files_to_analyze}
                for future in tqdm(as_completed(futures), total=len(files_to_analyze), desc="Analyzing"):
                    f = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        print(f"Fout bij analyseren van {f}: {e}")
        else:
            for file_path in tqdm(files_to_analyze, desc="Analyzing"):
                if self.verbose:
                    print(f"\n--- Analysing: {os.path.basename(file_path)} ---")
                self.analyze_track(file_path, save=save, skip_existing=skip_existing, tags_only=tags_only)
        
        self.verbose = original_verbose

    def get_training_data(self, min_quality='human_verified', use_tags_as_fallback=True, include_unapproved=False):
        """Haal gecombineerde features en library_labels op voor training."""
        if self.engine is None:
            return None
            
        import pandas as pd
        from sqlalchemy import text
        
        # We gebruiken een COALESCE om de genre_tag als fallback te gebruiken als ml_genre leeg is
        genre_col = "COALESCE(l.ml_genre, f.genre_tag)" if use_tags_as_fallback else "l.ml_genre"
        
        if include_unapproved:
            # Voor test-doeleinden: haal ALLES op wat een genre heeft (ml_genre of tag)
            query = f"""
                SELECT f.*, 
                       {genre_col} as ml_genre, 
                       l.ml_review_status, l.approved_for_training
                FROM library_track_audio_features f
                LEFT JOIN library_track_ml_labels l ON f.track_id = l.track_id
                WHERE ({genre_col} IS NOT NULL)
            """
        else:
            query = f"""
                SELECT f.*, 
                       {genre_col} as ml_genre, 
                       l.ml_review_status, l.approved_for_training
                FROM library_track_audio_features f
                LEFT JOIN library_track_ml_labels l ON f.track_id = l.track_id
                WHERE (l.approved_for_training = 1)
            """
            
            if use_tags_as_fallback:
                # Als we tags gebruiken, mogen we ook library_tracks meenemen die nog geen label record hebben 
                # maar wel een genre_tag hebben
                query = f"""
                    SELECT f.*, 
                           {genre_col} as ml_genre, 
                           l.ml_review_status, l.approved_for_training
                    FROM library_track_audio_features f
                    LEFT JOIN library_track_ml_labels l ON f.track_id = l.track_id
                    WHERE (l.approved_for_training = 1) 
                       OR (l.id IS NULL AND f.genre_tag IS NOT NULL)
                       OR (l.ml_genre IS NULL AND f.genre_tag IS NOT NULL AND l.ml_review_status != 'do_not_train')
                """
        
        if min_quality == 'human_verified' and not use_tags_as_fallback and not include_unapproved:
            query += " AND l.ml_review_status = 'human_verified'"
            
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(text(query), conn)
                return df
        except Exception as e:
            print(f"Error fetching training data: {e}")
            return None

    def get_subgenre_hierarchy(self):
        """Haal de subgenre hiërarchie op uit de database."""
        if self.engine is None:
            return {}
            
        from sqlalchemy import text
        query = "SELECT subgenre, genre FROM rules_subgenre_hierarchy"
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                hierarchy = {}
                for row in result:
                    sub = row[0]
                    parent = row[1]
                    if sub not in hierarchy:
                        hierarchy[sub] = []
                    hierarchy[sub].append(parent)
                return hierarchy
        except Exception as e:
            print(f"Error fetching subgenre hierarchy: {e}")
            return {}

    def run_full_scan(self, save=False, parallel=False, tags_only=False):
        """Voer een volledige scan uit op de muziekcollectie (vergelijkbaar met tagger)."""
        music_path = os.getenv("MUSIC_PATH", "/mnt/music")
        eps_path = os.getenv("EPS_PATH", os.path.join(music_path, "EPs"))
        
        folders_to_scan = []
        
        # 1. EPs / Labels
        if os.path.exists(eps_path):
            folders_to_scan.append(eps_path)
            
        # 2. Platform mappen
        for platform in ['Soundcloud', 'Youtube', 'Telegram']:
            p_path = os.path.join(music_path, platform)
            if os.path.exists(p_path):
                folders_to_scan.append(p_path)
                
        # 3. Generieke mappen
        generic_folders = ['Livesets', 'Podcasts', 'Top 100', 'Warm Up Mixes']
        for gf in generic_folders:
            gf_path = os.path.join(music_path, gf)
            if os.path.exists(gf_path):
                folders_to_scan.append(gf_path)
        
        if not folders_to_scan:
            print(f"Geen mappen gevonden om te scannen in {music_path}")
            # Val terug op het hoofdpad als er niets specifieks gevonden is
            if os.path.exists(music_path):
                folders_to_scan = [music_path]
            else:
                return

        print(f"Start volledige scan op {len(folders_to_scan)} hoofdmappen...")
        for folder in folders_to_scan:
            print(f"\n>>> Scannen van map: {folder}")
            self.analyze_folder(folder, save=save, parallel=parallel, tags_only=tags_only)

if __name__ == "__main__":
    if len(sys.argv) < 2 and "--all" not in sys.argv:
        print("Gebruik: python analyzer.py <path_to_audio_file_or_folder> [--save] [--parallel] [--all] [--tags-only]")
        sys.exit(1)

    path = None
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        path = sys.argv[1]
        
    save_to_db = "--save" in sys.argv
    parallel_mode = "--parallel" in sys.argv
    full_scan = "--all" in sys.argv
    tags_only = "--tags-only" in sys.argv
    
    # Zoek het argument dat het pad is (als niet --all)
    if not full_scan and path is None:
        for arg in sys.argv[1:]:
            if not arg.startswith("--"):
                path = arg
                break
    
    analyzer = TrackAnalyzer(max_workers=4)
    
    if full_scan:
        analyzer.run_full_scan(save=save_to_db, parallel=parallel_mode, tags_only=tags_only)
    elif path:
        if os.path.isdir(path):
            analyzer.analyze_folder(path, save=save_to_db, parallel=parallel_mode, tags_only=tags_only)
        else:
            results = analyzer.analyze_track(path, save=save_to_db, tags_only=tags_only)
            if results:
                print("\nAnalyse resultaten:")
                for k, v in results.items():
                    print(f"  {k}: {v}")
            else:
                print("Analyse mislukt.")
    else:
        print("Geen pad opgegeven en --all niet gebruikt.")
