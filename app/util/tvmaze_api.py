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
    def get_season_episodes(season_id):
        try:
            response = requests.get(f'{TVMazeAPI.BASE_URL}/seasons/{season_id}/episodes')
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting episodes for season {season_id}: {e}")
            return []

    @staticmethod
    def parse_filename(filename, folder_path=None):
        """Parse episode info from filename and/or folder path."""
        # Pattern 1: SXXEYY (most common in user's library)
        # Example: S01E01 - Episode Title.mkv
        simple_match = re.search(r'[Ss](\d+)[Ee](\d+)', filename)
        if simple_match:
            season = int(simple_match.group(1))
            episode = int(simple_match.group(2))
            
            # Try to get show name from folder path
            show_name = None
            if folder_path:
                path_parts = Path(folder_path).parts
                # Look for show name in parent folders
                for i, part in enumerate(path_parts):
                    if re.match(r'^season\s*\d+', part, re.IGNORECASE) or part.lower() in ['s01', 's02', 's03', 's04', 's05', 's06', 's07', 's08', 's09', 's10', 's11', 's12', 's13', 's14']:
                        # Found season folder, show name is the parent
                        if i > 0:
                            show_name = path_parts[i-1]
                            break
                # If no season folder found, use immediate parent
                if not show_name and len(path_parts) >= 2:
                    show_name = path_parts[-2]
            
            # Clean up show name
            if show_name:
                # Remove common suffixes
                show_name = re.sub(r'\s+season\s*\d+.*$', '', show_name, flags=re.IGNORECASE)
                show_name = show_name.replace('.', ' ').replace('_', ' ').strip()
            else:
                show_name = 'Unknown Show'
            
            return {'type': 'episode', 'show_name': show_name, 'season': season, 'episode': episode}
        
        # Pattern 2: Show.Name.SXXEYY (standard format)
        show_match = re.search(r'(.+?)\.S(\d+)E(\d+)', filename, re.IGNORECASE)
        if show_match:
            show_name = show_match.group(1).replace('.', ' ').replace('_', ' ').strip()
            season = int(show_match.group(2))
            episode = int(show_match.group(3))
            return {'type': 'episode', 'show_name': show_name, 'season': season, 'episode': episode}
        
        # Assume movie if no match
        return {'type': 'movie', 'title': filename}

    @staticmethod
    def auto_detect(path):
        filename = Path(path).stem
        parsed = TVMazeAPI.parse_filename(filename, path)
        if parsed['type'] == 'episode':
            results = TVMazeAPI.search_show(parsed['show_name'])
            if results:
                show = results[0]['show']
                return {'tvmaze_id': show['id'], 'name': show['name'], 'image_url': show.get('image', {}).get('medium')}
        return None

    @staticmethod
    def download_image(url, save_path):
        """Download an image from URL and save to path. Returns True on success."""
        if not url:
            return False
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            with open(save_path, 'wb') as f:
                f.write(response.content)
            return True
        except Exception as e:
            print(f"Error downloading image from {url}: {e}")
            return False