#!/bin/bash

# Exit on error
set -e

# Display what's happening
echo "Starting Voxel system with GUI v2..."

# Check if we have Python3
if ! command -v python3 &> /dev/null; then
    echo "Python3 is required but not found. Please install Python3."
    exit 1
fi

# Check if required dependencies are installed
echo "Checking required dependencies..."
python3 -c "import sounddevice" 2>/dev/null || {
    echo "Installing sounddevice (required for audio calibration)..."
    pip install sounddevice
}

python3 -c "import noisereduce" 2>/dev/null || {
    echo "Installing noisereduce (required for audio calibration)..."
    pip install noisereduce
}

python3 -c "import librosa" 2>/dev/null || {
    echo "Installing librosa (required for audio calibration)..."
    pip install librosa
}

# Create a log file for console output
CONSOLE_LOG="voice_control_console.log"
echo "Starting new session $(date)" > $CONSOLE_LOG

# Start the voice control in the background
echo "Starting Voice Control in background..."
python3 voice_control.py "$@" >> $CONSOLE_LOG 2>&1 &
VOICE_CONTROL_PID=$!

# Write PID to the log file so GUI can detect and control the process
echo "VOICE_CONTROL_PID: $VOICE_CONTROL_PID" >> $CONSOLE_LOG
echo "Started voice control with PID: $VOICE_CONTROL_PID"

# Sleep for a moment to allow voice control to initialize
sleep 1

# Start the GUI v2
echo "Starting GUI v2..."
python3 gui_v2.py $CONSOLE_LOG

# When GUI exits, also stop the voice control
echo "GUI closed, shutting down voice control..."
if ps -p $VOICE_CONTROL_PID > /dev/null 2>&1; then
    echo "Killing voice control process ($VOICE_CONTROL_PID)..."
    kill $VOICE_CONTROL_PID
else
    echo "Voice control process ($VOICE_CONTROL_PID) is no longer running"
fi

echo "Voxel system has been shut down." 