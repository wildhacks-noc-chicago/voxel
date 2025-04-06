#!/bin/bash

# Exit on error
set -e

# Display what's happening
echo "Starting Voxel Calibration GUI (without voice control)..."
echo "This script runs ONLY the audio calibration tool."
echo "No voice control will be started."
echo ""

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

# Start the GUI v2 only
echo "Starting Calibration GUI..."
python3 gui_v2.py

echo "Calibration GUI has been closed." 