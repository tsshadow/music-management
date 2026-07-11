import argparse
import logging
import sys
import os
import pymysql.cursors
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from services.music_manager.artist_image_fetcher.fetcher import ArtistImageFetcher
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from dotenv import load_dotenv
load_dotenv()

def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])

def main():
    setup_logging()
    parser = argparse.ArgumentParser(description='Artist Image Fetcher CLI')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    fetch_parser = subparsers.add_parser('fetch', help='Fetch images for a specific artist')
    fetch_parser.add_argument('--artist-id', type=int, help='Artist ID')
    fetch_parser.add_argument('--name', type=str, help='Artist Name')
    fetch_parser.add_argument('--force', action='store_true', help='Force refresh even if image exists')
    missing_parser = subparsers.add_parser('fetch-missing', help='Fetch images for artists missing them')
    missing_parser.add_argument('--limit', type=int, default=100, help='Limit number of artists to process')
    missing_parser.add_argument('--include-failed', action='store_true', help='Include artists that previously failed')
    refresh_parser = subparsers.add_parser('refresh', help='Refresh stale images')
    refresh_parser.add_argument('--older-than-days', type=int, default=90, help='Refresh images older than X days')
    refresh_parser.add_argument('--limit', type=int, default=100, help='Limit number of artists to process')
    parser.add_argument('--repeat', '--daemon', action='store_true', dest='repeat', help='Keep running in a loop')
    parser.add_argument('--sleeptime', type=int, default=3600, help='Time to sleep between scans (seconds)')
    args = parser.parse_args()
    fetcher = ArtistImageFetcher()
    while True:
        if args.command == 'fetch':
            if args.artist_id:
                fetcher.fetch_for_artist(args.artist_id, args.name, force_refresh=args.force)
            elif args.name:
                db = DatabaseConnector().connect()
                with db.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute('SELECT id FROM library_artists WHERE name = %s', (args.name,))
                    row = cursor.fetchone()
                    if row:
                        fetcher.fetch_for_artist(row['id'], args.name, force_refresh=args.force)
                    else:
                        print(f"Artist '{args.name}' not found in database")
            else:
                print('Either --artist-id or --name must be provided')
        elif args.command == 'fetch-missing':
            db = DatabaseConnector().connect()
            with db.cursor(pymysql.cursors.DictCursor) as cursor:
                status_filter = "(image_status IS NULL OR image_status != 'failed')"
                if args.include_failed:
                    status_filter = "(image_status IS NULL OR image_status = 'failed')"
                query = f'\n                    SELECT id, name FROM library_artists\n                    WHERE primary_image_id IS NULL AND {status_filter}\n                    LIMIT %s\n                '
                cursor.execute(query, (args.limit,))
                artists = cursor.fetchall()
                if not artists:
                    print('Found 0 artists missing images.')
                    cursor.execute('\n                        SELECT image_status, COUNT(*) as count \n                        FROM library_artists \n                        WHERE primary_image_id IS NULL \n                        GROUP BY image_status\n                    ')
                    stats = cursor.fetchall()
                    if stats:
                        print(f'Stats for NULL primary_image_id: {stats}')
                else:
                    print(f'Found {len(artists)} artists missing images')
                    for artist in artists:
                        fetcher.fetch_for_artist(artist['id'], artist['name'])
        elif args.command == 'refresh':
            db = DatabaseConnector().connect()
            with db.cursor(pymysql.cursors.DictCursor) as cursor:
                query = '\n                    SELECT id, name FROM library_artists\n                    WHERE image_updated_at < DATE_SUB(NOW(), INTERVAL %s DAY)\n                    LIMIT %s\n                '
                cursor.execute(query, (args.older_than_days, args.limit))
                artists = cursor.fetchall()
                print(f'Refreshing {len(artists)} stale artist images')
                for artist in artists:
                    fetcher.fetch_for_artist(artist['id'], artist['name'], force_refresh=True)
        else:
            parser.print_help()
            break
        if not args.repeat:
            break
        print(f'Sleeping for {args.sleeptime} seconds...')
        import time
        time.sleep(args.sleeptime)
if __name__ == '__main__':
    main()