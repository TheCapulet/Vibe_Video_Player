import sqlite3
import os
from pathlib import Path

class MetadataDB:
    def __init__(self, db_path='metadata.db'):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
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
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO videos (path, title, show_name, season, episode, tvmaze_id, image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (str(path), title, show_name, season, episode, tvmaze_id, image_url))

    def get_video(self, path):
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute('SELECT * FROM videos WHERE path = ?', (str(path),)).fetchone()

    def add_show(self, tvmaze_id, name, image_url=None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO shows (tvmaze_id, name, image_url)
                VALUES (?, ?, ?)
            ''', (tvmaze_id, name, image_url))

    def get_show(self, tvmaze_id):
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute('SELECT * FROM shows WHERE tvmaze_id = ?', (tvmaze_id,)).fetchone()

    def add_season(self, show_id, season_number, image_url=None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO seasons (show_id, season_number, image_url)
                VALUES (?, ?, ?)
            ''', (show_id, season_number, image_url))

    def update_show_cached_image(self, tvmaze_id, path):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE shows SET cached_image_path = ? WHERE tvmaze_id = ?', (path, tvmaze_id))