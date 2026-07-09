from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from services.music_manager.database import get_db_connection
from services.music_manager.routers.management import verify_api_key

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

def init_db(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255),
            message TEXT,
            topic VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

@router.get("/")
def get_notifications(limit: int = 50, auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM notifications ORDER BY created_at DESC LIMIT %s", (limit,))
            return cursor.fetchall()
    finally:
        conn.close()

@router.delete("/{notification_id}")
def delete_notification(notification_id: int, auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM notifications WHERE id = %s", (notification_id,))
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()

@router.delete("/")
def clear_notifications(auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM notifications")
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()
