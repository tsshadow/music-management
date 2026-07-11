import os
import pymysql
from dbutils.pooled_db import PooledDB
from dotenv import load_dotenv
load_dotenv()
_pool = None

def get_db_pool():
    global _pool
    if _pool is None:
        try:
            _pool = PooledDB(creator=pymysql, maxconnections=20, mincached=2, maxcached=5, maxshared=0, blocking=True, maxusage=None, setsession=[], ping=4, host=os.getenv('DB_HOST', 'db'), port=int(os.getenv('DB_PORT', '3306')), user=os.getenv('DB_USER', 'music-management'), password=os.getenv('DB_PASS', ''), database=os.getenv('DB_DB', 'music-management'), cursorclass=pymysql.cursors.DictCursor, autocommit=True)
        except Exception as e:
            print(f'Failed to create connection pool: {e}')
    return _pool

def get_db_connection():
    pool = get_db_pool()
    if pool:
        return pool.connection()
    return None