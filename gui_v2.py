import sys
import os
import cv2
import threading
import time
import pyautogui
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QSlider, QLabel, QMessageBox,
                            QTextEdit, QSplitter, QTabWidget)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QIcon, QColor, QTextCursor, QFont
from pynosetracker import NoseTracker

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
        self.setWindowTitle("Voxel")
        self.setGeometry(0, 0, 500, 500)
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
        
        # Create splitter for resizing sections
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(self.splitter)
        
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
        
        top_layout.addLayout(controls_layout)
        
        # Add keyboard shortcuts help
        shortcuts_label = QLabel("Keyboard Shortcuts: C - Calibrate | R - Recenter | T - Toggle Tracking")
        shortcuts_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_layout.addWidget(shortcuts_label)
        
        # Add top widget to splitter
        self.splitter.addWidget(top_widget)
        
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
        self.splitter.addWidget(bottom_widget)
        
        # Set initial sizes for splitter
        self.splitter.setSizes([500, 200])
        
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
            
    def closeEvent(self, event):
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