import requests
import re
from pathlib import Path
import os

class TVMazeAPI:
    BASE_URL = 'http://api.tvmaze.com'

    @staticmethod
    def search_show(query):
        try:
            response = requests.get(f'{TVMazeAPI.BASE_URL}/search/shows', params={'q': query})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error searching TVMaze: {e}")
            return []

    @staticmethod
    def get_show(show_id):
        try:
            response = requests.get(f'{TVMazeAPI.BASE_URL}/shows/{show_id}')
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting show: {e}")
            return None

    @staticmethod
    def get_show_seasons(show_id):
        try:
            response = requests.get(f'{TVMazeAPI.BASE_URL}/shows/{show_id}/seasons')
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting seasons: {e}")
            return []

    @staticmethod
    def download_image(url, cache_path):
        try:
            response = requests.get(url)
            response.raise_for_status()
            with open(cache_path, 'wb') as f:
                f.write(response.content)
            return True
        except Exception as e:
            print(f"Error downloading image: {e}")
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
        parsed = TVMazeAPI.parse_filename(filename)
        if parsed['type'] == 'episode':
            results = TVMazeAPI.search_show(parsed['show_name'])
            if results:
                show = results[0]['show']
                return {'tvmaze_id': show['id'], 'name': show['name'], 'image_url': show.get('image', {}).get('medium')}
        return None