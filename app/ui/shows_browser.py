"""
TV-Style Shows Browser
A Netflix/Kodi-style interface for browsing TV shows.
Supports both mouse and remote control navigation.
"""

from qtpy.QtWidgets import *
from qtpy.QtCore import *
from qtpy.QtGui import *
from pathlib import Path
import logging

logger = logging.getLogger("SHOWS_BROWSER")


class TVStyleShowsWidget(QWidget):
    """
    TV-style shows browser with grid layout.
    Supports both mouse and keyboard navigation.
    """
    
    play_video = Signal(str)  # Emitted when user selects an episode to play
    
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_view = 'shows'  # shows, seasons, episodes
        self.current_show = None
        self.current_season = None
        self.items = []  # List of current items for keyboard navigation
        self.selected_index = 0
        
        self._setup_ui()
        self._setup_styles()
        
    def _setup_ui(self):
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Header with breadcrumb
        self.header = QWidget()
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Back button
        self.back_btn = QPushButton("← Back")
        self.back_btn.setVisible(False)
        self.back_btn.clicked.connect(self._on_back)
        header_layout.addWidget(self.back_btn)
        
        # Breadcrumb label
        self.breadcrumb = QLabel("TV Shows")
        self.breadcrumb.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 24px;
                font-weight: bold;
                padding-left: 20px;
            }
        """)
        header_layout.addWidget(self.breadcrumb)
        header_layout.addStretch()
        
        layout.addWidget(self.header)
        
        # Scroll area for grid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: #1a1a1a;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #444;
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #666;
            }
        """)
        
        # Grid container
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(20)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        self.scroll.setWidget(self.grid_container)
        layout.addWidget(self.scroll)
        
        # Info panel at bottom
        self.info_panel = QWidget()
        info_layout = QVBoxLayout(self.info_panel)
        info_layout.setContentsMargins(10, 10, 10, 10)
        
        self.info_title = QLabel()
        self.info_title.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 20px;
                font-weight: bold;
            }
        """)
        info_layout.addWidget(self.info_title)
        
        self.info_description = QLabel()
        self.info_description.setWordWrap(True)
        self.info_description.setStyleSheet("""
            QLabel {
                color: #aaa;
                font-size: 14px;
            }
        """)
        info_layout.addWidget(self.info_description)
        
        self.info_panel.setStyleSheet("""
            QWidget {
                background: #1a1a1a;
                border-radius: 10px;
            }
        """)
        self.info_panel.setVisible(False)
        
        layout.addWidget(self.info_panel)
        
        # Set focus policy for keyboard navigation
        self.setFocusPolicy(Qt.StrongFocus)
        
    def _setup_styles(self):
        """Setup widget styles."""
        self.setStyleSheet("""
            TVStyleShowsWidget {
                background: #0a0a0a;
            }
            QPushButton {
                background: #333;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #555;
            }
            QPushButton:pressed {
                background: #777;
            }
        """)
        
    def refresh(self):
        """Refresh the current view."""
        if self.current_view == 'shows':
            self._show_shows_grid()
        elif self.current_view == 'seasons':
            self._show_seasons_grid()
        elif self.current_view == 'episodes':
            self._show_episodes_grid()
            
    def _clear_grid(self):
        """Clear the grid layout."""
        self.items = []
        self.selected_index = 0
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
    def _show_shows_grid(self):
        """Display grid of all TV shows."""
        self._clear_grid()
        self.current_view = 'shows'
        self.current_show = None
        self.current_season = None
        
        self.breadcrumb.setText("TV Shows")
        self.back_btn.setVisible(False)
        self.info_panel.setVisible(False)
        
        # Get all shows from database
        shows = self.db.get_all_shows()
        
        if not shows:
            # Show empty state
            empty_label = QLabel("No TV shows found.\n\nAdd a folder with TV shows to get started.")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("""
                QLabel {
                    color: #666;
                    font-size: 18px;
                    padding: 50px;
                }
            """)
            self.grid_layout.addWidget(empty_label, 0, 0)
            return
        
        # Calculate columns based on width
        columns = self._calculate_columns()
        
        # Add show cards
        for i, show in enumerate(shows):
            card = self._create_show_card(show)
            row = i // columns
            col = i % columns
            self.grid_layout.addWidget(card, row, col)
            self.items.append(card)
            
        # Highlight first item
        if self.items:
            self._highlight_item(0)
            
    def _create_show_card(self, show_data):
        """Create a show card widget."""
        card = QFrame()
        card.setFixedSize(200, 300)
        card.setCursor(Qt.PointingHandCursor)
        card.setProperty('show_data', show_data)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Poster image
        poster = QLabel()
        poster.setFixedSize(180, 270)
        poster.setAlignment(Qt.AlignCenter)
        poster.setStyleSheet("""
            QLabel {
                background: #1a1a1a;
                border-radius: 8px;
            }
        """)
        
        # Load image if available
        if show_data[4]:  # cached_image_path
            pixmap = QPixmap(show_data[4])
            if not pixmap.isNull():
                scaled = pixmap.scaled(180, 270, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                poster.setPixmap(scaled)
        else:
            # Show placeholder with show name
            poster.setText(show_data[2])  # show name
            poster.setWordWrap(True)
            poster.setStyleSheet("""
                QLabel {
                    background: #1a1a1a;
                    border-radius: 8px;
                    color: white;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 10px;
                }
            """)
        
        layout.addWidget(poster)
        
        # Show title
        title = QLabel(show_data[2])  # show name
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        layout.addWidget(title)
        
        # Style
        card.setStyleSheet("""
            QFrame {
                background: transparent;
                border: 3px solid transparent;
                border-radius: 10px;
            }
            QFrame:hover {
                border: 3px solid #4CAF50;
            }
            QFrame[selected="true"] {
                border: 3px solid #4CAF50;
                background: #1a1a1a;
            }
        """)
        
        # Click handler
        card.mousePressEvent = lambda e, s=show_data: self._on_show_clicked(s)
        
        # Context menu for right-click
        def context_menu_event(event):
            menu = QMenu(self)
            menu.setStyleSheet("""
                QMenu {
                    background: #2a2a2a;
                    color: white;
                    border: 1px solid #444;
                    padding: 5px;
                }
                QMenu::item {
                    padding: 8px 20px;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background: #4CAF50;
                }
            """)
            
            play_action = menu.addAction("▶  Play All Episodes")
            info_action = menu.addAction("ℹ  Show Details")
            menu.addSeparator()
            remove_action = menu.addAction("🗑️  Remove Show")
            
            action = menu.exec_(card.mapToGlobal(event.pos()))
            if action == play_action:
                self._play_all_show_episodes(show_data)
            elif action == info_action:
                self._show_show_details(show_data)
            elif action == remove_action:
                self._remove_show(show_data)
        
        card.contextMenuEvent = context_menu_event
        
        return card
        
    def _show_seasons_grid(self):
        """Display grid of seasons for current show."""
        if not self.current_show:
            return
            
        self._clear_grid()
        self.current_view = 'seasons'
        
        show_name = self.current_show[2]
        self.breadcrumb.setText(f"TV Shows / {show_name}")
        self.back_btn.setVisible(True)
        
        # Get seasons
        show_id = self.current_show[0]
        seasons = self.db.get_seasons_for_show(show_id)
        
        if not seasons:
            empty_label = QLabel("No seasons found for this show.")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("color: #666; font-size: 18px; padding: 50px;")
            self.grid_layout.addWidget(empty_label, 0, 0)
            return
        
        # Calculate columns
        columns = self._calculate_columns()
        
        # Add season cards
        for i, season in enumerate(seasons):
            card = self._create_season_card(season)
            row = i // columns
            col = i % columns
            self.grid_layout.addWidget(card, row, col)
            self.items.append(card)
            
        if self.items:
            self._highlight_item(0)
            
    def _create_season_card(self, season_data):
        """Create a season card widget."""
        card = QFrame()
        card.setFixedSize(200, 280)
        card.setCursor(Qt.PointingHandCursor)
        card.setProperty('season_data', season_data)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Season number display
        season_num = season_data[2]  # season_number
        
        poster = QLabel()
        poster.setFixedSize(180, 250)
        poster.setAlignment(Qt.AlignCenter)
        poster.setText(f"Season\n{season_num}")
        poster.setStyleSheet("""
            QLabel {
                background: #1a1a1a;
                border-radius: 8px;
                color: white;
                font-size: 24px;
                font-weight: bold;
            }
        """)
        
        # Try to load season image
        if season_data[3]:  # image_url or cached path
            pixmap = QPixmap(season_data[3])
            if not pixmap.isNull():
                scaled = pixmap.scaled(180, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                poster.setPixmap(scaled)
                poster.setText("")
        
        layout.addWidget(poster)
        
        # Season label
        label = QLabel(f"Season {season_num}")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        layout.addWidget(label)
        
        card.setStyleSheet("""
            QFrame {
                background: transparent;
                border: 3px solid transparent;
                border-radius: 10px;
            }
            QFrame:hover {
                border: 3px solid #4CAF50;
            }
            QFrame[selected="true"] {
                border: 3px solid #4CAF50;
                background: #1a1a1a;
            }
        """)
        
        card.mousePressEvent = lambda e, s=season_data: self._on_season_clicked(s)
        
        # Context menu for right-click
        def season_context_menu(event):
            menu = QMenu(self)
            menu.setStyleSheet("""
                QMenu {
                    background: #2a2a2a;
                    color: white;
                    border: 1px solid #444;
                    padding: 5px;
                }
                QMenu::item {
                    padding: 8px 20px;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background: #4CAF50;
                }
            """)
            
            play_action = menu.addAction("▶  Play All Episodes in Season")
            
            action = menu.exec_(card.mapToGlobal(event.pos()))
            if action == play_action:
                self._play_all_season_episodes(season_data)
        
        card.contextMenuEvent = season_context_menu
        
        return card
        
    def _play_all_show_episodes(self, show_data):
        """Play all episodes from a show."""
        show_id = show_data[0]
        video_paths = []
        
        # Get all seasons
        seasons = self.db.get_seasons_for_show(show_id)
        for season in seasons:
            season_id = season[0]
            episodes = self.db.get_episodes_for_season(season_id)
            for episode in episodes:
                episode_id = episode[0]
                video_path = self.db.get_video_for_episode(episode_id)
                if video_path:
                    video_paths.append(video_path)
        
        if video_paths:
            # Play first episode, add rest to playlist
            self.play_video.emit(video_paths[0])
            # Note: We'd need to add remaining episodes to the main playlist
            # For now, just emit the first one
            logger.info(f"Playing show {show_data[2]} with {len(video_paths)} episodes")
        else:
            QMessageBox.information(self, "No Videos Found", 
                f"No video files found for {show_data[2]}.\n\n"
                "Make sure the video files are in the correct folders.")
    
    def _play_all_season_episodes(self, season_data):
        """Play all episodes from a season."""
        season_id = season_data[0]
        video_paths = []
        
        episodes = self.db.get_episodes_for_season(season_id)
        for episode in episodes:
            episode_id = episode[0]
            video_path = self.db.get_video_for_episode(episode_id)
            if video_path:
                video_paths.append(video_path)
        
        if video_paths:
            self.play_video.emit(video_paths[0])
            logger.info(f"Playing season with {len(video_paths)} episodes")
        else:
            QMessageBox.information(self, "No Videos Found", 
                "No video files found for this season.\n\n"
                "Make sure the video files are in the correct folder.")
    
    def _show_show_details(self, show_data):
        """Show details about how a show was designated."""
        show_id = show_data[0]
        show_name = show_data[2]
        tvmaze_id = show_data[1]
        
        # Get associated videos
        videos = []
        seasons = self.db.get_seasons_for_show(show_id)
        for season in seasons:
            season_id = season[0]
            episodes = self.db.get_episodes_for_season(season_id)
            for episode in episodes:
                episode_id = episode[0]
                video_path = self.db.get_video_for_episode(episode_id)
                if video_path:
                    videos.append(video_path)
        
        # Build info message
        info_text = f"<b>Show:</b> {show_name}<br><br>"
        info_text += f"<b>TVMaze ID:</b> {tvmaze_id}<br><br>"
        info_text += f"<b>Seasons:</b> {len(seasons)}<br><br>"
        info_text += f"<b>Episodes with Videos:</b> {len(videos)}<br><br>"
        
        if videos:
            info_text += "<b>Sample Video Files:</b><br>"
            for video in videos[:5]:
                info_text += f"• {Path(video).name}<br>"
            if len(videos) > 5:
                info_text += f"<i>... and {len(videos) - 5} more</i><br>"
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Show Details")
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(info_text)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()
    
    def _remove_show(self, show_data):
        """Remove a show from the watch tab."""
        show_id = show_data[0]
        show_name = show_data[2]
        
        reply = QMessageBox.question(self, "Remove Show", 
            f"Are you sure you want to remove '{show_name}' from the Watch tab?\n\n"
            "This will remove the show and all its metadata, but your video files will not be affected.",
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            if self.db.remove_show(show_id):
                QMessageBox.information(self, "Success", f"'{show_name}' has been removed.")
                # Refresh the shows grid
                if self.current_view == 'shows':
                    self._show_shows_grid()
                else:
                    # Go back to shows view
                    self._show_shows_grid()
            else:
                QMessageBox.warning(self, "Error", f"Failed to remove '{show_name}'.")
        
    def _show_episodes_grid(self):
        """Display list/grid of episodes for current season."""
        if not self.current_show or not self.current_season:
            return
            
        self._clear_grid()
        self.current_view = 'episodes'
        
        show_name = self.current_show[2]
        season_num = self.current_season[2]
        self.breadcrumb.setText(f"TV Shows / {show_name} / Season {season_num}")
        self.back_btn.setVisible(True)
        
        # Get episodes
        season_id = self.current_season[0]
        episodes = self.db.get_episodes_for_season(season_id)
        
        if not episodes:
            empty_label = QLabel("No episodes found for this season.")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("color: #666; font-size: 18px; padding: 50px;")
            self.grid_layout.addWidget(empty_label, 0, 0)
            return
        
        # For episodes, use a list layout instead of grid
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setSpacing(5)
        list_layout.setContentsMargins(0, 0, 0, 0)
        
        for episode in episodes:
            item = self._create_episode_item(episode)
            list_layout.addWidget(item)
            self.items.append(item)
        
        list_layout.addStretch()
        self.grid_layout.addWidget(list_widget, 0, 0)
        
        if self.items:
            self._highlight_item(0)
            
    def _create_episode_item(self, episode_data):
        """Create an episode list item."""
        item = QFrame()
        item.setFixedHeight(80)
        item.setCursor(Qt.PointingHandCursor)
        item.setProperty('episode_data', episode_data)
        
        layout = QHBoxLayout(item)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(15)
        
        # Episode number
        ep_num = episode_data[2]  # episode_number
        ep_num_str = f"E{int(ep_num):02d}" if ep_num is not None else "E??"
        num_label = QLabel(ep_num_str)
        num_label.setFixedWidth(50)
        num_label.setStyleSheet("""
            QLabel {
                color: #4CAF50;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        layout.addWidget(num_label)
        
        # Episode info
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(5)
        
        # Title
        title = episode_data[3]  # name
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        info_layout.addWidget(title_label)
        
        # Airdate
        airdate = episode_data[4]  # airdate
        if airdate:
            date_label = QLabel(f"Aired: {airdate}")
            date_label.setStyleSheet("color: #888; font-size: 12px;")
            info_layout.addWidget(date_label)
        
        layout.addWidget(info_widget)
        layout.addStretch()
        
        # Play button
        play_btn = QLabel("▶")
        play_btn.setStyleSheet("""
            QLabel {
                color: #4CAF50;
                font-size: 24px;
                padding: 5px;
            }
        """)
        layout.addWidget(play_btn)
        
        item.setStyleSheet("""
            QFrame {
                background: #1a1a1a;
                border-radius: 8px;
                border: 2px solid transparent;
            }
            QFrame:hover {
                background: #2a2a2a;
                border: 2px solid #4CAF50;
            }
            QFrame[selected="true"] {
                background: #2a2a2a;
                border: 2px solid #4CAF50;
            }
        """)
        
        item.mousePressEvent = lambda e, ep=episode_data: self._on_episode_clicked(ep)
        
        return item
        
    def _calculate_columns(self):
        """Calculate number of columns based on width."""
        width = self.scroll.viewport().width()
        card_width = 220  # 200 + spacing
        return max(1, width // card_width)
        
    def _highlight_item(self, index):
        """Highlight item at given index."""
        # Remove highlight from all items
        for item in self.items:
            item.setProperty('selected', False)
            item.style().unpolish(item)
            item.style().polish(item)
        
        # Add highlight to selected item
        if 0 <= index < len(self.items):
            self.selected_index = index
            item = self.items[index]
            item.setProperty('selected', True)
            item.style().unpolish(item)
            item.style().polish(item)
            
            # Scroll into view
            self.scroll.ensureWidgetVisible(item)
            
            # Update info panel
            self._update_info_panel(item)
            
    def _update_info_panel(self, item):
        """Update info panel with selected item details."""
        if self.current_view == 'shows':
            show_data = item.property('show_data')
            if show_data:
                self.info_title.setText(show_data[2])  # name
                # Could add description here if available
                self.info_panel.setVisible(True)
        elif self.current_view == 'seasons':
            self.info_panel.setVisible(False)
        elif self.current_view == 'episodes':
            episode_data = item.property('episode_data')
            if episode_data:
                self.info_title.setText(f"Episode {episode_data[2]}: {episode_data[3]}")
                summary = episode_data[5] or "No description available."
                self.info_description.setText(summary)
                self.info_panel.setVisible(True)
                
    def _on_show_clicked(self, show_data):
        """Handle show selection."""
        self.current_show = show_data
        self._show_seasons_grid()
        
    def _on_season_clicked(self, season_data):
        """Handle season selection."""
        self.current_season = season_data
        self._show_episodes_grid()
        
    def _on_episode_clicked(self, episode_data):
        """Handle episode selection - play the video."""
        # Get video path for this episode
        video_path = self.db.get_video_for_episode(episode_data[0])
        if video_path:
            self.play_video.emit(video_path)
        else:
            # Show message that video file not found
            QMessageBox.information(self, "Video Not Found", 
                f"Episode found in database, but video file not found.\n\n"
                f"Make sure the episode file is in the correct folder.")
        
    def _on_back(self):
        """Handle back navigation."""
        if self.current_view == 'episodes':
            self._show_seasons_grid()
        elif self.current_view == 'seasons':
            self._show_shows_grid()
            
    # Keyboard navigation
    def keyPressEvent(self, event):
        """Handle keyboard navigation."""
        if not self.items:
            return
            
        key = event.key()
        columns = self._calculate_columns()
        
        if key == Qt.Key_Right:
            self._highlight_item(min(self.selected_index + 1, len(self.items) - 1))
        elif key == Qt.Key_Left:
            self._highlight_item(max(self.selected_index - 1, 0))
        elif key == Qt.Key_Down:
            if self.current_view == 'episodes':
                # List view - just go down one
                self._highlight_item(min(self.selected_index + 1, len(self.items) - 1))
            else:
                # Grid view
                self._highlight_item(min(self.selected_index + columns, len(self.items) - 1))
        elif key == Qt.Key_Up:
            if self.current_view == 'episodes':
                # List view
                self._highlight_item(max(self.selected_index - 1, 0))
            else:
                # Grid view
                self._highlight_item(max(self.selected_index - columns, 0))
        elif key == Qt.Key_Return or key == Qt.Key_Enter:
            self._activate_current_item()
        elif key == Qt.Key_Backspace or key == Qt.Key_Escape:
            self._on_back()
        else:
            super().keyPressEvent(event)
            
    def _activate_current_item(self):
        """Activate the currently selected item."""
        if not self.items or not (0 <= self.selected_index < len(self.items)):
            return
            
        item = self.items[self.selected_index]
        
        if self.current_view == 'shows':
            show_data = item.property('show_data')
            if show_data:
                self._on_show_clicked(show_data)
        elif self.current_view == 'seasons':
            season_data = item.property('season_data')
            if season_data:
                self._on_season_clicked(season_data)
        elif self.current_view == 'episodes':
            episode_data = item.property('episode_data')
            if episode_data:
                self._on_episode_clicked(episode_data)
                
    def resizeEvent(self, event):
        """Handle resize to recalculate grid."""
        super().resizeEvent(event)
        if self.current_view != 'episodes':
            # Refresh grid layout
            self.refresh()
