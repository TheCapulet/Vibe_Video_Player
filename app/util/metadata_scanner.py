"""
Metadata Scanner Worker
A Qt-based worker thread for scanning TV show metadata.
Uses signals/slots for thread-safe communication with UI.
"""

import threading
import time
import queue
from pathlib import Path
from qtpy.QtCore import QObject, Signal, QRunnable, QThreadPool
from app.util.tvmaze_api import TVMazeAPI
import logging

logger = logging.getLogger("METADATA_SCANNER")


class MetadataScanSignals(QObject):
    """Signals for metadata scanning operations."""
    show_detected = Signal(str, str, int)  # folder_path, show_name, tvmaze_id
    show_not_found = Signal(str)  # folder_path
    show_uncertain = Signal(str, list)  # folder_path, list of possible shows
    episode_associated = Signal(str, str)  # video_path, episode_name
    progress = Signal(str)  # status message
    finished = Signal()
    error = Signal(str, str)  # folder_path, error_message


class MetadataScanner(QObject):
    """
    Single-threaded metadata scanner with rate limiting.
    Processes folders one at a time to avoid overwhelming TVMaze API.
    """
    
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.signals = MetadataScanSignals()
        self._queue = queue.Queue()
        self._worker_thread = None
        self._stop_event = threading.Event()
        self._rate_limit_lock = threading.Lock()
        self._last_request_time = 0
        self._min_request_interval = 0.5  # 2 requests per second max
        
    def start(self):
        """Start the scanner worker thread."""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_event.clear()
            self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker_thread.start()
            logger.info("Metadata scanner started")
            
    def stop(self):
        """Stop the scanner worker thread."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)
        logger.info("Metadata scanner stopped")
        
    def queue_folder(self, folder_path, silent=True):
        """Add a folder to the scanning queue."""
        self._queue.put({
            'folder_path': str(folder_path),
            'silent': silent
        })
        logger.info(f"Queued folder for scanning: {folder_path}")
        
    def _rate_limited_api_call(self, func, *args, **kwargs):
        """Execute API call with rate limiting."""
        with self._rate_limit_lock:
            elapsed = time.time() - self._last_request_time
            if elapsed < self._min_request_interval:
                time.sleep(self._min_request_interval - elapsed)
            try:
                result = func(*args, **kwargs)
                self._last_request_time = time.time()
                return result
            except Exception as e:
                logger.exception(f"API call failed: {e}")
                raise
                
    def _worker_loop(self):
        """Main worker loop - processes folders from queue."""
        while not self._stop_event.is_set():
            try:
                # Get next folder from queue (blocking with timeout)
                item = self._queue.get(timeout=1)
                folder_path = item['folder_path']
                silent = item['silent']
                
                # Process the folder
                self._process_folder(folder_path, silent)
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.exception(f"Error in worker loop: {e}")
                
    def _process_folder(self, folder_path, silent=True):
        """Process a single folder - detect show and associate episodes."""
        try:
            folder = Path(folder_path)
            if not folder.exists():
                return
                
            # Skip season folders
            if self._is_season_folder(folder.name):
                return
                
            # Check if folder has video files
            video_files = self._find_video_files(folder)
            if not video_files:
                return
                
            logger.info(f"Processing folder: {folder.name} ({len(video_files)} videos)")
            self.signals.progress.emit(f"Scanning: {folder.name}")
            
            # Try to detect show from folder name
            show_name = folder.name
            show_data, uncertain_matches = self._detect_show(show_name)
            
            if show_data:
                logger.info(f"Detected show: {show_data['name']}")
                self.signals.show_detected.emit(str(folder), show_data['name'], show_data['tvmaze_id'])
                
                # Store show metadata
                self._store_show_metadata(show_data)
                
                # Associate videos with episodes
                self._associate_videos(folder, show_data, video_files)
            elif uncertain_matches and not silent:
                # Uncertain match - prompt user
                logger.info(f"Uncertain match for '{show_name}' - {len(uncertain_matches)} possibilities")
                self.signals.show_uncertain.emit(str(folder), uncertain_matches)
            else:
                logger.info(f"No show found for: {show_name}")
                if not silent:
                    self.signals.show_not_found.emit(str(folder))
                    
        except Exception as e:
            logger.exception(f"Error processing folder {folder_path}: {e}")
            self.signals.error.emit(folder_path, str(e))
            
    def _detect_show(self, show_name, require_exact_match=False):
        """Detect TV show from name using TVMaze API with confidence scoring.
        
        Returns:
            tuple: (detected_show_data, uncertain_matches)
            detected_show_data: dict if confident match, None otherwise
            uncertain_matches: list of possible shows with confidence < threshold
        """
        uncertain_matches = []
        try:
            results = self._rate_limited_api_call(TVMazeAPI.search_show, show_name)
            if results:
                # Score each result
                best_match = None
                best_score = 0
                
                for result in results[:3]:  # Check top 3 results
                    show = result['show']
                    
                    # Skip non-TV content
                    if show.get('type') not in ('Scripted', 'Animation', 'Reality', 'Talk Show', 'Documentary'):
                        continue
                    
                    # Calculate match score
                    tvmaze_name = show['name'].lower().strip()
                    folder_name = show_name.lower().strip()
                    
                    # Exact match = highest score
                    if tvmaze_name == folder_name:
                        score = 100
                    # Contains match = medium score
                    elif tvmaze_name in folder_name or folder_name in tvmaze_name:
                        score = 75
                    # Word match = lower score
                    else:
                        folder_words = set(folder_name.split())
                        show_words = set(tvmaze_name.split())
                        common_words = folder_words & show_words
                        if common_words:
                            score = len(common_words) / max(len(folder_words), len(show_words)) * 50
                        else:
                            score = 0
                    
                    show_data = {
                        'tvmaze_id': show['id'],
                        'name': show['name'],
                        'image_url': (show.get('image') or {}).get('medium'),
                        'type': show.get('type'),
                        'confidence': score
                    }
                    
                    if score > best_score:
                        best_score = score
                        best_match = show_data
                    
                    # Collect uncertain matches (score between 40-60)
                    if 40 <= score < 60:
                        uncertain_matches.append(show_data)
                
                # Require minimum confidence
                min_confidence = 80 if require_exact_match else 60
                
                if best_match and best_score >= min_confidence:
                    logger.info(f"Matched '{show_name}' to '{best_match['name']}' with confidence {best_score:.1f}%")
                    return best_match, uncertain_matches
                elif best_match:
                    logger.info(f"Low confidence match for '{show_name}' -> '{best_match['name']}' ({best_score:.1f}%) - needs user confirmation")
                    # Add the best match to uncertain if it wasn't already
                    if best_match not in uncertain_matches:
                        uncertain_matches.insert(0, best_match)
                    return None, uncertain_matches
                    
        except Exception as e:
            logger.exception(f"Error detecting show {show_name}: {e}")
        return None, uncertain_matches
        
    def _store_show_metadata(self, show_data):
        """Store show, seasons, and episodes in database."""
        try:
            # Download and cache show image
            from pathlib import Path
            import sys
            
            # Get root path for cache
            root = Path(__file__).parent.parent.parent.absolute()
            cache_dir = root / "resources" / "thumbs"
            cache_dir.mkdir(exist_ok=True, parents=True)
            
            cached_image_path = None
            if show_data.get('image_url'):
                cache_path = cache_dir / f"show_{show_data['tvmaze_id']}.jpg"
                if not cache_path.exists():
                    if TVMazeAPI.download_image(show_data['image_url'], str(cache_path)):
                        cached_image_path = str(cache_path)
                        logger.info(f"Downloaded show image for {show_data['name']}")
                else:
                    cached_image_path = str(cache_path)
            
            # Store show with cached image path
            self.db.add_show(show_data['tvmaze_id'], show_data['name'], show_data.get('image_url'))
            if cached_image_path:
                self.db.update_show_cached_image(show_data['tvmaze_id'], cached_image_path)
            
            # Get show record
            show_record = self.db.get_show(show_data['tvmaze_id'])
            if not show_record:
                return
            show_id = show_record[0]
            
            # Fetch and store seasons
            seasons = self._rate_limited_api_call(TVMazeAPI.get_show_seasons, show_data['tvmaze_id'])
            for season in seasons:
                if season and isinstance(season, dict) and 'number' in season:
                    season_image_url = (season.get('image') or {}).get('medium')
                    
                    # Download season image
                    season_cached_path = None
                    if season_image_url:
                        season_cache_path = cache_dir / f"season_{show_data['tvmaze_id']}_{season['number']}.jpg"
                        if not season_cache_path.exists():
                            if TVMazeAPI.download_image(season_image_url, str(season_cache_path)):
                                season_cached_path = str(season_cache_path)
                        else:
                            season_cached_path = str(season_cache_path)
                    
                    self.db.add_season(show_id, season['number'], season_cached_path or season_image_url)
                    
                    # Fetch and store episodes for this season
                    season_record = self.db.get_season(show_id, season['number'])
                    if season_record:
                        season_id = season_record[0]
                        episodes = self._rate_limited_api_call(TVMazeAPI.get_season_episodes, season['id'])
                        for ep in episodes:
                            if ep and isinstance(ep, dict) and 'number' in ep and 'name' in ep:
                                ep_image_url = (ep.get('image') or {}).get('medium')
                                
                                # Download episode image
                                ep_cached_path = None
                                if ep_image_url:
                                    ep_cache_path = cache_dir / f"ep_{show_data['tvmaze_id']}_{season['number']}_{ep['number']}.jpg"
                                    if not ep_cache_path.exists():
                                        if TVMazeAPI.download_image(ep_image_url, str(ep_cache_path)):
                                            ep_cached_path = str(ep_cache_path)
                                    else:
                                        ep_cached_path = str(ep_cache_path)
                                
                                self.db.add_episode(
                                    season_id, 
                                    ep['number'], 
                                    ep['name'], 
                                    ep.get('airdate'), 
                                    ep.get('summary'), 
                                    ep_cached_path or ep_image_url
                                )
                                
            logger.info(f"Stored metadata for {show_data['name']}")
            
        except Exception as e:
            logger.exception(f"Error storing show metadata: {e}")
            
    def _associate_videos(self, folder, show_data, video_files):
        """Associate video files with episodes."""
        try:
            show_record = self.db.get_show(show_data['tvmaze_id'])
            if not show_record:
                return
            show_id = show_record[0]
            
            for video_path in video_files:
                try:
                    parsed = TVMazeAPI.parse_filename(Path(video_path).stem, video_path)
                    if parsed['type'] == 'episode':
                        episode = self.db.get_episode_by_season_and_number(
                            show_id, parsed['season'], parsed['episode']
                        )
                        if episode:
                            self.db.add_video(video_path, episode_id=episode[0])
                            self.signals.episode_associated.emit(video_path, episode[3])  # episode name
                            logger.debug(f"Associated {video_path} with {episode[3]}")
                except Exception as e:
                    logger.exception(f"Error associating video {video_path}: {e}")
                    
        except Exception as e:
            logger.exception(f"Error associating videos: {e}")
            
    def _find_video_files(self, folder):
        """Find all video files in folder recursively."""
        video_files = []
        for ext in ['.mp4', '.mkv', '.avi']:
            video_files.extend(folder.rglob(f'*{ext}'))
        return [str(f) for f in video_files]
        
    def _is_season_folder(self, folder_name):
        """Check if folder is a season folder."""
        import re
        # Match: Season 1, Season 01, S1, S01, etc.
        patterns = [
            r'^season\s*\d+',  # Season 1, Season 01
            r'^s\d+$',         # S1, S01, S12
            r'^s\d+\s*-\s*\d+$',  # S01-S02 (multi-season folders)
        ]
        for pattern in patterns:
            if re.match(pattern, folder_name, re.IGNORECASE):
                return True
        return False


class QuickMetadataScanner:
    """
    Quick scanner that just identifies show folders without fetching metadata.
    Used for initial UI population.
    """
    
    @staticmethod
    def scan_for_shows(root_folder):
        """Quickly identify potential show folders."""
        shows = []
        folder = Path(root_folder)
        
        if not folder.exists():
            return shows
            
        # Check each subfolder
        for subfolder in folder.iterdir():
            if subfolder.is_dir() and not subfolder.name.startswith('.'):
                # Check if it has videos (but don't scan recursively yet)
                has_videos = any(
                    subfolder.glob(f'*{ext}') 
                    for ext in ['.mp4', '.mkv', '.avi']
                )
                if has_videos:
                    shows.append({
                        'name': subfolder.name,
                        'path': str(subfolder),
                        'video_count': len(list(subfolder.glob('*.mp4'))) + 
                                     len(list(subfolder.glob('*.mkv'))) +
                                     len(list(subfolder.glob('*.avi')))
                    })
                    
        return shows
