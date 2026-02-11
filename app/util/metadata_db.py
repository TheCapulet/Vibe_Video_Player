import sqlite3
import os
from pathlib import Path
from app.util.logger import setup_app_logger

logger = setup_app_logger('METADB')

class MetadataDB:
    def __init__(self, db_path='metadata.db'):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        logger.debug("Initializing metadata DB at %s", self.db_path)
        with sqlite3.connect(self.db_path) as conn:
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
                    cached_image_path TEXT
                )
            ''')
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

    def add_video(self, path, title=None, show_name=None, season=None, episode=None, tvmaze_id=None, image_url=None):
        logger.info("Adding video %s show=%s S%s E%s tvmaze=%s", path, show_name, season, episode, tvmaze_id)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO videos (path, title, show_name, season, episode, tvmaze_id, image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (str(path), title, show_name, season, episode, tvmaze_id, image_url))

    def get_video(self, path):
        logger.debug("Query get_video path=%s", path)
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute('SELECT * FROM videos WHERE path = ?', (str(path),)).fetchone()

    def get_videos_for_episode(self, tvmaze_id, season, episode):
        logger.debug("Query get_videos_for_episode tvmaze=%s season=%s episode=%s", tvmaze_id, season, episode)
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute('SELECT * FROM videos WHERE tvmaze_id = ? AND season = ? AND episode = ?', (tvmaze_id, season, episode)).fetchall()

    def add_show(self, tvmaze_id, name, image_url=None):
        logger.info("Adding show tvmaze_id=%s name=%s image=%s", tvmaze_id, name, image_url)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO shows (tvmaze_id, name, image_url)
                VALUES (?, ?, ?)
            ''', (tvmaze_id, name, image_url))

    def get_show(self, tvmaze_id):
        logger.debug("Query get_show tvmaze_id=%s", tvmaze_id)
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute('SELECT * FROM shows WHERE tvmaze_id = ?', (tvmaze_id,)).fetchone()

    def get_all_shows(self):
        logger.debug("Query get_all_shows")
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute('SELECT * FROM shows').fetchall()

    def add_season(self, show_id, season_number, image_url=None):
        logger.info("Adding season show_id=%s season=%s image=%s", show_id, season_number, image_url)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO seasons (show_id, season_number, image_url)
                VALUES (?, ?, ?)
            ''', (show_id, season_number, image_url))

    def update_show_cached_image(self, tvmaze_id, path):
        logger.info("Updating cached image for show %s -> %s", tvmaze_id, path)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE shows SET cached_image_path = ? WHERE tvmaze_id = ?', (path, tvmaze_id))