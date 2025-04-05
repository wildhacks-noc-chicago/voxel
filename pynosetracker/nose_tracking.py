import cv2
import mediapipe as mp
import pyautogui
import numpy as np
import platform
import time

class NoseTracker:
    def __init__(self, headless=False, default_sensitivity=8.0):
        self.headless = headless
        self.sensitivity = default_sensitivity
        self.base_sensitivity = 2.0
        self.smoothing = 0.3
        self.prev_x, self.prev_y = 0, 0
        
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

    def run(self):
        self.calibrate_using_keypress()
        
        # Check if calibration was successful
        if not hasattr(self, 'face_center') or not hasattr(self, 'nose_center'):
            print("Error: Calibration failed. Cannot start nose tracking.")
            return
        
        while True:
            ret, frame = self.cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
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
        """Run nose tracking for a single frame in GUI mode.
        Returns the annotated frame with tracking visualization."""
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
        self.cap.release()
        if not self.headless:
            cv2.destroyAllWindows()
        self.face_mesh.close() 