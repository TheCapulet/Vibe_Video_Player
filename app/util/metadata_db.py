import sqlite3
import os
from pathlib import Path
import threading
import logging

logger = logging.getLogger("METADATA_DB")

class MetadataDB:
    def __init__(self, db_path='metadata.db'):
        self.db_path = db_path
        self._lock = threading.Lock()  # Thread lock for concurrent access
        self.init_db()
    
    def reset_database(self):
        """Reset the entire database - delete all data."""
        with self._lock:
            try:
                # On Windows, we can't delete while connections are open
                # Instead, we'll clear all tables
                logger.info("Clearing all database tables...")
                
                with sqlite3.connect(self.db_path, timeout=30) as conn:
                    # Get all table names
                    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = cursor.fetchall()
                    
                    # Delete all data from each table
                    for table in tables:
                        table_name = table[0]
                        if table_name != 'sqlite_sequence':  # Skip internal SQLite table
                            conn.execute(f'DELETE FROM {table_name}')
                    
                    # Reset auto-increment counters
                    conn.execute("DELETE FROM sqlite_sequence")
                    
                    # Vacuum to reclaim space
                    conn.execute("VACUUM")
                
                logger.info("Database reset complete - all tables cleared")
                return True
            except Exception as e:
                logger.exception(f"Error resetting database: {e}")
                return False
    
    def clear_show_metadata(self):
        """Clear all show metadata but keep video paths."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path, timeout=30) as conn:
                    # Clear all show-related tables
                    conn.execute('DELETE FROM episodes')
                    conn.execute('DELETE FROM seasons')
                    conn.execute('DELETE FROM shows')
                    # Reset episode associations
                    conn.execute('UPDATE videos SET episode_id = NULL')
                    logger.info("Cleared all show metadata")
                return True
            except Exception as e:
                logger.exception(f"Error clearing show metadata: {e}")
                return False

    def init_db(self):
        with self._lock:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS videos (
                        id INTEGER PRIMARY KEY,
                        path TEXT UNIQUE,
                        title TEXT,
                        show_name TEXT,
                        season INTEGER,
                        episode INTEGER,
                        tvmaze_id INTEGER,
                        image_url TEXT,
                        cached_image_path TEXT,
                        episode_id INTEGER,
                        FOREIGN KEY(episode_id) REFERENCES episodes(id)
                    )
                ''')
                # Migration: add episode_id column if it doesn't exist
                try:
                    conn.execute('SELECT episode_id FROM videos LIMIT 1')
                except sqlite3.OperationalError:
                    conn.execute('ALTER TABLE videos ADD COLUMN episode_id INTEGER REFERENCES episodes(id)')
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS shows (
                        id INTEGER PRIMARY KEY,
                        tvmaze_id INTEGER UNIQUE,
                        name TEXT,
                        image_url TEXT,
                        cached_image_path TEXT
                    )
                ''')
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS seasons (
                        id INTEGER PRIMARY KEY,
                        show_id INTEGER,
                        season_number INTEGER,
                        image_url TEXT,
                        cached_image_path TEXT,
                        FOREIGN KEY(show_id) REFERENCES shows(id)
                    )
                ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY,
                    season_id INTEGER,
                    episode_number INTEGER,
                    name TEXT,
                    airdate TEXT,
                    summary TEXT,
                    image_url TEXT,
                    cached_image_path TEXT,
                    FOREIGN KEY(season_id) REFERENCES seasons(id)
                )
            ''')

    def add_video(self, path, title=None, show_name=None, season=None, episode=None, tvmaze_id=None, image_url=None, episode_id=None):
        with self._lock:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO videos (path, title, show_name, season, episode, tvmaze_id, image_url, episode_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (str(path), title, show_name, season, episode, tvmaze_id, image_url, episode_id))

    def get_video(self, path):
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            return conn.execute('SELECT * FROM videos WHERE path = ?', (str(path),)).fetchone()

    def add_show(self, tvmaze_id, name, image_url=None):
        with self._lock:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO shows (tvmaze_id, name, image_url)
                    VALUES (?, ?, ?)
                ''', (tvmaze_id, name, image_url))

    def get_show(self, tvmaze_id):
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            return conn.execute('SELECT * FROM shows WHERE tvmaze_id = ?', (tvmaze_id,)).fetchone()

    def get_all_shows(self):
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            return conn.execute('SELECT * FROM shows').fetchall()

    def add_season(self, show_id, season_number, image_url=None):
        with self._lock:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO seasons (show_id, season_number, image_url)
                    VALUES (?, ?, ?)
                ''', (show_id, season_number, image_url))

    def get_season(self, show_id, season_number):
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            return conn.execute('SELECT * FROM seasons WHERE show_id = ? AND season_number = ?', (show_id, season_number)).fetchone()

    def add_episode(self, season_id, episode_number, name, airdate=None, summary=None, image_url=None):
        with self._lock:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO episodes (season_id, episode_number, name, airdate, summary, image_url)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (season_id, episode_number, name, airdate, summary, image_url))

    def get_episodes_for_season(self, season_id):
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            return conn.execute('SELECT * FROM episodes WHERE season_id = ? ORDER BY episode_number', (season_id,)).fetchall()

    def get_episode(self, season_id, episode_number):
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            return conn.execute('SELECT * FROM episodes WHERE season_id = ? AND episode_number = ?', (season_id, episode_number)).fetchone()

    def get_episode_by_season_and_number(self, show_id, season_number, episode_number):
        """Get episode by show_id, season_number, and episode_number."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            return conn.execute('''
                SELECT e.* FROM episodes e
                JOIN seasons s ON e.season_id = s.id
                WHERE s.show_id = ? AND s.season_number = ? AND e.episode_number = ?
            ''', (show_id, season_number, episode_number)).fetchone()

    def get_seasons_for_show(self, show_id):
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            return conn.execute('SELECT * FROM seasons WHERE show_id = ? ORDER BY season_number', (show_id,)).fetchall()

    def get_video_for_episode(self, episode_id):
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            result = conn.execute('SELECT path FROM videos WHERE episode_id = ?', (episode_id,)).fetchone()
            return result[0] if result else None

    def get_episode_by_id(self, episode_id):
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            return conn.execute('SELECT * FROM episodes WHERE id = ?', (episode_id,)).fetchone()

    def get_season_by_id(self, season_id):
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            return conn.execute('SELECT * FROM seasons WHERE id = ?', (season_id,)).fetchone()

    def update_video_path(self, old_path, new_path):
        with self._lock:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute('UPDATE videos SET path = ? WHERE path = ?', (str(new_path), str(old_path)))

    def update_show_cached_image(self, tvmaze_id, cached_image_path):
        with self._lock:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute('UPDATE shows SET cached_image_path = ? WHERE tvmaze_id = ?', (cached_image_path, tvmaze_id))

    def remove_show(self, show_id):
        """Remove a show and all its associated data from the database."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path, timeout=30) as conn:
                    # Get all season IDs for this show
                    seasons = conn.execute('SELECT id FROM seasons WHERE show_id = ?', (show_id,)).fetchall()
                    
                    # Remove all episodes for these seasons
                    for season in seasons:
                        season_id = season[0]
                        # Remove video associations first
                        conn.execute('''
                            UPDATE videos SET episode_id = NULL 
                            WHERE episode_id IN (
                                SELECT id FROM episodes WHERE season_id = ?
                            )
                        ''', (season_id,))
                        # Remove episodes
                        conn.execute('DELETE FROM episodes WHERE season_id = ?', (season_id,))
                    
                    # Remove seasons
                    conn.execute('DELETE FROM seasons WHERE show_id = ?', (show_id,))
                    
                    # Remove show
                    conn.execute('DELETE FROM shows WHERE id = ?', (show_id,))
                    
                    logger.info(f"Removed show {show_id} and all associated data")
                    return True
            except Exception as e:
                logger.exception(f"Error removing show {show_id}: {e}")
                return False

    def associate_video_with_episode(self, video_path, episode_id):
        """Manually associate a video file with an episode."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path, timeout=30) as conn:
                    conn.execute('UPDATE videos SET episode_id = ? WHERE path = ?', (episode_id, video_path))
                    logger.info(f"Associated video {video_path} with episode {episode_id}")
                    return True
            except Exception as e:
                logger.exception(f"Error associating video with episode: {e}")
                return False