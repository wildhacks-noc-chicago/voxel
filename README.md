# Voxel

Voxel is an advanced hands-free control system that combines voice recognition and computer vision technologies to enable intuitive interaction with your computer. Built as part of the Productivity/Wellness track for Wildhacks 2025, this project aims to make computing more accessible and efficient through multimodal inputs.

## Features

- **Voice Control**: Issue commands using natural language processing for hands-free operation
- **Nose Tracking**: Control cursor movement through facial gestures with precision
- **Modern GUI**: User-friendly PyQt6-based interface with real-time feedback
- **Multimodal Input**: Seamless integration of voice and visual inputs
- **Cross-Platform**: Compatible with various operating systems
- **Accessibility Focus**: Designed to make computing accessible for users with mobility limitations

## Requirements

- Python 3.12+
- OpenCV (opencv-python)
- Mediapipe 0.10.21
- PyQt6
- Speech recognition libraries (SpeechRecognition, pocketsphinx, vosk, faster_whisper)
- CUDA-compatible GPU (recommended for optimal performance)

## Installation

1. Clone the repository:

   ```
   git clone https://github.com/yourusername/voxel.git
   cd voxel
   ```
2. Create a virtual environment (recommended):

   ```
   conda create -n voxel python=3.12
   conda activate voxel
   ```
3. Install dependencies:

   ```
   pip install -r requirements.txt
   ```
4. Set up environment variables (if applicable):

   ```
   export VOXEL_CONFIG_PATH=/path/to/config
   ```

## Usage

1. Start the system with GUI:

   ```
   ./run_gui_v2.sh
   ```
2. Voice commands:

   - "Click" - Performs a click at the current cursor position
   - "Scroll up/down" - Scrolls the page in the specified direction
   - "Type [text]" - Types the specified text
   - "Double click" - Performs a double click operation
   - "Right click" - Performs a right click operation
   - "Drag" - Initiates drag operation
   - "Drop" - Completes drag and drop operation
   - Additional commands available in documentation
3. Nose tracking:

   - Move your nose to control cursor position
   - Adjust your head position to navigate the screen
   - Configure sensitivity in settings for personalized control

## Troubleshooting

- **Camera access issues**: Ensure your camera is properly connected and permissions are granted
- **Voice recognition problems**: Check microphone settings and ensure proper audio input
- **Semaphore errors**: Run the cleanup script or restart the application
- **Performance issues**: Consider using a dedicated GPU for improved tracking performance
- **Conda environment conflicts**: Make sure to activate the correct environment before running

## Logs

- Voice logs: `/multi_voice_logs.txt`
- Console logs: `/voice_control_console.log`

## Team

- Ashley J Williams
- Chloe Tan
- Keagan Pang
- Yuv Bindal

## Background

Voxel was created to address the need for more intuitive and accessible computer interfaces. By combining visual tracking and voice commands, we've developed a system that can be used by individuals with mobility limitations or those looking for more efficient ways to interact with their devices.

## Technical Implementation

### Facial Tracking for Mouse Movements

Our nose tracking system uses OpenCV and MediaPipe to create a precise facial mesh. By tracking specific facial landmarks, we can translate nose movement into cursor control with customizable sensitivity and acceleration profiles.

### Voice Recognition for Mouse Control

We've implemented a multi-engine voice recognition system that combines several technologies (SpeechRecognition, Vosk, Whisper) to ensure reliable command detection even in noisy environments. Natural language processing allows for intuitive command structures.

### GUI System

The PyQt6-based interface provides real-time feedback on tracking quality, recognized commands, and system status. Users can adjust settings and view performance metrics directly through the GUI.

### Deployment

The application is designed to be lightweight and compatible with various operating systems. Our semaphore cleanup system ensures reliable performance across multiple sessions.

## Technical Diagrams
See [Architecture Diagrams](assets/architecture_diagram.md) for detailed technical diagrams.

## Packages Used

### Nose Tracking

- `cv2` - OpenCV wrapper for Python
- `mediapipe` - Face mesh provider for the webcam
- `numpy` - It's numpy
- `PyQt6` - Python GUI library for developing native applications
- `pyautogui` - Python library for programmatic mouse/keyboard control

### Voice Recognition

- `SpeechRecognition` - Framework for working with various speech recognition engines
- `pocketsphinx` - Lightweight speech recognition library
- `vosk` - Offline speech recognition toolkit
- `faster_whisper` - Optimized implementation of OpenAI's Whisper model
- `azure-cognitiveservices-speech` - Microsoft's speech services integration
- `google-generativeai` - For advanced language understanding

### Audio Processing

- `noisereduce` - Audio noise reduction library
- `librosa` - Audio analysis tools
- `soundfile` - Audio file reading/writing
- `pynput` - Monitor and control input devices
