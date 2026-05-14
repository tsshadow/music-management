import os
import sys
import librosa
import numpy as np
import torch
import torchaudio
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

    def extract_basic_features(self, y, sr):
        """Extraheer uitgebreide muziekelementen."""
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
        
        # Tijdsdomein kenmerken
        rms = librosa.feature.rms(y=y)[0]
        zcr = librosa.feature.zero_crossing_rate(y=y)[0]
        
        # Timbre (MFCCs) - we nemen de eerste 5 voor een compact overzicht
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=5)
        
        # Harmonische inhoud (Chroma)
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        
        features = {
            "tempo": float(np.mean(tempo)),
            "duration": float(librosa.get_duration(y=y, sr=sr)),
            "mean_spectral_centroid": float(np.mean(spectral_centroids)),
            "mean_spectral_rolloff": float(np.mean(spectral_rolloff)),
            "mean_rms": float(np.mean(rms)),
            "mean_zcr": float(np.mean(zcr)),
            "mfcc_1": float(np.mean(mfccs[0])),
            "mfcc_2": float(np.mean(mfccs[1])),
            "mfcc_3": float(np.mean(mfccs[2])),
            "mfcc_4": float(np.mean(mfccs[3])),
            "mfcc_5": float(np.mean(mfccs[4])),
            "mean_chroma": float(np.mean(chroma))
        }
        
        return features

    def save_features(self, track_id, features, internal_track_id=None):
        """Sla de geëxtraheerde features op in de database."""
        if self.engine is None:
            if self.verbose:
                print("Geen database verbinding beschikbaar om features op te slaan.")
            return False

        from sqlalchemy import Table, MetaData, Column, Float, String, Integer
        from sqlalchemy.dialects.mysql import insert

        metadata = MetaData()
        # Handmatige definitie voor robuustheid (overeenkomstig met db_init.sql)
        track_audio_features = Table(
            'track_audio_features', metadata,
            Column('track_id', String(255), primary_key=True),
            Column('internal_track_id', Integer),
            Column('tempo', Float),
            Column('duration', Float),
            Column('mean_spectral_centroid', Float),
            Column('mean_spectral_rolloff', Float),
            Column('mean_rms', Float),
            Column('mean_zcr', Float),
            Column('mfcc_1', Float),
            Column('mfcc_2', Float),
            Column('mfcc_3', Float),
            Column('mfcc_4', Float),
            Column('mfcc_5', Float),
            Column('mean_chroma', Float),
            extend_existing=True
        )

        with self.engine.begin() as conn:
            stmt = insert(track_audio_features).values(
                track_id=track_id,
                internal_track_id=internal_track_id,
                tempo=features['tempo'],
                duration=features['duration'],
                mean_spectral_centroid=features['mean_spectral_centroid'],
                mean_spectral_rolloff=features['mean_spectral_rolloff'],
                mean_rms=features['mean_rms'],
                mean_zcr=features['mean_zcr'],
                mfcc_1=features['mfcc_1'],
                mfcc_2=features['mfcc_2'],
                mfcc_3=features['mfcc_3'],
                mfcc_4=features['mfcc_4'],
                mfcc_5=features['mfcc_5'],
                mean_chroma=features['mean_chroma']
            )
            # Update bij duplicate key (track_id)
            update_dict = {
                'tempo': stmt.inserted.tempo,
                'duration': stmt.inserted.duration,
                'mean_spectral_centroid': stmt.inserted.mean_spectral_centroid,
                'mean_spectral_rolloff': stmt.inserted.mean_spectral_rolloff,
                'mean_rms': stmt.inserted.mean_rms,
                'mean_zcr': stmt.inserted.mean_zcr,
                'mfcc_1': stmt.inserted.mfcc_1,
                'mfcc_2': stmt.inserted.mfcc_2,
                'mfcc_3': stmt.inserted.mfcc_3,
                'mfcc_4': stmt.inserted.mfcc_4,
                'mfcc_5': stmt.inserted.mfcc_5,
                'mean_chroma': stmt.inserted.mean_chroma
            }
            if internal_track_id is not None:
                update_dict['internal_track_id'] = stmt.inserted.internal_track_id
                
            on_duplicate_stmt = stmt.on_duplicate_key_update(**update_dict)
            conn.execute(on_duplicate_stmt)
            
        if self.verbose:
            print(f"Features opgeslagen voor track_id: {track_id} (internal: {internal_track_id})")
        return True

    def is_already_analyzed(self, track_id):
        """Check of een track al geanalyseerd is."""
        if self.engine is None:
            return False
            
        from sqlalchemy import text
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT 1 FROM track_audio_features WHERE track_id = :id"),
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
                # 1. Zoek in media_files
                result = conn.execute(
                    text("SELECT track_id, id FROM media_files WHERE file_path_hash = :hash OR file_path = :path"),
                    {"hash": path_hash, "path": file_path}
                ).fetchone()
                
                if result:
                    internal_track_id = result[0]
                    media_file_id = result[1]
                    
                    # Als er geen track_id is, maak er een aan
                    if internal_track_id is None:
                        # Probeer een titel te extraheren uit het pad voor de tracks tabel
                        title = Path(file_path).stem
                        res = conn.execute(
                            text("INSERT INTO tracks (title, track_uid) VALUES (:title, :uid)"),
                            {"title": title, "uid": path_hash}
                        )
                        # internal_track_id = res.lastrowid # Afhankelijk van driver
                        # Veiligere manier:
                        internal_track_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()
                        
                        # Update media_files koppeling
                        conn.execute(
                            text("UPDATE media_files SET track_id = :tid WHERE id = :mid"),
                            {"tid": internal_track_id, "mid": media_file_id}
                        )
                        conn.commit()
                        
                    return path_hash, internal_track_id
                else:
                    # Bestand onbekend in media_files, voeg toe
                    title = Path(file_path).stem
                    # Maak track aan
                    conn.execute(
                        text("INSERT INTO tracks (title, track_uid) VALUES (:title, :uid)"),
                        {"title": title, "uid": path_hash}
                    )
                    internal_track_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()
                    
                    # Voeg media_file toe
                    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                    file_mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else 0
                    
                    conn.execute(
                        text("INSERT INTO media_files (file_path, file_path_hash, track_id, file_size, file_mtime) VALUES (:path, :hash, :tid, :size, :mtime)"),
                        {"path": file_path, "hash": path_hash, "tid": internal_track_id, "size": file_size, "mtime": file_mtime}
                    )
                    conn.commit()
                    return path_hash, internal_track_id
                    
        except Exception as e:
            if self.verbose:
                print(f"Fout bij opzoeken/aanmaken track info: {e}")
            
        return path_hash, None

    def analyze_track(self, file_path, save=False, skip_existing=False):
        """Voer volledige analyse uit op een track."""
        track_hash, internal_id = self.get_track_info(file_path)
        
        # Gebruik de internal_id als hoofd-ID voor checks als die er is, anders de hash
        id_for_check = str(internal_id) if internal_id else track_hash
        
        if skip_existing and self.is_already_analyzed(id_for_check):
            if self.verbose:
                print(f"Skipping already analyzed track: {file_path}")
            return None

        y, sr = self.load_audio(file_path)
        if y is None:
            return None
            
        features = self.extract_basic_features(y, sr)
        
        if save and features:
            self.save_features(track_hash, features, internal_track_id=internal_id)
            
        return features

    def analyze_folder(self, folder_path, save=False, parallel=False, skip_existing=True):
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
                futures = {executor.submit(self.analyze_track, f, save, skip_existing): f for f in files_to_analyze}
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
                self.analyze_track(file_path, save=save, skip_existing=skip_existing)
        
        self.verbose = original_verbose

    def run_full_scan(self, save=False, parallel=False):
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
            self.analyze_folder(folder, save=save, parallel=parallel)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Gebruik: python analyzer.py <path_to_audio_file_or_folder> [--save] [--parallel] [--all]")
        sys.exit(1)

    path = sys.argv[1] if len(sys.argv) > 1 else None
    save_to_db = "--save" in sys.argv
    parallel_mode = "--parallel" in sys.argv
    full_scan = "--all" in sys.argv
    
    # Zoek het argument dat het pad is (als niet --all)
    if not full_scan:
        for arg in sys.argv[1:]:
            if not arg.startswith("--"):
                path = arg
                break
    
    analyzer = TrackAnalyzer(max_workers=4)
    
    if full_scan:
        analyzer.run_full_scan(save=save_to_db, parallel=parallel_mode)
    elif path:
        if os.path.isdir(path):
            analyzer.analyze_folder(path, save=save_to_db, parallel=parallel_mode)
        else:
            results = analyzer.analyze_track(path, save=save_to_db)
            if results:
                print("\nAnalyse resultaten:")
                for k, v in results.items():
                    print(f"  {k}: {v}")
            else:
                print("Analyse mislukt.")
    else:
        print("Geen pad opgegeven en --all niet gebruikt.")
