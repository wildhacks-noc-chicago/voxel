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

# Create a log file for console output
CONSOLE_LOG="voice_control_console.log"
echo "Starting new session $(date)" > $CONSOLE_LOG

# Start the voice control in the background
echo "Starting Voice Control in background..."
python3 voice_control.py "$@" >> $CONSOLE_LOG 2>&1 &
VOICE_CONTROL_PID=$!

# Sleep for a moment to allow voice control to initialize
sleep 2

# Start the GUI v2
echo "Starting GUI v2..."
python3 gui_v2.py $CONSOLE_LOG

# When GUI exits, also stop the voice control
echo "GUI closed, shutting down voice control..."
if ps -p $VOICE_CONTROL_PID > /dev/null; then
    kill $VOICE_CONTROL_PID
fi

echo "Voxel system has been shut down." 