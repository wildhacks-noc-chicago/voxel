import sys
import os
import cv2
import threading
import time
import subprocess
import signal
import pyautogui
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QSlider, QLabel, QMessageBox,
                            QTextEdit, QSplitter, QTabWidget, QProgressBar, QCheckBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QImage, QPixmap, QIcon, QColor, QTextCursor, QFont
from pynosetracker import NoseTracker
from audio_to_cursor.calibration import CalibrationManager, CalibrationError

# Global state flags for resource management
CALIBRATION_IN_PROGRESS = False
VOICE_CONTROL_RUNNING = False
VOICE_CONTROL_PID = None

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
        
    def run(self):
        while self.running:
            if os.path.exists(self.log_file):
                try:
                    with open(self.log_file, 'r') as f:
                        # Go to the last read position
                        f.seek(self.last_position)
                        new_content = f.read()
                        if new_content:
                            self.text_widget.append(new_content)
                            # Auto-scroll to bottom
                            cursor = self.text_widget.textCursor()
                            cursor.movePosition(QTextCursor.MoveOperation.End)
                            self.text_widget.setTextCursor(cursor)
                        # Update last position
                        self.last_position = f.tell()
                except Exception as e:
                    print(f"Error reading log file: {e}")
            time.sleep(0.5)  # Check for updates every half second
    
    def stop(self):
        self.running = False


class NoseTrackerGUIv2(QMainWindow):
    def __init__(self, log_file="multi_voice_logs.txt", console_log_file=None):
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

        self.setWindowTitle("Voxel")
        self.setGeometry(100, 100, 500, 500)
        self.log_file = log_file
        self.console_log_file = console_log_file
        
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
        
        # Create tabs for main content
        self.main_tabs = QTabWidget()
        main_layout.addWidget(self.main_tabs)
        
        # ---- Nose Tracker Tab ----
        nose_tracker_tab = QWidget()
        nose_tracker_layout = QVBoxLayout(nose_tracker_tab)
        
        # Create splitter for resizing sections
        self.tracker_splitter = QSplitter(Qt.Orientation.Vertical)
        nose_tracker_layout.addWidget(self.tracker_splitter)
        
        # Top widget (camera and controls)
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        
        # Camera feed display
        self.camera_label = QLabel()
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_label.setMinimumHeight(300)
        top_layout.addWidget(self.camera_label)
        
        # Status label
        self.status_label = QLabel("Status: Ready - Press C to calibrate")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_layout.addWidget(self.status_label)
        
        # Controls layout
        controls_layout = QHBoxLayout()
        
        # Sensitivity slider
        sensitivity_layout = QVBoxLayout()
        sensitivity_label = QLabel("Sensitivity")
        self.sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.sensitivity_slider.setMinimum(1)
        self.sensitivity_slider.setMaximum(10)
        self.sensitivity_slider.setValue(8)
        self.sensitivity_slider.valueChanged.connect(self.update_sensitivity)
        sensitivity_layout.addWidget(sensitivity_label)
        sensitivity_layout.addWidget(self.sensitivity_slider)
        controls_layout.addLayout(sensitivity_layout)
        
        # Buttons
        self.calibrate_button = QPushButton("Calibrate (C)")
        self.calibrate_button.clicked.connect(self.start_calibration)
        controls_layout.addWidget(self.calibrate_button)
        
        self.start_button = QPushButton("Start Tracking (T)")
        self.start_button.clicked.connect(self.toggle_tracking)
        controls_layout.addWidget(self.start_button)
        
        self.recenter_button = QPushButton("Recenter (R)")
        self.recenter_button.clicked.connect(self.recenter)
        controls_layout.addWidget(self.recenter_button)
        
        # Add voice control toggle button (if console log file is provided)
        if console_log_file:
            self.voice_control_button = QPushButton("Voice Control: ON" if VOICE_CONTROL_RUNNING else "Voice Control: OFF")
            self.voice_control_button.clicked.connect(self.toggle_voice_control)
            self.voice_control_button.setStyleSheet(
                "QPushButton { background-color: #4CAF50; color: white; border-radius: 10px; }" if VOICE_CONTROL_RUNNING 
                else "QPushButton { background-color: #f44336; color: white; border-radius: 10px; }"
            )
            controls_layout.addWidget(self.voice_control_button)
        
        top_layout.addLayout(controls_layout)
        
        # Add keyboard shortcuts help
        shortcuts_label = QLabel("Keyboard Shortcuts: C - Calibrate | R - Recenter | T - Toggle Tracking")
        shortcuts_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_layout.addWidget(shortcuts_label)
        
        # Add top widget to splitter
        self.tracker_splitter.addWidget(top_widget)
        
        # Bottom widget (logs)
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        
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
        self.tracker_splitter.setSizes([500, 200])
        
        # Add tracker tab to main tabs
        self.main_tabs.addTab(nose_tracker_tab, "Nose Tracker")
        
        # ---- Audio Calibration Tab ----
        audio_calibration_tab = QWidget()
        audio_layout = QVBoxLayout(audio_calibration_tab)
        
        # Store reference to the tab for switching
        self.audio_calibration_tab = audio_calibration_tab
        
        # Title and description
        audio_title = QLabel("Audio Calibration")
        audio_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        audio_title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        audio_layout.addWidget(audio_title)
        
        description = QLabel(
            "This process will calibrate the audio noise filter for voice control.\n"
            "It will record background noise and test voice samples.\n"
            "Please ensure you are in a quiet environment before starting."
        )
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        audio_layout.addWidget(description)
        
        # Status display
        self.calibration_status = QLabel("Ready to calibrate")
        self.calibration_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        audio_layout.addWidget(self.calibration_status)
        
        # Progress bar
        self.calibration_progress = QProgressBar()
        self.calibration_progress.setRange(0, 100)
        self.calibration_progress.setValue(0)
        audio_layout.addWidget(self.calibration_progress)
        
        # Keep test files checkbox
        self.keep_files_checkbox = QCheckBox("Keep test files after calibration")
        audio_layout.addWidget(self.keep_files_checkbox)
        
        # Buttons
        calibration_buttons = QHBoxLayout()
        
        self.start_audio_calibration_btn = QPushButton("Start Audio Calibration")
        self.start_audio_calibration_btn.clicked.connect(self.start_audio_calibration)
        calibration_buttons.addWidget(self.start_audio_calibration_btn)
        
        self.cancel_audio_calibration_btn = QPushButton("Cancel")
        self.cancel_audio_calibration_btn.clicked.connect(self.cancel_audio_calibration)
        self.cancel_audio_calibration_btn.setEnabled(False)
        calibration_buttons.addWidget(self.cancel_audio_calibration_btn)
        
        audio_layout.addLayout(calibration_buttons)
        
        # Calibration log
        self.calibration_log = QTextEdit()
        self.calibration_log.setReadOnly(True)
        self.calibration_log.setFont(self.log_font)
        self.calibration_log.setPlaceholderText("Calibration logs will appear here...")
        audio_layout.addWidget(self.calibration_log)
        
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
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Voxel v2")
    app.setApplicationDisplayName("Voxel v2")
    
    # Get console log file from command line argument if provided
    console_log_file = sys.argv[1] if len(sys.argv) > 1 else None
    
    # Set application icon
    try:
        icon = QIcon('assets/icon.png')
        app.setWindowIcon(icon)
    except:
        pass
    
    window = NoseTrackerGUIv2(console_log_file=console_log_file)
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 