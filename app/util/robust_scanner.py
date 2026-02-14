"""
Robust Metadata Scanner
A completely rewritten scanner with proper queue management, error handling, and progress tracking.
"""

import threading
import time
import queue
from pathlib import Path
from qtpy.QtCore import QObject, Signal, QThread
from app.util.tvmaze_api import TVMazeAPI
import logging

logger = logging.getLogger("ROBUST_SCANNER")


class ScanJob:
    """Represents a single folder to be scanned."""
    def __init__(self, folder_path, silent=False):
        self.folder_path = folder_path
        self.silent = silent
        self.status = 'pending'  # pending, scanning, complete, error, uncertain
        self.show_data = None
        self.error_message = None
        self.start_time = None
        self.end_time = None


class RobustMetadataScanner(QObject):
    """
    Robust metadata scanner with proper state management.
    
    Features:
    - Processes folders sequentially with proper error recovery
    - Tracks job state (pending/scanning/complete/error/uncertain)
    - Non-blocking uncertain match handling
    - Comprehensive logging
    - Proper completion detection
    """
    
    # Signals for UI updates
    job_started = Signal(str)  # folder_path
    job_progress = Signal(str, str, str)  # folder, stage, details
    job_completed = Signal(str, object)  # folder_path, show_data (or None)
    job_error = Signal(str, str)  # folder_path, error_message
    job_uncertain = Signal(str, list)  # folder_path, possible_shows
    all_jobs_complete = Signal()
    scan_stats = Signal(int, int, int)  # total, completed, errors
    
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.jobs = []  # List of ScanJob objects
        self.current_job_index = -1
        self.is_scanning = False
        self._lock = threading.Lock()
        self._worker_thread = None
        self._stop_requested = False
        
        # Rate limiting
        self._last_api_call = 0
        self._api_delay = 0.2  # 5 requests per second
        
    def add_job(self, folder_path, silent=False):
        """Add a folder to the scan queue."""
        with self._lock:
            job = ScanJob(folder_path, silent)
            self.jobs.append(job)
            logger.info(f"Added job: {folder_path}")
            return len(self.jobs)
    
    def start_scan(self):
        """Start processing all jobs."""
        with self._lock:
            if self.is_scanning:
                logger.warning("Scan already in progress")
                return False
            
            if not self.jobs:
                logger.warning("No jobs to process")
                return False
            
            self.is_scanning = True
            self.current_job_index = 0
            self._stop_requested = False
        
        # Start worker thread
        self._worker_thread = threading.Thread(target=self._scan_worker, daemon=True)
        self._worker_thread.start()
        logger.info(f"Started scan with {len(self.jobs)} jobs")
        return True
    
    def stop_scan(self):
        """Request scan to stop."""
        self._stop_requested = True
        logger.info("Scan stop requested")
    
    def reset(self):
        """Clear all jobs and reset state."""
        with self._lock:
            self.stop_scan()
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=2)
            self.jobs.clear()
            self.current_job_index = -1
            self.is_scanning = False
            logger.info("Scanner reset")
    
    def get_stats(self):
        """Get current scan statistics."""
        with self._lock:
            total = len(self.jobs)
            completed = sum(1 for j in self.jobs if j.status in ('complete', 'error', 'uncertain'))
            errors = sum(1 for j in self.jobs if j.status == 'error')
            return total, completed, errors
    
    def _rate_limited_api_call(self, func, *args, **kwargs):
        """Execute API call with rate limiting."""
        elapsed = time.time() - self._last_api_call
        if elapsed < self._api_delay:
            time.sleep(self._api_delay - elapsed)
        
        try:
            result = func(*args, **kwargs)
            self._last_api_call = time.time()
            return result
        except Exception as e:
            logger.exception(f"API call failed: {e}")
            raise
    
    def _scan_worker(self):
        """Main worker thread - processes jobs sequentially."""
        logger.info("Worker thread started")
        
        while not self._stop_requested:
            # Get next job
            job = None
            with self._lock:
                if self.current_job_index < len(self.jobs):
                    job = self.jobs[self.current_job_index]
                    self.current_job_index += 1
                else:
                    # All jobs processed
                    break
            
            if job:
                self._process_job(job)
        
        # Scan complete
        with self._lock:
            self.is_scanning = False
        
        logger.info("Worker thread finished")
        self.all_jobs_complete.emit()
        
        # Emit final stats
        total, completed, errors = self.get_stats()
        self.scan_stats.emit(total, completed, errors)
    
    def _process_job(self, job):
        """Process a single scan job."""
        folder_path = job.folder_path
        folder = Path(folder_path)
        folder_name = folder.name
        
        logger.info(f"[JOB START] {folder_name}")
        job.status = 'scanning'
        job.start_time = time.time()
        self.job_started.emit(folder_path)
        self.job_progress.emit(folder_name, "Initializing", "Checking folder...")
        
        try:
            # Validate folder
            if not folder.exists():
                raise FileNotFoundError(f"Folder not found: {folder_path}")
            
            # Skip season folders
            if self._is_season_folder(folder_name):
                logger.info(f"[SKIP] Season folder: {folder_name}")
                job.status = 'complete'
                job.show_data = None
                self.job_completed.emit(folder_path, None)
                return
            
            # Skip container folders
            if self._is_container_folder(folder):
                logger.info(f"[SKIP] Container folder: {folder_name}")
                job.status = 'complete'
                job.show_data = None
                self.job_completed.emit(folder_path, None)
                return
            
            # Find video files
            self.job_progress.emit(folder_name, "Scanning", "Looking for video files...")
            video_files = self._find_video_files(folder)
            
            if not video_files:
                logger.info(f"[SKIP] No videos: {folder_name}")
                job.status = 'complete'
                job.show_data = None
                self.job_completed.emit(folder_path, None)
                return
            
            logger.info(f"[VIDEOS] {folder_name}: {len(video_files)} files")
            
            # Detect show
            self.job_progress.emit(folder_name, "Searching TVMaze", f"Looking up '{folder_name}'...")
            show_data, uncertain_matches = self._detect_show(folder_name)
            
            if show_data:
                # Good match found
                logger.info(f"[MATCH] {folder_name} -> {show_data['name']} ({show_data.get('confidence', 0):.1f}%)")
                
                # Store metadata
                self.job_progress.emit(folder_name, "Downloading", f"Show: {show_data['name']}")
                self._store_show_metadata(show_data, folder_name)
                
                # Associate videos
                self.job_progress.emit(folder_name, "Matching", f"Processing {len(video_files)} videos...")
                self._associate_videos(folder, show_data, video_files)
                
                # Complete
                job.status = 'complete'
                job.show_data = show_data
                job.end_time = time.time()
                elapsed = job.end_time - job.start_time
                logger.info(f"[JOB COMPLETE] {folder_name} in {elapsed:.2f}s")
                self.job_completed.emit(folder_path, show_data)
                
            elif uncertain_matches and not job.silent:
                # Uncertain match - needs user input
                logger.info(f"[UNCERTAIN] {folder_name}: {len(uncertain_matches)} possibilities")
                job.status = 'uncertain'
                job.end_time = time.time()
                self.job_uncertain.emit(folder_path, uncertain_matches)
                # Don't emit completed - wait for user
                
            else:
                # No match found
                logger.info(f"[NO MATCH] {folder_name}")
                job.status = 'complete'
                job.show_data = None
                job.end_time = time.time()
                self.job_completed.emit(folder_path, None)
                
        except Exception as e:
            logger.exception(f"[JOB ERROR] {folder_name}: {e}")
            job.status = 'error'
            job.error_message = str(e)
            job.end_time = time.time()
            self.job_error.emit(folder_path, str(e))
    
    def resolve_uncertain_match(self, folder_path, selected_show_data):
        """Resolve an uncertain match with user-selected show data."""
        # Find the job
        job = None
        for j in self.jobs:
            if j.folder_path == folder_path and j.status == 'uncertain':
                job = j
                break
        
        if not job:
            logger.error(f"No uncertain job found for {folder_path}")
            return False
        
        try:
            folder = Path(folder_path)
            video_files = self._find_video_files(folder)
            
            # Store metadata
            self._store_show_metadata(selected_show_data, folder.name)
            
            # Associate videos
            self._associate_videos(folder, selected_show_data, video_files)
            
            # Mark complete
            job.status = 'complete'
            job.show_data = selected_show_data
            job.end_time = time.time()
            
            logger.info(f"[RESOLVED] {folder.name} -> {selected_show_data['name']}")
            self.job_completed.emit(folder_path, selected_show_data)
            
            # Emit updated stats
            total, completed, errors = self.get_stats()
            self.scan_stats.emit(total, completed, errors)
            
            return True
            
        except Exception as e:
            logger.exception(f"[RESOLVE ERROR] {folder_path}: {e}")
            job.status = 'error'
            job.error_message = str(e)
            self.job_error.emit(folder_path, str(e))
            return False
    
    def skip_uncertain_match(self, folder_path):
        """Skip an uncertain match."""
        for j in self.jobs:
            if j.folder_path == folder_path and j.status == 'uncertain':
                j.status = 'complete'
                j.show_data = None
                j.end_time = time.time()
                logger.info(f"[SKIPPED] {Path(folder_path).name}")
                self.job_completed.emit(folder_path, None)
                
                # Emit updated stats
                total, completed, errors = self.get_stats()
                self.scan_stats.emit(total, completed, errors)
                return True
        return False
    
    def _is_season_folder(self, folder_name):
        """Check if folder is a season folder."""
        import re
        patterns = [
            r'^season\s*\d+',
            r'^s\d+$',
            r'^s\d+\s*-\s*\d+$',
        ]
        for pattern in patterns:
            if re.match(pattern, folder_name, re.IGNORECASE):
                return True
        return False
    
    def _is_container_folder(self, folder):
        """Check if folder is a container."""
        direct_videos = []
        for ext in ['.mp4', '.mkv', '.avi']:
            direct_videos.extend(folder.glob(f'*{ext}'))
        
        subfolders_with_videos = 0
        for subfolder in folder.iterdir():
            if subfolder.is_dir() and not subfolder.name.startswith('.'):
                has_videos = any(subfolder.rglob(f'*{ext}') for ext in ['.mp4', '.mkv', '.avi'])
                if has_videos:
                    subfolders_with_videos += 1
        
        return subfolders_with_videos > 0 and len(direct_videos) < 3
    
    def _find_video_files(self, folder):
        """Find all video files recursively."""
        video_files = []
        for ext in ['.mp4', '.mkv', '.avi']:
            video_files.extend(folder.rglob(f'*{ext}'))
        return [str(f) for f in video_files]
    
    def _detect_show(self, show_name):
        """Detect TV show with confidence scoring."""
        uncertain_matches = []
        
        try:
            results = self._rate_limited_api_call(TVMazeAPI.search_show, show_name)
            if results:
                best_match = None
                best_score = 0
                
                for result in results[:3]:
                    show = result['show']
                    
                    if show.get('type') not in ('Scripted', 'Animation', 'Reality', 'Talk Show', 'Documentary'):
                        continue
                    
                    tvmaze_name = show['name'].lower().strip()
                    folder_name = show_name.lower().strip()
                    
                    if tvmaze_name == folder_name:
                        score = 100
                    elif tvmaze_name in folder_name or folder_name in tvmaze_name:
                        score = 75
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
                    
                    if 40 <= score < 60:
                        uncertain_matches.append(show_data)
                
                if best_match and best_score >= 60:
                    return best_match, uncertain_matches
                elif best_match:
                    if best_match not in uncertain_matches:
                        uncertain_matches.insert(0, best_match)
                    return None, uncertain_matches
                    
        except Exception as e:
            logger.exception(f"Error detecting show {show_name}: {e}")
        
        return None, uncertain_matches
    
    def _store_show_metadata(self, show_data, folder_name=""):
        """Store metadata without blocking on image downloads."""
        try:
            # Store show
            self.db.add_show(show_data['tvmaze_id'], show_data['name'], show_data.get('image_url'))
            
            show_record = self.db.get_show(show_data['tvmaze_id'])
            if not show_record:
                return
            show_id = show_record[0]
            
            # Fetch seasons
            seasons = self._rate_limited_api_call(TVMazeAPI.get_show_seasons, show_data['tvmaze_id'])
            
            for season in seasons:
                if season and isinstance(season, dict) and 'number' in season:
                    season_image = (season.get('image') or {}).get('medium')
                    self.db.add_season(show_id, season['number'], season_image)
                    
                    season_record = self.db.get_season(show_id, season['number'])
                    if season_record:
                        season_id = season_record[0]
                        episodes = self._rate_limited_api_call(TVMazeAPI.get_season_episodes, season['id'])
                        
                        for ep in episodes:
                            if ep and isinstance(ep, dict) and 'number' in ep and 'name' in ep:
                                ep_image = (ep.get('image') or {}).get('medium')
                                self.db.add_episode(
                                    season_id,
                                    ep['number'],
                                    ep['name'],
                                    ep.get('airdate'),
                                    ep.get('summary'),
                                    ep_image
                                )
            
        except Exception as e:
            logger.exception(f"Error storing metadata: {e}")
            raise
    
    def _associate_videos(self, folder, show_data, video_files):
        """Associate videos with episodes."""
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
                except Exception as e:
                    logger.exception(f"Error associating video {video_path}: {e}")
                    
        except Exception as e:
            logger.exception(f"Error associating videos: {e}")
