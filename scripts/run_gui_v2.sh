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

# Run the semaphore cleanup script before starting to ensure clean state
echo "Running semaphore cleanup before startup..."
if [ -f "./cleanup_semaphores.py" ]; then
    python3 ./cleanup_semaphores.py
else
    echo "Warning: semaphore cleanup script not found. Continuing without cleanup."
fi

# Create log files
CONSOLE_LOG="voice_control_console.log"
VOICE_LOG="multi_voice_logs.txt"

echo "Starting new session $(date)" > $CONSOLE_LOG
echo "Starting new session $(date)" > $VOICE_LOG

# Get absolute paths for log files
CONSOLE_LOG_ABS="$(pwd)/$CONSOLE_LOG"
VOICE_LOG_ABS="$(pwd)/$VOICE_LOG"

echo "Console log: $CONSOLE_LOG_ABS"
echo "Voice log: $VOICE_LOG_ABS"

# Start the voice control in the background with specific log file path
echo "Starting Voice Control in background..."
python3 voice_control.py --log-file "$VOICE_LOG_ABS" "$@" >> $CONSOLE_LOG 2>&1 &
VOICE_CONTROL_PID=$!

# Write PID to the log file so GUI can detect and control the process
echo "VOICE_CONTROL_PID: $VOICE_CONTROL_PID" >> $CONSOLE_LOG
echo "Started voice control with PID: $VOICE_CONTROL_PID"

# Sleep for a moment to allow voice control to initialize
sleep 1

# Start the GUI v2
echo "Starting GUI v2..."
python3 gui_v2.py $VOICE_LOG_ABS $CONSOLE_LOG

# ===== Enhanced Cleanup Process =====
echo "=== Running Voxel Cleanup Process ==="
echo "GUI closed, performing thorough cleanup..."

# Find all lingering voice control processes
echo "Finding all voice control processes..."
VOICE_PIDS=$(pgrep -f "python.*voice_control.py|python3.*voice_control.py")
VOICE_COUNT=$(echo "$VOICE_PIDS" | grep -v "^$" | wc -l | tr -d ' ')

# Find all lingering GUI processes
echo "Finding all GUI processes..."
GUI_PIDS=$(pgrep -f "python.*gui_v2.py|python3.*gui_v2.py")
GUI_COUNT=$(echo "$GUI_PIDS" | grep -v "^$" | wc -l | tr -d ' ')

# Show summary
echo "Found processes to clean up:"
echo "- Voice control processes: $VOICE_COUNT"
echo "- GUI processes: $GUI_COUNT"

# Terminate voice control processes
if [ $VOICE_COUNT -gt 0 ]; then
    echo "Terminating voice control processes..."
    echo "$VOICE_PIDS" | xargs -I{} echo "Killing process {}..."
    kill -15 $VOICE_PIDS 2>/dev/null || true
    sleep 1
    # Force kill any remaining processes
    kill -9 $VOICE_PIDS 2>/dev/null || true
fi

# Terminate GUI processes
if [ $GUI_COUNT -gt 0 ]; then
    echo "Terminating GUI processes..."
    echo "$GUI_PIDS" | xargs -I{} echo "Killing process {}..."
    kill -15 $GUI_PIDS 2>/dev/null || true
    sleep 1
    # Force kill any remaining processes
    kill -9 $GUI_PIDS 2>/dev/null || true
fi

# Verify all processes were terminated
REMAINING_PIDS=$(pgrep -f "python.*voice_control.py|python3.*voice_control.py|python.*gui_v2.py|python3.*gui_v2.py")
if [ -z "$REMAINING_PIDS" ]; then
    echo "✅ All Voxel processes successfully terminated!"
else
    REMAINING_COUNT=$(echo "$REMAINING_PIDS" | wc -l | tr -d ' ')
    echo "⚠️ $REMAINING_COUNT processes could not be terminated:"
    ps -o pid,ppid,%cpu,%mem,command -p $REMAINING_PIDS
fi

# Clean up state flag files
echo "Removing state flag files..."
FLAG_FILES=("typing_mode.flag" "mouse_lock.flag" "ai_editor.flag")
for flag in "${FLAG_FILES[@]}"; do
    if [ -f "$flag" ]; then
        rm -f "$flag"
        echo "Removed: $flag"
    fi
done

# Run final semaphore cleanup
echo "Running final semaphore cleanup..."
if [ -f "./cleanup_semaphores.py" ]; then
    python3 ./cleanup_semaphores.py
else
    echo "Warning: semaphore cleanup script not found. Continuing without cleanup."
fi

echo "Voxel system has been shut down and cleaned up."