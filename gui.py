import os
import signal
import subprocess
import sys
import threading
import time

import cv2
import pyautogui
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QImage, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from audio_to_cursor.calibration import CalibrationError, CalibrationManager
from pynosetracker import NoseTracker

# Global state flags for resource management
CALIBRATION_IN_PROGRESS = False
VOICE_CONTROL_RUNNING = False
VOICE_CONTROL_PID = None

# Path to typing mode flag file
TYPING_MODE_FILE = "typing_mode.flag"
# Path to mouse lock flag file
MOUSE_LOCK_FILE = "mouse_lock.flag"

# Helper function to check if typing mode is active
def is_typing_mode_active():
    """Check if typing mode is active by checking the flag file"""
    return os.path.exists(TYPING_MODE_FILE)

# Helper function to check if mouse is locked
def is_mouse_locked():
    """Check if mouse is locked by checking the flag file"""
    return os.path.exists(MOUSE_LOCK_FILE)

class CalibrationWorker(QThread):
    """Worker thread for audio calibration"""
    update_status = pyqtSignal(str)
    update_progress = pyqtSignal(int)
    calibration_complete = pyqtSignal(bool, str)
    
    def __init__(self, keep_test_files=False):
        super().__init__()
        self.keep_test_files = keep_test_files
        self.calibration_manager = CalibrationManager()
        
    def run(self):
        try:
            # Step 1: Capture background noise
            self.update_status.emit("Step 1: Capturing background noise. Please remain silent...")
            self.update_progress.emit(10)
            success = self.calibration_manager.capture_background_noise()
            if not success:
                self.calibration_complete.emit(False, "Failed to capture background noise")
                return
                
            # Step 2: Capture voice sample
            self.update_status.emit("Step 2: Capturing voice sample. Please speak naturally...")
            self.update_progress.emit(40)
            success = self.calibration_manager.capture_voice_sample()
            if not success:
                self.calibration_complete.emit(False, "Failed to capture voice sample")
                return
                
            # Step 3: Process and test
            self.update_status.emit("Step 3: Processing audio and testing noise reduction...")
            self.update_progress.emit(70)
            success = True or self.calibration_manager.process_and_test()
            if not success:
                self.calibration_complete.emit(False, "Failed to process audio")
                return
                
            # Step 4: Save calibration data
            self.update_status.emit("Step 4: Saving calibration data...")
            self.update_progress.emit(90)
            success = True or self.calibration_manager.save_calibration()
            if not success:
                self.calibration_complete.emit(False, "Failed to save calibration data")
                return
                
            # Clean up if needed
            if not self.keep_test_files:
                self.calibration_manager.cleanup_test_files()
                
            self.update_progress.emit(100)
            self.calibration_complete.emit(True, "Calibration completed successfully!")
            
        except CalibrationError as e:
            self.calibration_complete.emit(False, f"Calibration error: {str(e)}")
        except Exception as e:
            self.calibration_complete.emit(False, f"Unexpected error: {str(e)}")

class LogReader(threading.Thread):
    """Thread to read and monitor a log file"""
    def __init__(self, log_file, text_widget):
        threading.Thread.__init__(self, daemon=True)
        self.log_file = log_file
        self.text_widget = text_widget
        self.running = True
        self.last_position = 0
        
        # Define highlight patterns and colors
        self.highlight_patterns = [
            # Speech detection events - yellow
            {"pattern": "Listening for voice command", "color": "#F9A826"},
            {"pattern": "Audio captured", "color": "#F9A826"},
            
            # Recognition events - light blue
            {"pattern": "recognized:", "color": "#03A9F4"},
            {"pattern": "Collected", "color": "#03A9F4"},
            
            # Command interpretation - green
            {"pattern": "Final interpretation:", "color": "#4CAF50"},
            {"pattern": "Executing command:", "color": "#4CAF50"},
            
            # Typing mode - purple
            {"pattern": "Typing mode", "color": "#9C27B0"},
            {"pattern": "Typing:", "color": "#9C27B0"},
            
            # Mouse lock - orange
            {"pattern": "Mouse movement locked", "color": "#FF5722"},
            {"pattern": "Mouse movement unlocked", "color": "#2196F3"},
            
            # Errors and warnings - red
            {"pattern": "ERROR", "color": "#F44336"},
            {"pattern": "WARNING", "color": "#FF9800"},
            {"pattern": "Failed", "color": "#F44336"},
            {"pattern": "Error", "color": "#F44336"}
        ]
        
    def run(self):
        while self.running:
            if os.path.exists(self.log_file):
                try:
                    with open(self.log_file, 'r') as f:
                        # Go to the last read position
                        f.seek(self.last_position)
                        new_content = f.read()
                        if new_content:
                            # Apply highlighting
                            self.append_highlighted_text(new_content)
                            
                            # Auto-scroll to bottom
                            cursor = self.text_widget.textCursor()
                            cursor.movePosition(QTextCursor.MoveOperation.End)
                            self.text_widget.setTextCursor(cursor)
                        # Update last position
                        self.last_position = f.tell()
                except Exception as e:
                    print(f"Error reading log file: {e}")
            time.sleep(0.5)  # Check for updates every half second
    
    def append_highlighted_text(self, text):
        """Append text with highlighting for important events"""
        # Split text into lines for line-by-line processing
        lines = text.strip().split('\n')
        
        for line in lines:
            if not line.strip():
                continue
                
            # Check for any highlights
            highlighted = False
            for highlight in self.highlight_patterns:
                if highlight["pattern"].lower() in line.lower():
                    # Set the text color for this line
                    self.text_widget.setTextColor(QColor(highlight["color"]))
                    self.text_widget.append(line)
                    # Reset color to default black
                    self.text_widget.setTextColor(QColor("#000000"))
                    highlighted = True
                    break
            
            # If no highlight pattern matched, append with default color
            if not highlighted:
                self.text_widget.append(line)
    
    def stop(self):
        self.running = False


