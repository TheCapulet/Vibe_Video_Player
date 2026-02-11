import requests
import re
from pathlib import Path
import os
from app.util.logger import setup_app_logger

logger = setup_app_logger('TVMAZE')

class TVMazeAPI:
    BASE_URL = 'http://api.tvmaze.com'

    @staticmethod
    def search_show(query):
        logger.debug("search_show query=%s", query)
        try:
            response = requests.get(f'{TVMazeAPI.BASE_URL}/search/shows', params={'q': query})
            response.raise_for_status()
            data = response.json()
            logger.debug("search_show returned %d results", len(data) if data else 0)
            return data
        except Exception as e:
            logger.exception("Error searching TVMaze for %s", query)
            return []

    @staticmethod
    def get_show(show_id):
        logger.debug("get_show id=%s", show_id)
        try:
            response = requests.get(f'{TVMazeAPI.BASE_URL}/shows/{show_id}')
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.exception("Error getting show %s", show_id)
            return None

    @staticmethod
    def get_show_seasons(show_id):
        logger.debug("get_show_seasons id=%s", show_id)
        try:
            response = requests.get(f'{TVMazeAPI.BASE_URL}/shows/{show_id}/seasons')
            response.raise_for_status()
            data = response.json()
            logger.debug("get_show_seasons returned %d seasons", len(data) if data else 0)
            return data
        except Exception:
            logger.exception("Error getting seasons for %s", show_id)
            return []

    @staticmethod
    def get_show_episodes(show_id):
        try:
            response = requests.get(f'{TVMazeAPI.BASE_URL}/shows/{show_id}/episodes')
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting episodes: {e}")
            return []

    @staticmethod
    def download_image(url, cache_path):
        logger.debug("download_image url=%s cache=%s", url, cache_path)
        try:
            response = requests.get(url)
            response.raise_for_status()
            with open(cache_path, 'wb') as f:
                f.write(response.content)
            logger.info("Saved image to %s", cache_path)
            return True
        except Exception:
            logger.exception("Error downloading image from %s", url)
            return False

    @staticmethod
    def parse_filename(filename):
        # Simple parsing for show S01E01 or movie patterns
        # This is basic; can be improved
        show_match = re.search(r'(.+?)\.S(\d+)E(\d+)', filename, re.IGNORECASE)
        if show_match:
            show_name = show_match.group(1).replace('.', ' ')
            season = int(show_match.group(2))
            episode = int(show_match.group(3))
            return {'type': 'episode', 'show_name': show_name, 'season': season, 'episode': episode}
        # Assume movie if no match
        return {'type': 'movie', 'title': filename}

    @staticmethod
    def auto_detect(path):
        filename = Path(path).stem
        logger.debug("auto_detect path=%s filename=%s", path, filename)
        parsed = TVMazeAPI.parse_filename(filename)
        if parsed['type'] == 'episode':
            results = TVMazeAPI.search_show(parsed['show_name'])
            if results:
                show = results[0]['show']
                logger.debug("auto_detect matched show id=%s name=%s", show.get('id'), show.get('name'))
                return {'tvmaze_id': show['id'], 'name': show['name'], 'image_url': show.get('image', {}).get('medium')}
        return None