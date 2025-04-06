import os
import platform
import time

import cv2
import mediapipe as mp
import numpy as np
import pyautogui

# File-based lock state
MOUSE_LOCK_FILE = "mouse_lock.flag"

# Helper function to check mouse lock status
def is_mouse_locked():
    """Check if mouse is locked by checking the lock file"""
    return os.path.exists(MOUSE_LOCK_FILE)


class NoseTracker:
    def __init__(self, headless=False, default_sensitivity=8.0):
        self.headless = headless
        self.sensitivity = default_sensitivity
        self.base_sensitivity = 2.0
        self.smoothing = 0.3
        self.prev_x, self.prev_y = 0, 0
        
        # Remember if tracking is active - used for lock/unlock
        self.tracking_active = False
        
        # Print system info
        print(f"Python version: {platform.python_version()}")
        print(f"System: {platform.system()} {platform.release()}")
        print(f"Processor: {platform.processor()}")
        
        # Initialize mediapipe face detection
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        # Get built-in webcam
        self.camera_index = self._get_builtin_camera()
        print(f"Using camera at index {self.camera_index}")
        self.cap = cv2.VideoCapture(self.camera_index)
        
        # Set camera to highest possible FPS
        self.cap.set(cv2.CAP_PROP_FPS, 120)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        # Get screen dimensions
        self.screen_w, self.screen_h = pyautogui.size()
        
        # Disable pyautogui's fail-safe
        pyautogui.FAILSAFE = False
        
        # Initialize window if not headless
        if not self.headless:
            ret, frame = self.cap.read()
            if ret:
                height, width = frame.shape[:2]
                cv2.namedWindow('Nose Tracking')
                self._center_window('Nose Tracking', width, height)

    def _center_window(self, window_name, width, height):
        x = (self.screen_w - width) // 2
        y = (self.screen_h - height) // 2
        cv2.moveWindow(window_name, x, y)

    def _get_builtin_camera(self):
        for i in range(10):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                if width in [1280, 640] and height in [720, 480]:
                    return i
                cap.release()
        return 0
    
    def calibrate(self):
        face_center = None
        nose_center = None
        
        ret, frame = self.cap.read()
        if not ret:
            return False
            
        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)
        
        if results.multi_face_landmarks:
            mesh_points = np.array([np.multiply([p.x, p.y], [frame.shape[1], frame.shape[0]]).astype(int) 
                                  for p in results.multi_face_landmarks[0].landmark])
            
            nose_tip = mesh_points[4]
            face_center = np.mean(mesh_points, axis=0).astype(int)
            
            if not self.headless:
                cv2.circle(frame, tuple(nose_tip), 5, (0, 255, 0), -1)
                cv2.circle(frame, tuple(face_center), 5, (255, 0, 0), -1)
                cv2.line(frame, tuple(face_center), tuple(nose_tip), (0, 255, 255), 2)
                cv2.imshow('Nose Tracking', frame)
            
            nose_center = (nose_tip[0] - face_center[0], nose_tip[1] - face_center[1])
            self.face_center = face_center
            self.nose_center = nose_center
            return True
            
        return False

    def calibrate_using_keypress(self):
        print("Starting calibration...")
        
        if self.headless:
            print("Headless mode: Attempting automatic calibration...")
            max_attempts = 10
            for attempt in range(max_attempts):
                if self.calibrate():
                    print("Calibration complete!")
                    return
                print(f"Calibration attempt {attempt + 1}/{max_attempts} failed, retrying...")
                time.sleep(0.5)  # Wait a bit before retrying
            print("Calibration failed after multiple attempts. Please check your camera and lighting conditions.")
            return
        
        print("Look straight at the camera and press 'c' to calibrate")
        while True:
            ret, frame = self.cap.read()
            if not ret:
                continue
                
            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb_frame)
            
            if results.multi_face_landmarks:
                mesh_points = np.array([np.multiply([p.x, p.y], [frame.shape[1], frame.shape[0]]).astype(int) 
                                      for p in results.multi_face_landmarks[0].landmark])
                
                nose_tip = mesh_points[4]
                face_center = np.mean(mesh_points, axis=0).astype(int)
                
                if not self.headless:
                    cv2.circle(frame, tuple(nose_tip), 5, (0, 255, 0), -1)
                    cv2.circle(frame, tuple(face_center), 5, (255, 0, 0), -1)
                    cv2.line(frame, tuple(face_center), tuple(nose_tip), (0, 255, 255), 2)
                    cv2.putText(frame, "Press 'c' to calibrate", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    cv2.imshow('Nose Tracking', frame)
            
            key = cv2.waitKey(1) & 0xFF if not self.headless else 0
            if key == ord('c'):
                if self.calibrate():
                    print("Calibration complete!")
                    break
                else:
                    print("Calibration failed, please try again")

    def calibrate_for_gui(self, frame):
        """Calibrate using the provided frame from the GUI.
        Returns (success, annotated_frame) where annotated_frame is the frame with calibration visualization."""
        if not hasattr(self, 'face_mesh'):
            return False, frame
            
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)
        print(results)
        
        if results.multi_face_landmarks:
            mesh_points = np.array([np.multiply([p.x, p.y], [frame.shape[1], frame.shape[0]]).astype(int) 
                                  for p in results.multi_face_landmarks[0].landmark])
            
            nose_tip = mesh_points[4]
            face_center = np.mean(mesh_points, axis=0).astype(int)
            
            # Annotate the frame
            cv2.circle(frame, tuple(nose_tip), 5, (0, 255, 0), -1)
            cv2.circle(frame, tuple(face_center), 5, (255, 0, 0), -1)
            cv2.line(frame, tuple(face_center), tuple(nose_tip), (0, 255, 255), 2)
            cv2.putText(frame, "Calibrating...", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
            nose_center = (nose_tip[0] - face_center[0], nose_tip[1] - face_center[1])
            self.face_center = face_center
            self.nose_center = nose_center
            return True, frame
            
        return False, frame

    def is_mouse_locked(self):
        """Check if mouse is locked using file-based approach"""
        return is_mouse_locked()

    def run(self):
        """Main tracking loop with lock checking"""
        self.calibrate_using_keypress()
        
        # Check if calibration was successful
        if not hasattr(self, 'face_center') or not hasattr(self, 'nose_center'):
            print("Error: Calibration failed. Cannot start nose tracking.")
            return
        
        # Store last lock check time to avoid excessive file checks
        last_lock_check = 0
        lock_check_interval = 0.1  # seconds
        was_locked = False
        
        # Mark tracking as active - initial state
        self.tracking_active = True
        
        while True:
            # Check lock state periodically (not every frame)
            current_time = time.time()
            if current_time - last_lock_check > lock_check_interval:
                locked = self.is_mouse_locked()
                last_lock_check = current_time
                
                # Log state changes for better debugging
                if locked != was_locked:
                    if locked:
                        print("🔒 Mouse movement locked. Pausing nose tracking.")
                        # Explicitly make note that tracking is paused but not stopped
                        self.tracking_active = False
                    else:
                        print("🔓 Mouse movement unlocked. Resuming nose tracking.")
                        # Re-enable tracking
                        self.tracking_active = True
                    was_locked = locked
            
            # Capture frame regardless of lock state (keep camera active)
            ret, frame = self.cap.read()
            if not ret:
                break
                
            frame = cv2.flip(frame, 1)
            
            # If locked, show status but don't move cursor
            if was_locked:
                if not self.headless:
                    # Still show camera but with lock message
                    cv2.putText(frame, "🔒 MOUSE LOCKED BY VOICE", (50, 50), 
                              cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    cv2.putText(frame, "Manual mouse movement still works", (50, 100), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    cv2.imshow('Nose Tracking', frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        break
                continue  # Skip all tracking while locked
            
            # Only process tracking when unlocked
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb_frame)
            
            if results.multi_face_landmarks:
                mesh_points = np.array([np.multiply([p.x, p.y], [frame.shape[1], frame.shape[0]]).astype(int) 
                                      for p in results.multi_face_landmarks[0].landmark])
                
                nose_tip = mesh_points[4]
                nose_x = nose_tip[0] - self.face_center[0]
                nose_y = nose_tip[1] - self.face_center[1]
                
                rel_x = (nose_x - self.nose_center[0]) * self.sensitivity
                rel_y = (nose_y - self.nose_center[1]) * self.sensitivity
                
                screen_x = self.screen_w // 2 + rel_x
                screen_y = self.screen_h // 2 + rel_y
                
                cursor_x = int(self.prev_x + (screen_x - self.prev_x) * self.smoothing)
                cursor_y = int(self.prev_y + (screen_y - self.prev_y) * self.smoothing)
                
                # Double-check we're not locked before actually moving the mouse
                # This extra check helps if lock state changes during processing
                if not self.is_mouse_locked():
                    pyautogui.moveTo(cursor_x, cursor_y)
                    self.prev_x, self.prev_y = cursor_x, cursor_y
                
                if not self.headless:
                    cv2.circle(frame, tuple(nose_tip), 5, (0, 255, 0), -1)
                    cv2.circle(frame, tuple(self.face_center), 5, (255, 0, 0), -1)
                    cv2.line(frame, tuple(self.face_center), tuple(nose_tip), (0, 255, 255), 2)
                    
                    normalized_sensitivity = self.sensitivity / self.base_sensitivity
                    cv2.putText(frame, f"Sensitivity: {normalized_sensitivity:.0f}/10", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    cv2.putText(frame, "Press 'c' to recenter", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    cv2.imshow('Nose Tracking', frame)
            
            if not self.headless:
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('c'):
                    pyautogui.moveTo(self.screen_w // 2, self.screen_h // 2)
                    self.prev_x, self.prev_y = self.screen_w // 2, self.screen_h // 2
                elif key >= ord('1') and key <= ord('9'):
                    self.sensitivity = self.base_sensitivity * (key - ord('0'))
                elif key == ord('0'):
                    self.sensitivity = self.base_sensitivity * 10

    def run_for_gui(self, frame):
        """Run nose tracking for a single frame in GUI mode with lock checking."""
        # Check if mouse is locked - using file-based approach
        if self.is_mouse_locked():
            cv2.putText(frame, "🔒 MOUSE LOCKED BY VOICE", (50, 50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            cv2.putText(frame, "Manual mouse movement still works", (50, 100), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            # Make sure we mark tracking as inactive
            self.tracking_active = False
            return frame
            
        # Set tracking state to active
        self.tracking_active = True
            
        if not hasattr(self, 'face_center') or not hasattr(self, 'nose_center'):
            return frame
            
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)
        
        if results.multi_face_landmarks:
            mesh_points = np.array([np.multiply([p.x, p.y], [frame.shape[1], frame.shape[0]]).astype(int) 
                                  for p in results.multi_face_landmarks[0].landmark])
            
            nose_tip = mesh_points[4]
            nose_x = nose_tip[0] - self.face_center[0]
            nose_y = nose_tip[1] - self.face_center[1]
            
            rel_x = (nose_x - self.nose_center[0]) * self.sensitivity
            rel_y = (nose_y - self.nose_center[1]) * self.sensitivity
            
            screen_x = self.screen_w // 2 + rel_x
            screen_y = self.screen_h // 2 + rel_y
            
            cursor_x = int(self.prev_x + (screen_x - self.prev_x) * self.smoothing)
            cursor_y = int(self.prev_y + (screen_y - self.prev_y) * self.smoothing)
            
            # Double-check lock state before moving the mouse
            if not self.is_mouse_locked():
                pyautogui.moveTo(cursor_x, cursor_y)
                self.prev_x, self.prev_y = cursor_x, cursor_y
            
            # Annotate the frame
            cv2.circle(frame, tuple(nose_tip), 5, (0, 255, 0), -1)
            cv2.circle(frame, tuple(self.face_center), 5, (255, 0, 0), -1)
            cv2.line(frame, tuple(self.face_center), tuple(nose_tip), (0, 255, 255), 2)
            
            normalized_sensitivity = self.sensitivity / self.base_sensitivity
            cv2.putText(frame, f"Sensitivity: {normalized_sensitivity:.0f}/10", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            cv2.putText(frame, "Tracking Active", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
        return frame

    def __del__(self):
        """Clean up resources when the object is garbage collected."""
        try:
            # Stop the video capture if it exists
            if hasattr(self, 'cap') and self.cap is not None:
                self.cap.release()
                
            # Destroy any OpenCV windows if not in headless mode
            if hasattr(self, 'headless') and not self.headless:
                try:
                    import cv2
                    cv2.destroyAllWindows()
                except:
                    pass
                
            # Close the face mesh if it exists and hasn't already been closed
            if hasattr(self, 'face_mesh') and self.face_mesh is not None:
                try:
                    # Check if the MediaPipe graph still exists before closing
                    if hasattr(self.face_mesh, '_graph') and self.face_mesh._graph is not None:
                        self.face_mesh.close()
                except (ValueError, AttributeError):
                    # Ignore errors if the face_mesh is already closed or being finalized
                    pass
        except Exception as e:
            # Just log the error - can't do much during garbage collection
            pass 