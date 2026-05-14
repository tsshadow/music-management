import json
import re
import os
import sys

# Add project root to path to import services
sys.path.append(os.getcwd())

try:
    from services.common.settings import Settings
    Settings() # This calls load_dotenv()
    # Force reload environment variables just in case
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

# Configurable mappings for "auto-completing" genres
CORRECTIONS = {
    'raw': 'Raw Hardstyle',
    'uptempo': 'Uptempo Hardcore',
    'frenchcore': 'Frenchcore',
    'hardcore': 'Hardcore',
    'hardstyle': 'Hardstyle',
    'industrial': 'Industrial Hardcore',
    'speedcore': 'Speedcore',
    'terror': 'Terror',
    'tekno': 'Tekno',
    'tribecore': 'Tribecore',
    'mainstream hardcore': 'Mainstream Hardcore',
    'mainstream hardstyle': 'Mainstream Hardstyle',
    'euphoric hardstyle': 'Euphoric Hardstyle',
    'raw hardstyle': 'Raw Hardstyle',
    'uptempo hardcore': 'Uptempo Hardcore',
    'early hardcore': 'Early Hardcore',
    'early hardstyle': 'Early Hardstyle',
    'happy hardcore': 'Happy Hardcore',
    'hard techno': 'Hard Techno',
    'acid': 'Acid',
    'acidcore': 'Acidcore',
    'crossbreed': 'Crossbreed',
    'breakcore': 'Breakcore',
    'drum & bass': "Drum 'N Bass",
    'drum \'n bass': "Drum 'N Bass",
    'dnb': "Drum 'N Bass",
}

# Regex for items that are definitely NOT genres
JUNK_PATTERNS = [
    r'^[\d\s\W]+$',  # Only numbers, spaces, or symbols (e.g., "#", "(", "2021", "---")
    r'^\d+bpm$',     # BPM values (e.g., "170BPM")
    r'^@.*',         # Social media handles
    r'^#.*',         # Hashtag lists (often junk/multiple genres)
    r'^[\'"].*',     # Starts with quote (often malformed)
    r'.*mix.*',      # Mixes
    r'.*festival.*', # Festivals
    r'.*record.*',   # Records/Labels (mostly)
    r'^vol\..*',     # Volumes
    r'^edit$',       # Edit
    r'^bootleg$',    # Bootleg
    r'^preview$',    # Preview
    r'^set$',        # Set
    r'^live$',       # Live
    r'^liveset$',    # Liveset
    r'^track$',      # Track
    r'^podcast$',    # Podcast
    r'^ep$',         # EP
    r'^album$',      # Album
    r'.*\d{4}.*',    # Years (e.g., "2024")
    r'.*likes.*',    # "10k likes" etc
]

def is_junk(value):
    val_lower = value.lower().strip()
    if len(val_lower) < 2:
        return True
    for pattern in JUNK_PATTERNS:
        if re.match(pattern, val_lower):
            return True
    return False

def get_correction(value):
    val_lower = value.lower().strip()
    # Direct match in corrections
    if val_lower in CORRECTIONS:
        return CORRECTIONS[val_lower]
    
    # Check if it contains a known keyword and we want to expand it
    # But be careful not to over-correct valid complex genres
    # For now, let's stick to explicit corrections or simple expansions
    return None

class MockHelper:
    def __init__(self, table):
        self.table = table
        self.data = {}
        self.ignored = set()

    def get_corrected_or_exists(self, key):
        return self.data.get(key, False)

    def exists(self, key):
        return key in self.ignored

    def add(self, key, corrected=None):
        if self.table == 'ignored_genres':
            self.ignored.add(key)
        else:
            self.data[key] = corrected or key
        return True

