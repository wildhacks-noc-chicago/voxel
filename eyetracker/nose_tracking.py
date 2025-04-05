import cv2
import mediapipe as mp
import pyautogui
import numpy as np
from math import hypot
import time

def center_window(window_name, width, height):
    # Get screen dimensions
    screen_w, screen_h = pyautogui.size()
    
    # Calculate window position to center it
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    
    # Set window position
    cv2.moveWindow(window_name, x, y)

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
    print("Look straight at the camera and press 'c' to calibrate")
    
    # Get screen dimensions
    screen_w, screen_h = pyautogui.size()
    screen_center = (screen_w // 2, screen_h // 2)
    
    # Store the face center and nose position for calibration
    face_center = None
    nose_center = None
    
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
            
            # Get nose tip landmark (index 4 in MediaPipe face mesh)
            nose_tip = mesh_points[4]
            
            # Calculate face center
            face_center = np.mean(mesh_points, axis=0).astype(int)
            
            # Draw visual feedback
            cv2.circle(frame, tuple(nose_tip), 5, (0, 255, 0), -1)
            cv2.circle(frame, tuple(face_center), 5, (255, 0, 0), -1)
            cv2.line(frame, tuple(face_center), tuple(nose_tip), (0, 255, 255), 2)
            
            # Show calibration instructions
            cv2.putText(frame, "Press 'c' to calibrate", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        cv2.imshow('Nose Tracking', frame)
        
        if cv2.waitKey(1) & 0xFF == ord('c'):
            if results.multi_face_landmarks:
                # Store the relative position of the nose tip from the face center
                nose_center = (nose_tip[0] - face_center[0], nose_tip[1] - face_center[1])
                break
    
    print("Calibration complete!")
    return {
        'nose_center': nose_center,
        'screen_size': (screen_w, screen_h),
        'face_center': face_center
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

# Set camera to highest possible FPS
cap.set(cv2.CAP_PROP_FPS, 60)  # Try to set to 60 FPS
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffer size

# Get camera frame dimensions and create window
ret, frame = cap.read()
if ret:
    height, width = frame.shape[:2]
    cv2.namedWindow('Nose Tracking')
    center_window('Nose Tracking', width, height)

# Calibrate the system
calibration = calibrate(cap, face_mesh)
nose_center = calibration['nose_center']
screen_w, screen_h = calibration['screen_size']
face_center = calibration['face_center']

# Disable pyautogui's fail-safe
pyautogui.FAILSAFE = False

# Smoothing factor for cursor movement
smoothing = 0.3  # Reduced from 0.5 for faster response
prev_x, prev_y = 0, 0

# Sensitivity factor for cursor movement (1-10)
sensitivity = 8.0
base_sensitivity = 2.0

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
        
        # Get nose tip landmark (index 4 in MediaPipe face mesh)
        nose_tip = mesh_points[4]
        
        # Calculate nose position relative to face center
        nose_x = nose_tip[0] - face_center[0]
        nose_y = nose_tip[1] - face_center[1]
        
        # Calculate relative movement from calibrated center
        rel_x = (nose_x - nose_center[0]) * sensitivity
        rel_y = (nose_y - nose_center[1]) * sensitivity
        
        # Map to screen coordinates
        screen_x = screen_w // 2 + rel_x
        screen_y = screen_h // 2 + rel_y
        
        # Apply smoothing with reduced factor
        cursor_x = int(prev_x + (screen_x - prev_x) * smoothing)
        cursor_y = int(prev_y + (screen_y - prev_y) * smoothing)
        
        # Move cursor
        pyautogui.moveTo(cursor_x, cursor_y)
        
        # Update previous positions
        prev_x, prev_y = cursor_x, cursor_y
        
        # Draw visual feedback
        cv2.circle(frame, tuple(nose_tip), 5, (0, 255, 0), -1)
        cv2.circle(frame, tuple(face_center), 5, (255, 0, 0), -1)
        cv2.line(frame, tuple(face_center), tuple(nose_tip), (0, 255, 255), 2)
        
        # Show sensitivity and recenter instructions
        normalized_sensitivity = sensitivity / base_sensitivity
        cv2.putText(frame, f"Sensitivity: {normalized_sensitivity:.0f}/10", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        cv2.putText(frame, "Press 'c' to recenter", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    # Display the frame
    cv2.imshow('Nose Tracking', frame)
    
    # Handle key presses with minimal delay
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('c'):
        # Recenter the cursor
        pyautogui.moveTo(screen_w // 2, screen_h // 2)
        prev_x, prev_y = screen_w // 2, screen_h // 2
    elif key >= ord('1') and key <= ord('9'):
        # Set sensitivity based on number key (1-9)
        sensitivity = base_sensitivity * (key - ord('0'))
    elif key == ord('0'):
        # Set sensitivity to 10
        sensitivity = base_sensitivity * 10

# Release resources
cap.release()
cv2.destroyAllWindows() 