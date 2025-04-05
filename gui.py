import sys
import cv2
import pyautogui
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QSlider, QLabel, QMessageBox)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from pynosetracker import NoseTracker

class NoseTrackerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nose Tracker")
        self.setGeometry(100, 100, 800, 600)
        
        # Initialize nose tracker
        self.tracker = NoseTracker(headless=False)
        self.tracking_active = False
        self.calibrating = False
        self.calibration_attempts = 0
        self.max_calibration_attempts = 10
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Camera feed display
        self.camera_label = QLabel()
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.camera_label)
        
        # Status label
        self.status_label = QLabel("Status: Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
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
        self.calibrate_button = QPushButton("Calibrate")
        self.calibrate_button.clicked.connect(self.start_calibration)
        controls_layout.addWidget(self.calibrate_button)
        
        self.start_button = QPushButton("Start Tracking")
        self.start_button.clicked.connect(self.toggle_tracking)
        controls_layout.addWidget(self.start_button)
        
        self.recenter_button = QPushButton("Recenter")
        self.recenter_button.clicked.connect(self.recenter)
        controls_layout.addWidget(self.recenter_button)
        
        layout.addLayout(controls_layout)
        
        # Timer for updating camera feed
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)  # Update every 30ms
        
    def update_sensitivity(self, value):
        self.tracker.sensitivity = self.tracker.base_sensitivity * value
        
    def start_calibration(self):
        self.calibrating = True
        self.calibration_attempts = 0
        self.status_label.setText("Status: Calibrating...")
        self.calibrate_button.setText("Calibrating...")
        self.calibrate_button.setEnabled(False)
        
    def perform_calibration(self, frame):
        success, annotated_frame = self.tracker.calibrate_for_gui(frame)
        
        if success:
            self.calibrating = False
            self.status_label.setText("Status: Calibrated")
            self.calibrate_button.setText("Calibrate")
            self.calibrate_button.setEnabled(True)
            QMessageBox.information(self, "Calibration", "Calibration successful!")
            return annotated_frame
        else:
            self.calibration_attempts += 1
            if self.calibration_attempts >= self.max_calibration_attempts:
                self.calibrating = False
                self.status_label.setText("Status: Calibration Failed")
                self.calibrate_button.setText("Calibrate")
                self.calibrate_button.setEnabled(True)
                QMessageBox.warning(self, "Calibration Failed", 
                                  "Could not detect face. Please ensure your face is visible and well-lit.")
            return annotated_frame
        
    def toggle_tracking(self):
        if not self.tracking_active:
            if not hasattr(self.tracker, 'face_center') or not hasattr(self.tracker, 'nose_center'):
                QMessageBox.warning(self, "Error", "Please calibrate first!")
                return
            self.tracking_active = True
            self.start_button.setText("Stop Tracking")
            self.status_label.setText("Status: Tracking")
        else:
            self.tracking_active = False
            self.start_button.setText("Start Tracking")
            self.status_label.setText("Status: Ready")
            
    def recenter(self):
        screen_w, screen_h = self.tracker.screen_w, self.tracker.screen_h
        pyautogui.moveTo(screen_w // 2, screen_h // 2)
        self.tracker.prev_x, self.tracker.prev_y = screen_w // 2, screen_h // 2
        
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
        self.tracker.__del__()
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = NoseTrackerGUI()
    window.show()
    sys.exit(app.exec()) 