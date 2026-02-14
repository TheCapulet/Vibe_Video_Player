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
    detailed_progress = Signal(str, str, str)  # folder, stage, details (e.g., "Cobra Kai", "Downloading Season 3", "Episodes 1-10")
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
        self._min_request_interval = 0.2  # 5 requests per second max (was 0.5)
        
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
                
    def _is_container_folder(self, folder):
        """Check if folder is a container (has subfolders with videos but few direct videos)."""
        # Count direct videos (not in subfolders)
        direct_videos = []
        for ext in ['.mp4', '.mkv', '.avi']:
            direct_videos.extend(folder.glob(f'*{ext}'))
        
        # Count subfolders with videos
        subfolders_with_videos = 0
        for subfolder in folder.iterdir():
            if subfolder.is_dir() and not subfolder.name.startswith('.'):
                has_videos = any(subfolder.rglob(f'*{ext}') for ext in ['.mp4', '.mkv', '.avi'])
                if has_videos:
                    subfolders_with_videos += 1
        
        # If there are subfolders with videos and few/no direct videos, it's a container
        if subfolders_with_videos > 0 and len(direct_videos) < 3:
            logger.info(f"Skipping container folder: {folder.name} ({subfolders_with_videos} subfolders with videos, {len(direct_videos)} direct videos)")
            return True
        
        return False

    def _process_folder(self, folder_path, silent=True):
        """Process a single folder - detect show and associate episodes."""
        import time
        start_time = time.time()
        
        try:
            folder = Path(folder_path)
            if not folder.exists():
                return
                
            # Skip season folders
            if self._is_season_folder(folder.name):
                return
            
            # Skip container folders (like main Videos folder)
            if self._is_container_folder(folder):
                return
                
            # Check if folder has video files
            video_files = self._find_video_files(folder)
            if not video_files:
                return
                
            logger.info(f"[TIMER] Starting scan of: {folder.name} ({len(video_files)} videos)")
            self.signals.progress.emit(f"Scanning: {folder.name}")
            self.signals.detailed_progress.emit(folder.name, "Searching TVMaze", "Looking up show information...")
            
            # Try to detect show from folder name
            show_name = folder.name
            t1 = time.time()
            show_data, uncertain_matches = self._detect_show(show_name)
            t2 = time.time()
            logger.info(f"[TIMER] Show detection for {folder.name}: {t2-t1:.2f}s")
            
            if show_data:
                logger.info(f"[TIMER] Detected show: {show_data['name']} (confidence: {show_data.get('confidence', 'N/A')}%)")
                self.signals.show_detected.emit(str(folder), show_data['name'], show_data['tvmaze_id'])
                
                # Store show metadata
                self.signals.detailed_progress.emit(folder.name, "Downloading Metadata", f"Show: {show_data['name']}")
                t3 = time.time()
                self._store_show_metadata(show_data, folder.name)
                t4 = time.time()
                logger.info(f"[TIMER] Metadata storage for {show_data['name']}: {t4-t3:.2f}s")
                
                # Associate videos with episodes
                self.signals.detailed_progress.emit(folder.name, "Matching Episodes", f"Processing {len(video_files)} video files...")
                t5 = time.time()
                self._associate_videos(folder, show_data, video_files)
                t6 = time.time()
                logger.info(f"[TIMER] Video association for {show_data['name']}: {t6-t5:.2f}s")
                
                total_time = time.time() - start_time
                logger.info(f"[TIMER] TOTAL for {folder.name}: {total_time:.2f}s")
                
            elif uncertain_matches and not silent:
                # Uncertain match - prompt user
                logger.info(f"[TIMER] Uncertain match for '{show_name}' - {len(uncertain_matches)} possibilities")
                self.signals.show_uncertain.emit(str(folder), uncertain_matches)
            else:
                logger.info(f"[TIMER] No show found for: {show_name}")
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
        
    def _store_show_metadata(self, show_data, folder_name=""):
        """Store show, seasons, and episodes in database."""
        try:
            import time
            store_start = time.time()
            display_name = folder_name or show_data['name']
            
            # Store show (skip image downloading for speed - do it later)
            self.signals.detailed_progress.emit(display_name, "Saving Show Info", show_data['name'])
            self.db.add_show(show_data['tvmaze_id'], show_data['name'], show_data.get('image_url'))
            
            # Get show record
            show_record = self.db.get_show(show_data['tvmaze_id'])
            if not show_record:
                return
            show_id = show_record[0]
            
            # Fetch and store seasons
            self.signals.detailed_progress.emit(display_name, "Fetching Seasons", "Connecting to TVMaze...")
            t1 = time.time()
            seasons = self._rate_limited_api_call(TVMazeAPI.get_show_seasons, show_data['tvmaze_id'])
            t2 = time.time()
            logger.info(f"[TIMER] Fetched {len(seasons)} seasons for {show_data['name']}: {t2-t1:.2f}s")
            
            valid_seasons = [s for s in seasons if s and isinstance(s, dict) and 'number' in s]
            total_seasons = len(valid_seasons)
            
            for idx, season in enumerate(valid_seasons, 1):
                season_num = season['number']
                self.signals.detailed_progress.emit(display_name, f"Processing Season {season_num}", f"Season {idx} of {total_seasons}")
                
                season_image_url = (season.get('image') or {}).get('medium')
                
                # Skip image downloading for speed
                self.db.add_season(show_id, season_num, season_image_url)
                
                # Fetch and store episodes for this season
                season_record = self.db.get_season(show_id, season_num)
                if season_record:
                    season_id = season_record[0]
                    self.signals.detailed_progress.emit(display_name, f"Downloading Season {season_num}", "Fetching episode list...")
                    episodes = self._rate_limited_api_call(TVMazeAPI.get_season_episodes, season['id'])
                    logger.info(f"[TIMER] Fetched {len(episodes)} episodes for S{season_num}")
                    
                    # Update progress with episode count
                    self.signals.detailed_progress.emit(display_name, f"Storing Season {season_num}", f"{len(episodes)} episodes")
                    
                    for ep in episodes:
                        if ep and isinstance(ep, dict) and 'number' in ep and 'name' in ep:
                            ep_image_url = (ep.get('image') or {}).get('medium')
                            # Skip episode image downloading
                            self.db.add_episode(
                                season_id, 
                                ep['number'], 
                                ep['name'], 
                                ep.get('airdate'), 
                                ep.get('summary'), 
                                ep_image_url
                            )
            
            total_time = time.time() - store_start
            logger.info(f"[TIMER] Metadata storage for {show_data['name']} complete: {total_time:.2f}s")
            
            # Trigger background image download
            self._queue_image_download(show_data, seasons)
            
        except Exception as e:
            logger.exception(f"Error storing show metadata: {e}")
    
    def _queue_image_download(self, show_data, seasons):
        """Queue images for background download."""
        try:
            from pathlib import Path
            root = Path(__file__).parent.parent.parent.absolute()
            cache_dir = root / "resources" / "thumbs"
            cache_dir.mkdir(exist_ok=True, parents=True)
            
            # Download show image in background thread
            def download_images():
                try:
                    # Show poster
                    if show_data.get('image_url'):
                        cache_path = cache_dir / f"show_{show_data['tvmaze_id']}.jpg"
                        if not cache_path.exists():
                            TVMazeAPI.download_image(show_data['image_url'], str(cache_path))
                            self.db.update_show_cached_image(show_data['tvmaze_id'], str(cache_path))
                            logger.info(f"[BG] Downloaded show image for {show_data['name']}")
                    
                    # Season images (limit to first 3 seasons to save time)
                    for season in seasons[:3]:
                        if season and isinstance(season, dict) and 'number' in season:
                            season_image = (season.get('image') or {}).get('medium')
                            if season_image:
                                season_cache = cache_dir / f"season_{show_data['tvmaze_id']}_{season['number']}.jpg"
                                if not season_cache.exists():
                                    TVMazeAPI.download_image(season_image, str(season_cache))
                                    
                except Exception as e:
                    logger.exception(f"[BG] Error downloading images: {e}")
            
            # Start background download
            import threading
            threading.Thread(target=download_images, daemon=True).start()
            
        except Exception as e:
            logger.exception(f"Error queueing image download: {e}")
            
    def _associate_videos(self, folder, show_data, video_files):
        """Associate video files with episodes."""
        try:
            show_record = self.db.get_show(show_data['tvmaze_id'])
            if not show_record:
                return
            show_id = show_record[0]
            folder_name = folder.name
            
            total_videos = len(video_files)
            matched_count = 0
            
            for idx, video_path in enumerate(video_files, 1):
                try:
                    filename = Path(video_path).name
                    self.signals.detailed_progress.emit(folder_name, "Matching Videos", f"File {idx}/{total_videos}: {filename[:40]}...")
                    
                    parsed = TVMazeAPI.parse_filename(Path(video_path).stem, video_path)
                    if parsed['type'] == 'episode':
                        episode = self.db.get_episode_by_season_and_number(
                            show_id, parsed['season'], parsed['episode']
                        )
                        if episode:
                            self.db.add_video(video_path, episode_id=episode[0])
                            self.signals.episode_associated.emit(video_path, episode[3])  # episode name
                            matched_count += 1
                            logger.debug(f"Associated {video_path} with {episode[3]}")
                        else:
                            logger.warning(f"No episode match for {filename} (S{parsed['season']}E{parsed['episode']})")
                except Exception as e:
                    logger.exception(f"Error associating video {video_path}: {e}")
            
            # Final progress update
            self.signals.detailed_progress.emit(folder_name, "Complete", f"Matched {matched_count}/{total_videos} videos")
                    
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
