"""The voice guide in real voices: one recording per guide sentence and language.

The guide's sentences are the app's English texts (the same keys as the translation
files). Admins record them in the admin page's studio. People who use that language then
hear the recording instead of a phone's computer voice, which most phones don't have for
languages like Fulfulde, Sango or Lingala. Kept in the database (base64 text) because
Render's free disk is wiped on every restart.
"""
from datetime import datetime

from database.db import get_connection


def save_recording(language, text, mime_type, audio_base64, user_id):
    """Replaces any recording of this sentence in this language. A new id each time
    means phones never play an old cached copy."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM guide_recordings WHERE language = ? AND textKey = ?", (language, text))
    cursor.execute(
        """
        INSERT INTO guide_recordings (language, textKey, mimeType, audioData, recordedBy, createdAt)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (language, text, mime_type, audio_base64, user_id, datetime.utcnow().isoformat())
    )
    recording_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return recording_id


def list_recordings(language):
    """[{id, text, mimeType}] for a language, without the audio itself."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, textKey AS text, mimeType FROM guide_recordings WHERE language = ? ORDER BY id",
        (language,)
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_recording(recording_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM guide_recordings WHERE id = ?", (recording_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_recording(recording_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM guide_recordings WHERE id = ?", (recording_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def counts_by_language():
    """{language: number of recorded sentences}, for languages with at least one."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT language, COUNT(*) AS count FROM guide_recordings GROUP BY language")
    counts = {row["language"]: row["count"] for row in cursor.fetchall()}
    conn.close()
    return counts