class NoseTrackerGUIv2(QMainWindow):
    def __init__(self, voice_log_file="multi_voice_logs.txt", console_log_file=None):
        super().__init__()
        
        # Initialize the state flag
        global CALIBRATION_IN_PROGRESS, VOICE_CONTROL_RUNNING, VOICE_CONTROL_PID
        CALIBRATION_IN_PROGRESS = False
        
        # Check if voice control is already running (by checking the console log file)
        if console_log_file and os.path.exists(console_log_file):
            VOICE_CONTROL_RUNNING = True
            # Try to get the PID from the parent process
            try:
                with open(console_log_file, 'r') as f:
                    for line in f:
                        if "VOICE_CONTROL_PID:" in line:
                            VOICE_CONTROL_PID = int(line.split("VOICE_CONTROL_PID:")[1].strip())
                            break
            except Exception as e:
                print(f"Error getting voice control PID: {e}")
        else:
            VOICE_CONTROL_RUNNING = False

        # Voxel color scheme
        self.colors = {
            "primary_bg": "#F5F5DC",  # Beige background color
            "secondary_bg": "#EFEFEF", # Light gray for contrast elements
            "text": "#000000",         # Black text
            "accent": "#333333",       # Dark gray for accents
            "success": "#4CAF50",      # Green for success indicators
            "error": "#f44336",        # Red for error indicators
            "warning": "#FF9800",      # Orange for warnings
            "info": "#2196F3",         # Blue for info messages
            "highlight": "#9C27B0"     # Purple for highlights
        }

        # Set window title with custom styling
        self.setWindowTitle("Voxel - Look Mom No Hands")
        
        # Make the window larger by default and position it centered
        screen_size = QApplication.primaryScreen().size()
        window_width = int(screen_size.width() * 0.85)
        window_height = int(screen_size.height() * 0.85)
        self.setGeometry(
            (screen_size.width() - window_width) // 2,
            (screen_size.height() - window_height) // 2,
            window_width, 
            window_height
        )
        
        # Full screen toggle key (F11)
        self.is_fullscreen = False
        
        self.log_file = voice_log_file
        self.console_log_file = console_log_file
        
        print(f"GUI initialized with:")
        print(f"- Voice log file: {self.log_file}")
        print(f"- Console log file: {self.console_log_file}")
        
        # Create monospace font for logs
        self.log_font = QFont("Courier New")  # Primary monospace font
        if not self.log_font.exactMatch():  # If Courier New is not available
            self.log_font = QFont("Monospace")  # Fallback option
        self.log_font.setPointSize(12)
        
        # Set window icon
        try:
            self.setWindowIcon(QIcon('assets/icon.png'))
        except:
            pass
        
        # Set application style
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ 
                background-color: {self.colors['primary_bg']}; 
                color: {self.colors['text']}; 
            }}
            QTabWidget::pane {{ 
                border: 1px solid {self.colors['accent']}; 
                background-color: {self.colors['primary_bg']}; 
            }}
            QTabBar::tab {{ 
                background-color: {self.colors['secondary_bg']}; 
                color: {self.colors['text']}; 
                padding: 8px 20px; 
                border: 1px solid {self.colors['accent']}; 
                border-bottom: none; 
                border-top-left-radius: 6px; 
                border-top-right-radius: 6px; 
            }}
            QTabBar::tab:selected {{ 
                background-color: {self.colors['primary_bg']}; 
                border-bottom: none; 
                font-weight: bold;
            }}
            QPushButton {{ 
                background-color: {self.colors['accent']}; 
                color: white; 
                border-radius: 5px;
                padding: 6px 12px;
                min-height: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{ 
                background-color: #555555; 
            }}
            QLabel {{ 
                color: {self.colors['text']}; 
            }}
            QSlider::groove:horizontal {{
                border: 1px solid {self.colors['accent']};
                height: 8px;
                background: {self.colors['secondary_bg']};
                margin: 2px 0;
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {self.colors['accent']};
                border: 1px solid {self.colors['accent']};
                width: 18px;
                height: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }}
            QTextEdit {{ 
                background-color: {self.colors['secondary_bg']}; 
                color: {self.colors['text']}; 
                border: 1px solid {self.colors['accent']}; 
                border-radius: 5px;
            }}
            QProgressBar {{
                border: 1px solid {self.colors['accent']};
                border-radius: 5px;
                text-align: center;
                background-color: {self.colors['secondary_bg']};
                color: {self.colors['text']};
            }}
            QProgressBar::chunk {{
                background-color: {self.colors['success']};
                width: 10px;
                border-radius: 4px;
            }}
            QCheckBox {{
                color: {self.colors['text']};
                spacing: 5px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
            }}
        """)
        
        # Initialize nose tracker in headless mode (we'll handle the display)
        self.tracker = NoseTracker(headless=True)
        self.tracking_active = False
        self.calibrating = False
        self.calibration_attempts = 0
        self.max_calibration_attempts = 10
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Add header with Voxel logo and tagline
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(5, 5, 5, 5)
        
        # Logo and title
        title_label = QLabel("VOXEL")
        title_label.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        header_layout.addWidget(title_label)
        
        # Tagline
        tagline_label = QLabel("LOOK MOM NO HANDS")
        tagline_label.setFont(QFont("Arial", 12))
        header_layout.addWidget(tagline_label)
        
        # Add spacer and fullscreen button
        header_layout.addStretch()
        
        # Fullscreen button
        self.fullscreen_button = QPushButton("Fullscreen")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.fullscreen_button.setToolTip("Toggle fullscreen mode (F11)")
        header_layout.addWidget(self.fullscreen_button)
        
        # Add header to main layout
        main_layout.addWidget(header_widget)
        
        # Create tabs for main content
        self.main_tabs = QTabWidget()
        main_layout.addWidget(self.main_tabs)
        
        # ---- Nose Tracker Tab ----
        nose_tracker_tab = QWidget()
        nose_tracker_layout = QVBoxLayout(nose_tracker_tab)
        nose_tracker_layout.setContentsMargins(10, 10, 10, 10)
        nose_tracker_layout.setSpacing(10)
        
        # Create splitter for resizing sections
        self.tracker_splitter = QSplitter(Qt.Orientation.Vertical)
        nose_tracker_layout.addWidget(self.tracker_splitter)
        
        # Top widget (camera and controls)
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(5, 5, 5, 5)
        top_layout.setSpacing(10)
        
        # Camera feed display with frame
        camera_frame = QWidget()
        camera_frame.setStyleSheet(f"background-color: {self.colors['secondary_bg']}; border-radius: 8px;")
        camera_layout = QVBoxLayout(camera_frame)
        camera_layout.setContentsMargins(2, 2, 2, 2)
        
        self.camera_label = QLabel()
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_label.setMinimumHeight(300)
        self.camera_label.setStyleSheet("background-color: #000000; border-radius: 6px;")
        camera_layout.addWidget(self.camera_label)
        
        top_layout.addWidget(camera_frame)
        
        # Status label
        self.status_label = QLabel("Status: Ready - Press C to calibrate")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
        top_layout.addWidget(self.status_label)
        
        # Controls layout in a nice frame
        controls_frame = QWidget()
        controls_frame.setStyleSheet(f"background-color: {self.colors['secondary_bg']}; border-radius: 8px;")
        controls_layout = QHBoxLayout(controls_frame)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(10)
        
        # Sensitivity slider
        sensitivity_layout = QVBoxLayout()
        sensitivity_layout.setSpacing(5)
        sensitivity_label = QLabel("Sensitivity")
        sensitivity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sensitivity_label.setStyleSheet("font-weight: bold;")
        
        self.sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.sensitivity_slider.setMinimum(1)
        self.sensitivity_slider.setMaximum(10)
        self.sensitivity_slider.setValue(8)
        self.sensitivity_slider.valueChanged.connect(self.update_sensitivity)
        
        sensitivity_layout.addWidget(sensitivity_label)
        sensitivity_layout.addWidget(self.sensitivity_slider)
        controls_layout.addLayout(sensitivity_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(5)
        
        self.calibrate_button = QPushButton("Calibrate (C)")
        self.calibrate_button.clicked.connect(self.start_calibration)
        self.calibrate_button.setStyleSheet(
            "color: black;"
        )
        button_layout.addWidget(self.calibrate_button)
        
        self.start_button = QPushButton("Start Tracking (T)")
        self.start_button.clicked.connect(self.toggle_tracking)
        self.start_button.setStyleSheet(
            "color: black;"
        )
        button_layout.addWidget(self.start_button)
        
        self.recenter_button = QPushButton("Recenter (R)")
        self.recenter_button.clicked.connect(self.recenter)
        self.recenter_button.setStyleSheet(
            "color: black;"
        )
        button_layout.addWidget(self.recenter_button)
        
        controls_layout.addLayout(button_layout)
        
        # Add voice control toggle button (if console log file is provided)
        if console_log_file:
            self.voice_control_button = QPushButton("Voice Control: ON" if VOICE_CONTROL_RUNNING else "Voice Control: OFF")
            self.voice_control_button.clicked.connect(self.toggle_voice_control)
            self.voice_control_button.setStyleSheet(
                f"QPushButton {{ background-color: {self.colors['success']}; color: white; border-radius: 5px; }}" if VOICE_CONTROL_RUNNING 
                else f"QPushButton {{ background-color: {self.colors['error']}; color: white; border-radius: 5px; }}"
            )
            controls_layout.addWidget(self.voice_control_button)
        
        top_layout.addWidget(controls_frame)
        
        # Add keyboard shortcuts help in a nice info box
        shortcuts_frame = QWidget()
        shortcuts_frame.setStyleSheet(f"background-color: {self.colors['secondary_bg']}; border-radius: 8px;")
        shortcuts_layout = QVBoxLayout(shortcuts_frame)
        shortcuts_layout.setContentsMargins(5, 5, 5, 5)
        
        shortcuts_label = QLabel("Keyboard Shortcuts: C - Calibrate | R - Recenter | T - Toggle Tracking | F11 - Fullscreen")
        shortcuts_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shortcuts_layout.addWidget(shortcuts_label)
        top_layout.addWidget(shortcuts_frame)
        
        # Add top widget to splitter
        self.tracker_splitter.addWidget(top_widget)
        
        # Bottom widget (logs)
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(5, 5, 5, 5)
        
        # Create log tab widget
        self.log_tabs = QTabWidget()

        # Console output logs
        self.console_logs = QTextEdit()
        self.console_logs.setReadOnly(True)
        self.console_logs.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.console_logs.setPlaceholderText("Voice control console output will appear here...")
        self.console_logs.setFont(self.log_font)
        self.log_tabs.addTab(self.console_logs, "Console Output")
        
        # Voice command logs
        self.voice_logs = QTextEdit()
        self.voice_logs.setReadOnly(True)
        self.voice_logs.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.voice_logs.setPlaceholderText("Voice command logs will appear here...")
        self.voice_logs.setFont(self.log_font)
        self.log_tabs.addTab(self.voice_logs, "Voice Commands")
        
        # System logs
        self.system_logs = QTextEdit()
        self.system_logs.setReadOnly(True)
        self.system_logs.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.system_logs.setPlaceholderText("System status will appear here...")
        self.system_logs.setFont(self.log_font)
        self.log_tabs.addTab(self.system_logs, "System Status")
        
        bottom_layout.addWidget(self.log_tabs)
        
        # Add bottom widget to splitter
        self.tracker_splitter.addWidget(bottom_widget)
        
        # Set initial sizes for splitter
        self.tracker_splitter.setSizes([int(window_height * 0.7), int(window_height * 0.3)])
        
        # Add tracker tab to main tabs
        self.main_tabs.addTab(nose_tracker_tab, "Nose Tracker")
        
        # ---- Audio Calibration Tab ----
        audio_calibration_tab = QWidget()
        audio_layout = QVBoxLayout(audio_calibration_tab)
        audio_layout.setContentsMargins(10, 10, 10, 10)
        audio_layout.setSpacing(15)
        
        # Store reference to the tab for switching
        self.audio_calibration_tab = audio_calibration_tab
        
        # Title and description in a nice frame
        calibration_header = QWidget()
        calibration_header.setStyleSheet(f"background-color: {self.colors['secondary_bg']}; border-radius: 8px;")
        calibration_header_layout = QVBoxLayout(calibration_header)
        calibration_header_layout.setContentsMargins(10, 10, 10, 10)
        
        audio_title = QLabel("Audio Calibration")
        audio_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        audio_title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        calibration_header_layout.addWidget(audio_title)
        
        description = QLabel(
            "This process will calibrate the audio noise filter for voice control.\n"
            "It will record background noise and test voice samples.\n"
            "Please ensure you are in a quiet environment before starting."
        )
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        description.setStyleSheet("padding: 5px; font-size: 12px;")
        calibration_header_layout.addWidget(description)
        
        audio_layout.addWidget(calibration_header)
        
        # Status display
        self.calibration_status = QLabel("Ready to calibrate")
        self.calibration_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.calibration_status.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
        audio_layout.addWidget(self.calibration_status)
        
        # Progress bar
        self.calibration_progress = QProgressBar()
        self.calibration_progress.setRange(0, 100)
        self.calibration_progress.setValue(0)
        self.calibration_progress.setMinimumHeight(25)
        audio_layout.addWidget(self.calibration_progress)
        
        # Controls in a frame
        calibration_controls = QWidget()
        calibration_controls.setStyleSheet(f"background-color: {self.colors['secondary_bg']}; border-radius: 8px;")
        calibration_controls_layout = QVBoxLayout(calibration_controls)
        calibration_controls_layout.setContentsMargins(10, 10, 10, 10)
        calibration_controls_layout.setSpacing(10)
        
        # Keep test files checkbox
        self.keep_files_checkbox = QCheckBox("Keep test files after calibration")
        calibration_controls_layout.addWidget(self.keep_files_checkbox)
        
        # Buttons
        calibration_buttons = QHBoxLayout()
        calibration_buttons.setSpacing(10)
        
        self.start_audio_calibration_btn = QPushButton("Start Audio Calibration")
        self.start_audio_calibration_btn.setMinimumHeight(30)
        self.start_audio_calibration_btn.clicked.connect(self.start_audio_calibration)
        self.start_audio_calibration_btn.setStyleSheet(
            "color: black;"
        )
        calibration_buttons.addWidget(self.start_audio_calibration_btn)
        
        self.cancel_audio_calibration_btn = QPushButton("Cancel")
        self.cancel_audio_calibration_btn.setMinimumHeight(30)
        self.cancel_audio_calibration_btn.clicked.connect(self.cancel_audio_calibration)
        self.cancel_audio_calibration_btn.setEnabled(False)
        self.cancel_audio_calibration_btn.setStyleSheet(
            "color: black;"
        )
        calibration_buttons.addWidget(self.cancel_audio_calibration_btn)
        
        calibration_controls_layout.addLayout(calibration_buttons)
        audio_layout.addWidget(calibration_controls)
        
        # Calibration log
        calibration_log_frame = QWidget()
        calibration_log_frame.setStyleSheet(f"background-color: {self.colors['secondary_bg']}; border-radius: 8px;")
        calibration_log_layout = QVBoxLayout(calibration_log_frame)
        calibration_log_layout.setContentsMargins(10, 10, 10, 10)
        
        calibration_log_label = QLabel("Calibration Log")
        calibration_log_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        calibration_log_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        calibration_log_layout.addWidget(calibration_log_label)
        
        self.calibration_log = QTextEdit()
        self.calibration_log.setReadOnly(True)
        self.calibration_log.setFont(self.log_font)
        self.calibration_log.setPlaceholderText("Calibration logs will appear here...")
        calibration_log_layout.addWidget(self.calibration_log)
        
        audio_layout.addWidget(calibration_log_frame)
        
        # Add audio calibration tab to main tabs
        self.main_tabs.addTab(audio_calibration_tab, "Audio Calibration")
        
        # Start log readers
        self.log_reader = LogReader(self.log_file, self.voice_logs)
        self.log_reader.start()
        
        # Start console log reader if a file was provided
        if self.console_log_file and os.path.exists(self.console_log_file):
            self.console_log_reader = LogReader(self.console_log_file, self.console_logs)
            self.console_log_reader.start()
            self.log_system_message(f"Monitoring console output from: {self.console_log_file}")
        
        # Timer for updating camera feed
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)  # Update every 30ms
        
        # Add system log entry
        self.log_system_message("GUI v2 started")
        self.log_system_message(f"Monitoring voice logs from: {self.log_file}")
        
        # Add typing mode animation
        self.typing_animation_active = False
        self.animation_direction = 1
        self.animation_offset = 0
        self.animation_speed = 2
        self.animation_max_offset = 5
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.update_typing_animation)
        self.animation_timer.start(50)  # Check every 50ms
        
        # Add status bar with indicators
        status_bar = QWidget()
        status_bar_layout = QHBoxLayout(status_bar)
        status_bar_layout.setContentsMargins(5, 5, 5, 5)
        status_bar_layout.setSpacing(10)
        
        # Add typing mode indicator label
        self.typing_indicator = QLabel("TYPING MODE: OFF")
        self.typing_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.typing_indicator.setStyleSheet(f"background-color: {self.colors['secondary_bg']}; color: {self.colors['text']}; font-weight: bold; border-radius: 5px; padding: 5px; font-size: 12px;")
        self.typing_indicator.setMinimumWidth(150)
        status_bar_layout.addWidget(self.typing_indicator)
        
        status_bar_layout.addStretch()
        
        # Add mouse lock indicator label
        self.lock_indicator = QLabel("MOUSE: UNLOCKED 🔓")
        self.lock_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lock_indicator.setStyleSheet(f"background-color: {self.colors['success']}; color: white; font-weight: bold; border-radius: 5px; padding: 5px; font-size: 12px;")
        self.lock_indicator.setMinimumWidth(150)
        status_bar_layout.addWidget(self.lock_indicator)
        
        # Add AI status indicator
        self.ai_indicator = QLabel("AI EDITOR: OFF")
        self.ai_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ai_indicator.setStyleSheet(f"background-color: {self.colors['secondary_bg']}; color: {self.colors['text']}; font-weight: bold; border-radius: 5px; padding: 5px; font-size: 12px;")
        self.ai_indicator.setMinimumWidth(150)
        status_bar_layout.addWidget(self.ai_indicator)
        
        main_layout.addWidget(status_bar)
        
    def log_system_message(self, message):
        """Add a message to the system log tab"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.system_logs.append(f"[{timestamp}] {message}")
        
    def log_calibration_message(self, message):
        """Add a message to the calibration log"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.calibration_log.append(f"[{timestamp}] {message}")
        # Auto-scroll to bottom
        cursor = self.calibration_log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.calibration_log.setTextCursor(cursor)
        
    def start_audio_calibration(self):
        """Start the audio calibration process in a background thread"""
        global CALIBRATION_IN_PROGRESS, VOICE_CONTROL_RUNNING
        
        # Check if voice control is running
        if VOICE_CONTROL_RUNNING:
            QMessageBox.warning(self, "Cannot Start Calibration", 
                "Voice control is currently running. Please exit and run the calibration script separately.")
            self.log_calibration_message("Calibration canceled: Voice control is currently running")
            return
        
        # Set the global flag
        CALIBRATION_IN_PROGRESS = True
        
        self.log_calibration_message("Starting audio calibration process...")
        self.calibration_status.setText("Calibration in progress...")
        self.calibration_progress.setValue(0)
        
        # Switch to the calibration tab to show progress
        self.main_tabs.setCurrentIndex(self.main_tabs.indexOf(self.audio_calibration_tab))
        
        # Toggle UI elements
        self.start_audio_calibration_btn.setEnabled(False)
        self.cancel_audio_calibration_btn.setEnabled(True)
        self.keep_files_checkbox.setEnabled(False)
        
        # Create and start worker thread
        self.calibration_worker = CalibrationWorker(self.keep_files_checkbox.isChecked())
        self.calibration_worker.update_status.connect(self.update_calibration_status)
        self.calibration_worker.update_progress.connect(self.update_calibration_progress)
        self.calibration_worker.calibration_complete.connect(self.on_calibration_complete)
        self.calibration_worker.start()
        
    def update_calibration_status(self, message):
        """Update the calibration status label and log"""
        self.calibration_status.setText(message)
        self.log_calibration_message(message)
        
    def update_calibration_progress(self, value):
        """Update the calibration progress bar"""
        self.calibration_progress.setValue(value)
        
    def on_calibration_complete(self, success, message):
        """Handle completion of the calibration process"""
        global CALIBRATION_IN_PROGRESS
        
        # Reset the global flag
        CALIBRATION_IN_PROGRESS = False
        
        # Reset UI elements
        self.start_audio_calibration_btn.setEnabled(True)
        self.cancel_audio_calibration_btn.setEnabled(False)
        self.keep_files_checkbox.setEnabled(True)
        
        # Update status and log
        if success:
            self.calibration_status.setText("Calibration completed successfully")
            self.log_calibration_message(f"SUCCESS: {message}")
            self.log_system_message("Audio calibration completed successfully")
            QMessageBox.information(self, "Calibration Success", 
                                  "Audio calibration completed successfully.")
        else:
            self.calibration_status.setText("Calibration failed")
            self.log_calibration_message(f"ERROR: {message}")
            self.log_system_message(f"Audio calibration failed: {message}")
            QMessageBox.warning(self, "Calibration Failed", 
                              f"Audio calibration failed: {message}")
        
    def cancel_audio_calibration(self):
        """Cancel ongoing calibration"""
        global CALIBRATION_IN_PROGRESS
        
        if hasattr(self, 'calibration_worker') and self.calibration_worker.isRunning():
            self.calibration_worker.terminate()
            self.calibration_worker.wait()
            
            # Reset the global flag
            CALIBRATION_IN_PROGRESS = False
            
            # Reset UI
            self.start_audio_calibration_btn.setEnabled(True)
            self.cancel_audio_calibration_btn.setEnabled(False)
            self.keep_files_checkbox.setEnabled(True)
            self.calibration_status.setText("Calibration cancelled")
            self.log_calibration_message("Calibration cancelled by user")
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_C:
            self.start_calibration()
        elif event.key() == Qt.Key.Key_T:
            self.toggle_tracking()
        elif event.key() == Qt.Key.Key_R:
            self.recenter()
        elif event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        elif event.key() >= Qt.Key.Key_1 and event.key() <= Qt.Key.Key_9:
            # Handle sensitivity changes (1-9)
            value = event.key() - Qt.Key.Key_0
            self.sensitivity_slider.setValue(value)
        elif event.key() == Qt.Key.Key_0:
            # Handle sensitivity 10
            self.sensitivity_slider.setValue(10)
    
    def update_sensitivity(self, value):
        self.tracker.sensitivity = self.tracker.base_sensitivity * value
        self.log_system_message(f"Sensitivity set to {value}")
        
    def start_calibration(self):
        self.calibrating = True
        self.calibration_attempts = 0
        self.status_label.setText("Status: Calibrating...")
        self.calibrate_button.setText("Calibrating...")
        self.calibrate_button.setEnabled(False)
        self.log_system_message("Starting calibration...")
        
    def perform_calibration(self, frame):
        success, annotated_frame = self.tracker.calibrate_for_gui(frame)
        
        if success:
            self.calibrating = False
            if self.tracking_active:
                self.status_label.setText("Status: Tracking")
            else:
                self.status_label.setText("Status: Calibrated")
            self.calibrate_button.setText("Calibrate (C)")
            self.calibrate_button.setEnabled(True)
            self.log_system_message("Calibration successful")
            return annotated_frame
        else:
            self.calibration_attempts += 1
            self.log_system_message(f"Calibration attempt {self.calibration_attempts} failed")
            if self.calibration_attempts >= self.max_calibration_attempts:
                self.calibrating = False
                self.status_label.setText("Status: Calibration Failed")
                self.calibrate_button.setText("Calibrate (C)")
                self.calibrate_button.setEnabled(True)
                self.log_system_message("Calibration failed after maximum attempts")
                QMessageBox.warning(self, "Calibration Failed", 
                                  "Could not detect face. Please ensure your face is visible and well-lit.")
            return annotated_frame
        
    def toggle_tracking(self):
        if not self.tracking_active:
            if not hasattr(self.tracker, 'face_center') or not hasattr(self.tracker, 'nose_center'):
                self.log_system_message("Cannot start tracking - please calibrate first")
                QMessageBox.warning(self, "Error", "Please calibrate first!")
                return
            self.tracking_active = True
            self.start_button.setText("Stop Tracking (T)")
            self.status_label.setText("Status: Tracking")
            self.log_system_message("Tracking started")
        else:
            self.stop_tracking()
            
    def stop_tracking(self):
        self.tracking_active = False
        self.start_button.setText("Start Tracking (T)")
        self.status_label.setText("Status: Ready")
        self.log_system_message("Tracking stopped")
            
    def recenter(self):
        screen_w, screen_h = self.tracker.screen_w, self.tracker.screen_h
        pyautogui.moveTo(screen_w // 2, screen_h // 2)
        self.tracker.prev_x, self.tracker.prev_y = screen_w // 2, screen_h // 2
        self.log_system_message("Cursor recentered")
        
    def update_frame(self):
        ret, frame = self.tracker.cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            
            if self.calibrating:
                frame = self.perform_calibration(frame)
            elif self.tracking_active:
                frame = self.tracker.run_for_gui(frame)
            
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image)
            self.camera_label.setPixmap(pixmap.scaled(
                self.camera_label.size(), 
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
            
    def toggle_voice_control(self):
        """Toggle voice control on/off"""
        global VOICE_CONTROL_RUNNING, VOICE_CONTROL_PID
        
        # Check if calibration is in progress
        if CALIBRATION_IN_PROGRESS:
            QMessageBox.warning(self, "Cannot Toggle Voice Control", 
                              "Audio calibration is in progress. Please wait until it completes.")
            return
        
        if VOICE_CONTROL_RUNNING:
            # Stop voice control
            try:
                if VOICE_CONTROL_PID:
                    os.kill(VOICE_CONTROL_PID, signal.SIGTERM)
                    self.log_system_message(f"Stopped voice control process (PID: {VOICE_CONTROL_PID})")
                    VOICE_CONTROL_PID = None
                VOICE_CONTROL_RUNNING = False
                self.voice_control_button.setText("Voice Control: OFF")
                self.voice_control_button.setStyleSheet("QPushButton { background-color: #f44336; color: white; }")
                self.log_system_message("Voice control stopped")
            except Exception as e:
                self.log_system_message(f"Error stopping voice control: {e}")
                QMessageBox.warning(self, "Error", f"Failed to stop voice control: {e}")
        else:
            # Start voice control
            try:
                # Create console log file if it doesn't exist
                if not self.console_log_file:
                    self.console_log_file = "voice_control_console.log"
                
                with open(self.console_log_file, 'a') as f:
                    f.write(f"\nRestarting voice control at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                
                # Start the process
                process = subprocess.Popen(
                    ["python3", "voice_control.py"], 
                    stdout=open(self.console_log_file, 'a'),
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )
                VOICE_CONTROL_PID = process.pid
                
                # Write PID to log file for future reference
                with open(self.console_log_file, 'a') as f:
                    f.write(f"VOICE_CONTROL_PID: {VOICE_CONTROL_PID}\n")
                
                # Start console log reader if not already started
                if not hasattr(self, 'console_log_reader') or not self.console_log_reader.is_alive():
                    self.console_log_reader = LogReader(self.console_log_file, self.console_logs)
                    self.console_log_reader.start()
                
                VOICE_CONTROL_RUNNING = True
                self.voice_control_button.setText("Voice Control: ON")
                self.voice_control_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; }")
                self.log_system_message(f"Voice control started (PID: {VOICE_CONTROL_PID})")
            except Exception as e:
                self.log_system_message(f"Error starting voice control: {e}")
                QMessageBox.warning(self, "Error", f"Failed to start voice control: {e}")
    
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        try:
            # Temporarily pause timers to prevent resource conflicts
            self.timer.stop()
            self.animation_timer.stop()
            
            if self.is_fullscreen:
                # Exit fullscreen mode
                self.showNormal()
                self.fullscreen_button.setText("Fullscreen")
                self.is_fullscreen = False
            else:
                # Enter fullscreen mode
                self.showFullScreen()
                self.fullscreen_button.setText("Exit Fullscreen")
                self.is_fullscreen = True
            
            # Process pending events to ensure UI updates properly
            QApplication.processEvents()
            
            # Resume timers
            self.timer.start(30)
            self.animation_timer.start(50)
            
            self.log_system_message(f"Toggled fullscreen mode: {self.is_fullscreen}")
        except Exception as e:
            # If an error occurs, restore normal window state
            self.showNormal()
            self.is_fullscreen = False
            self.timer.start(30)
            self.animation_timer.start(50)
            self.log_system_message(f"Error during fullscreen toggle: {e}")
            print(f"Fullscreen error: {e}")
        
    def update_typing_animation(self):
        """Check typing mode and update window animation"""
        try:
            # Use the helper function to check typing mode state
            typing_active = is_typing_mode_active()
            
            # Check if typing mode state changed
            if typing_active and not self.typing_animation_active:
                # Typing mode activated
                self.typing_animation_active = True
                self.typing_indicator.setText("TYPING MODE: ON")
                self.typing_indicator.setStyleSheet(f"background-color: {self.colors['highlight']}; color: white; font-weight: bold; border-radius: 5px; padding: 8px; font-size: 14px;")
                self.log_system_message("Typing mode activated - window will animate")
            elif not typing_active and self.typing_animation_active:
                # Typing mode deactivated
                self.typing_animation_active = False
                self.typing_indicator.setText("TYPING MODE: OFF")
                self.typing_indicator.setStyleSheet(f"background-color: {self.colors['secondary_bg']}; color: {self.colors['text']}; font-weight: bold; border-radius: 5px; padding: 8px; font-size: 14px;")
                self.log_system_message("Typing mode deactivated - animation stopped")
                # Reset window position
                self.move(self.x(), self.y() - self.animation_offset)
                self.animation_offset = 0
            
            # Check mouse lock state and update indicator
            mouse_locked = is_mouse_locked()
            if mouse_locked:
                self.lock_indicator.setText("MOUSE: LOCKED 🔒")
                self.lock_indicator.setStyleSheet(f"background-color: {self.colors['error']}; color: white; font-weight: bold; border-radius: 5px; padding: 8px; font-size: 14px;")
            else:
                self.lock_indicator.setText("MOUSE: UNLOCKED 🔓")
                self.lock_indicator.setStyleSheet(f"background-color: {self.colors['success']}; color: white; font-weight: bold; border-radius: 5px; padding: 8px; font-size: 14px;")
            
            # Check AI editor state
            ai_editor_active = os.path.exists("ai_editor.flag")
            if ai_editor_active:
                self.ai_indicator.setText("AI EDITOR: ON 🤖")
                self.ai_indicator.setStyleSheet(f"background-color: {self.colors['info']}; color: white; font-weight: bold; border-radius: 5px; padding: 8px; font-size: 14px;")
            else:
                self.ai_indicator.setText("AI EDITOR: OFF")
                self.ai_indicator.setStyleSheet(f"background-color: {self.colors['secondary_bg']}; color: {self.colors['text']}; font-weight: bold; border-radius: 5px; padding: 8px; font-size: 14px;")
            
            # If animation is active, update window position
            if self.typing_animation_active:
                # Update offset based on direction
                self.animation_offset += self.animation_direction * self.animation_speed
                
                # Change direction if we hit the limits
                if abs(self.animation_offset) >= self.animation_max_offset:
                    self.animation_direction *= -1
                
                # Move the window up or down
                self.move(self.x(), self.y() + (self.animation_direction * self.animation_speed))
        except Exception as e:
            # Don't log errors from animation - it could flood the logs
            pass
    
    def closeEvent(self, event):
        """Handle window close event"""
        global CALIBRATION_IN_PROGRESS, VOICE_CONTROL_PID
        
        # Check if calibration is in progress
        if CALIBRATION_IN_PROGRESS:
            reply = QMessageBox.question(self, 'Exit Confirmation',
                                        "Audio calibration is in progress. Are you sure you want to quit?",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                        QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
        
        # Stop the voice control process if we started it
        if VOICE_CONTROL_PID:
            try:
                os.kill(VOICE_CONTROL_PID, signal.SIGTERM)
                self.log_system_message(f"Stopped voice control process (PID: {VOICE_CONTROL_PID})")
            except Exception as e:
                self.log_system_message(f"Error stopping voice control: {e}")
                
        self.timer.stop()
        if hasattr(self, 'log_reader'):
            self.log_reader.stop()
        if hasattr(self, 'console_log_reader'):
            self.console_log_reader.stop()
        self.tracker.__del__()
        
        # Stop animation timer
        self.animation_timer.stop()
        
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Voxel v2")
    app.setApplicationDisplayName("Voxel v2")
    
    # Get log file paths from command line arguments
    voice_log_file = sys.argv[1] if len(sys.argv) > 1 else "multi_voice_logs.txt"
    console_log_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"Starting GUI with voice log: {voice_log_file}, console log: {console_log_file}")
    
    # Set application icon
    try:
        icon = QIcon('assets/icon.png')
        app.setWindowIcon(icon)
    except:
        pass
    
    window = NoseTrackerGUIv2(voice_log_file=voice_log_file, console_log_file=console_log_file)
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()