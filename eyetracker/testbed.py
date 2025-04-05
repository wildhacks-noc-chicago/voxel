import cv2
import mediapipe as mp
import pyautogui
import numpy as np
from math import hypot
import time

def get_builtin_camera():
    # Try to find the built-in camera
    for i in range(10):  # Check first 10 indices
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            # Get camera properties
            width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            # Built-in cameras typically have specific resolutions
            if width in [1280, 640] and height in [720, 480]:
                return i
            cap.release()
    return 0  # Default to index 0 if no built-in camera found

def calibrate(cap, face_mesh):
    print("Starting calibration...")
    print("Look at the four corners of the screen when prompted")
    
    # Define calibration points (corners of the screen)
    screen_w, screen_h = pyautogui.size()
    calibration_points = [
        (0, 0),  # Top-left
        (screen_w, 0),  # Top-right
        (screen_w, screen_h),  # Bottom-right
        (0, screen_h)  # Bottom-left
    ]
    
    # Store eye positions for each calibration point
    eye_positions = []
    
    for i, (target_x, target_y) in enumerate(calibration_points):
        print(f"Look at corner {i+1} (press 'c' when ready)")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
                
            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb_frame)
            
            if results.multi_face_landmarks:
                mesh_points = np.array([np.multiply([p.x, p.y], [frame.shape[1], frame.shape[0]]).astype(int) 
                                      for p in results.multi_face_landmarks[0].landmark])
                
                # Get eye landmarks
                left_eye = [mesh_points[145], mesh_points[159]]
                right_eye = [mesh_points[374], mesh_points[386]]
                
                # Calculate eye centers
                left_center = np.mean(left_eye, axis=0).astype(int)
                right_center = np.mean(right_eye, axis=0).astype(int)
                
                # Calculate gaze point
                gaze_x = int((left_center[0] + right_center[0]) / 2)
                gaze_y = int((left_center[1] + right_center[1]) / 2)
                
                # Draw visual feedback
                cv2.circle(frame, (gaze_x, gaze_y), 5, (0, 255, 0), -1)
                cv2.circle(frame, tuple(left_center), 3, (0, 0, 255), -1)
                cv2.circle(frame, tuple(right_center), 3, (0, 0, 255), -1)
                
                # Show target point
                target_x, target_y = calibration_points[i]
                # Offset the text position by 20 pixels to make it more visible
                text_x = int(target_x) - 20 if target_x > 0 else 0
                text_y = int(target_y) - 20 if target_y > 0 else 0
                cv2.putText(frame, f"Look here ->", (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
            cv2.imshow('Calibration', frame)
            
            if cv2.waitKey(1) & 0xFF == ord('c'):
                if results.multi_face_landmarks:
                    eye_positions.append((gaze_x, gaze_y))
                break
    
    # Calculate mapping parameters
    eye_x_min = min(p[0] for p in eye_positions)
    eye_x_max = max(p[0] for p in eye_positions)
    eye_y_min = min(p[1] for p in eye_positions)
    eye_y_max = max(p[1] for p in eye_positions)
    
    print("Calibration complete!")
    return {
        'eye_x_range': (eye_x_min, eye_x_max),
        'eye_y_range': (eye_y_min, eye_y_max),
        'screen_size': (screen_w, screen_h)
    }

# Initialize mediapipe face detection
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# Get built-in webcam
camera_index = get_builtin_camera()
print(f"Using camera at index {camera_index}")
cap = cv2.VideoCapture(camera_index)

# Calibrate the system
calibration = calibrate(cap, face_mesh)
eye_x_min, eye_x_max = calibration['eye_x_range']
eye_y_min, eye_y_max = calibration['eye_y_range']
screen_w, screen_h = calibration['screen_size']

# Disable pyautogui's fail-safe
pyautogui.FAILSAFE = False

# Function to calculate midpoint
def midpoint(p1, p2):
    return int((p1.x + p2.x)/2), int((p1.y + p2.y)/2)

# Smoothing factor for cursor movement
smoothing = 0.5
prev_x, prev_y = 0, 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Flip the frame horizontally for a later selfie-view display
    frame = cv2.flip(frame, 1)
    
    # Convert the BGR image to RGB
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # Process the image and detect faces
    results = face_mesh.process(rgb_frame)
    
    if results.multi_face_landmarks:
        mesh_points = np.array([np.multiply([p.x, p.y], [frame.shape[1], frame.shape[0]]).astype(int) 
                              for p in results.multi_face_landmarks[0].landmark])
        
        # Get eye landmarks
        left_eye = [mesh_points[145], mesh_points[159]]
        right_eye = [mesh_points[374], mesh_points[386]]
        
        # Calculate eye centers
        left_center = np.mean(left_eye, axis=0).astype(int)
        right_center = np.mean(right_eye, axis=0).astype(int)
        
        # Calculate gaze point
        gaze_x = int((left_center[0] + right_center[0]) / 2)
        gaze_y = int((left_center[1] + right_center[1]) / 2)
        
        # Map eye position to screen coordinates using calibrated ranges
        screen_x = np.interp(gaze_x, [eye_x_min, eye_x_max], [0, screen_w])
        screen_y = np.interp(gaze_y, [eye_y_min, eye_y_max], [0, screen_h])
        
        # Apply smoothing
        cursor_x = int(prev_x + (screen_x - prev_x) * smoothing)
        cursor_y = int(prev_y + (screen_y - prev_y) * smoothing)
        
        # Move cursor
        pyautogui.moveTo(cursor_x, cursor_y)
        
        # Update previous positions
        prev_x, prev_y = cursor_x, cursor_y
        
        # Draw visual feedback
        cv2.circle(frame, (gaze_x, gaze_y), 5, (0, 255, 0), -1)
        cv2.circle(frame, tuple(left_center), 3, (0, 0, 255), -1)
        cv2.circle(frame, tuple(right_center), 3, (0, 0, 255), -1)

    # Display the frame
    cv2.imshow('Eye Tracking', frame)
    
    # Break the loop if 'q' is pressed
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release resources
cap.release()
cv2.destroyAllWindows() 