def process_genres(json_file=None, dry_run=True, interactive=False):
    genres_list = []
    if json_file:
        with open(json_file, 'r') as f:
            data = json.load(f)
        genres_list = [{'value': item['value']} for item in data['subsonic-response']['genres']['genre']]
    
    if dry_run:
        genre_helper = MockHelper('genres')
        ignored_helper = MockHelper('ignored_genres')
        backlog_helper = MockHelper('genre_backlog')
    else:
        from services.common.api.db_init import ensure_tables_exist
        ensure_tables_exist()
        
        from services.common.Helpers.FilterTableHelper import FilterTableHelper
        from services.common.Helpers.TableHelper import TableHelper
        genre_helper = FilterTableHelper('genres', 'genre', 'corrected_genre')
        ignored_helper = FilterTableHelper('ignored_genres', 'name', 'corrected_name')
        backlog_helper = TableHelper('genre_backlog', 'genre')
        
    if not json_file and not dry_run:
        print("Reading genres from database backlog...")
        genres_list = [{'value': g} for g in backlog_helper.get_all_values()]
    
    results = {
        'ignored': [],
        'corrected': [],
        'valid': [],
        'already_exists': []
    }

    for item in genres_list:
        value = item['value'].strip()
        if not value:
            continue
            
        # 1. Check if alrady in DB (including corrected_genre)
        existing_correction = genre_helper.get_corrected_or_exists(value)
        if existing_correction:
            if isinstance(existing_correction, str) and existing_correction.lower() != value.lower():
                results['already_exists'].append(f"{value} (already corrected to {existing_correction})")
            else:
                results['already_exists'].append(value)
            
            if not dry_run and hasattr(backlog_helper, 'delete'):
                 backlog_helper.delete(value)
            continue

        if ignored_helper.exists(value):
            results['already_exists'].append(value + " (ignored)")
            if not dry_run and hasattr(backlog_helper, 'delete'):
                 backlog_helper.delete(value)
            continue

        # 2. Check for junk
        if is_junk(value):
            print(f"Ignoring junk: '{value}'")
            if not dry_run:
                ignored_helper.add(value)
                if hasattr(backlog_helper, 'delete'):
                    backlog_helper.delete(value)
            results['ignored'].append(value)
            continue

        # 3. Check for hardcoded corrections
        correction = get_correction(value)
        if correction and correction.lower() != value.lower():
            print(f"Correcting (auto): '{value}' -> '{correction}'")
            if not dry_run:
                genre_helper.add(value, correction)
                if hasattr(backlog_helper, 'delete'):
                    backlog_helper.delete(value)
            results['corrected'].append(f"{value} -> {correction}")
            continue
            
        # 4. Interactive or default handling
        if interactive and not dry_run:
            print(f"\nUnknown genre detected: '{value}'")
            choice = input("[v]alid, [i]gnore, [c]orrect, [s]kip: ").lower().strip()
            if choice == 'v':
                normalized = value.title()
                genre_helper.add(value, normalized)
                backlog_helper.delete(value)
                results['valid'].append(value)
                continue
            elif choice == 'i':
                ignored_helper.add(value)
                backlog_helper.delete(value)
                results['ignored'].append(value)
                continue
            elif choice == 'c':
                new_val = input(f"Enter correction for '{value}': ").strip()
                if new_val:
                    genre_helper.add(value, new_val)
                    backlog_helper.delete(value)
                    results['corrected'].append(f"{value} -> {new_val}")
                continue

        # 5. Default: Normalize and keep if not interactive
        normalized = value.title()
        if normalized != value:
             print(f"Normalizing: '{value}' -> '{normalized}'")
             if not dry_run:
                 genre_helper.add(value, normalized)
                 if hasattr(backlog_helper, 'delete'):
                    backlog_helper.delete(value)
             results['corrected'].append(f"{value} -> {normalized}")
        else:
            print(f"Keeping as valid: '{value}'")
            if not dry_run:
                genre_helper.add(value)
                if hasattr(backlog_helper, 'delete'):
                    backlog_helper.delete(value)
            results['valid'].append(value)

    return results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Process and clean genres from Subsonic JSON or Database backlog.")
    parser.add_argument("json_file", nargs="?", help="Path to the JSON file containing genres (optional, defaults to DB backlog if --run is used).")
    parser.add_argument("--run", action="store_true", help="Actually update the database (requires dependencies).")
    parser.add_argument("--interactive", "-i", action="store_true", help="Ask for confirmation/corrections on unknown genres.")
    
    args = parser.parse_args()
    
    if not args.json_file and not args.run:
        print("Error: Specify a JSON file or use --run to process the database backlog.")
        sys.exit(1)

    res = process_genres(args.json_file, dry_run=not args.run, interactive=args.interactive)
    
    print("\n--- Summary ---")
    print(f"Ignored: {len(res['ignored'])}")
    print(f"Corrected: {len(res['corrected'])}")
    print(f"New Valid: {len(res['valid'])}")
    print(f"Already in DB: {len(res['already_exists'])}")
    
    if not args.run:
        print("\nNote: This was a DRY-RUN. Use --run to apply changes to the database.")
