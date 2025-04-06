#!/bin/bash

# cleanup_voxel.sh - Script to kill all lingering Voxel processes
# Usage: bash cleanup_voxel.sh

echo "=== Voxel Process Cleanup Tool ==="
echo "Searching for running Voxel processes..."

# Find all Python processes related to Voxel
echo "Finding voice control processes..."
VOICE_PIDS=$(pgrep -f "python.*voice_control.py|python3.*voice_control.py")
VOICE_COUNT=$(echo "$VOICE_PIDS" | grep -v "^$" | wc -l | tr -d ' ')

echo "Finding GUI processes..."
GUI_PIDS=$(pgrep -f "python.*gui_v2.py|python3.*gui_v2.py")
GUI_COUNT=$(echo "$GUI_PIDS" | grep -v "^$" | wc -l | tr -d ' ')

# Count total processes
TOTAL_COUNT=$((VOICE_COUNT + GUI_COUNT))

if [ $TOTAL_COUNT -eq 0 ]; then
    echo "No running Voxel processes found."
    exit 0
fi

echo "Found $TOTAL_COUNT running Voxel processes:"
echo "- Voice control processes: $VOICE_COUNT"
echo "- GUI processes: $GUI_COUNT"

# Show process details
if [ $VOICE_COUNT -gt 0 ]; then
    echo -e "\nVoice control processes:"
    ps -o pid,ppid,%cpu,%mem,command -p $VOICE_PIDS
fi

if [ $GUI_COUNT -gt 0 ]; then
    echo -e "\nGUI processes:"
    ps -o pid,ppid,%cpu,%mem,command -p $GUI_PIDS
fi

# Ask for confirmation
echo -e "\nDo you want to kill all these processes? (y/n)"
read -r answer

if [[ "$answer" =~ ^[Yy]$ ]]; then
    # Kill all processes
    echo "Killing all Voxel processes..."
    
    if [ $VOICE_COUNT -gt 0 ]; then
        echo "Terminating voice control processes..."
        kill -15 $VOICE_PIDS 2>/dev/null
        sleep 1
        # Force kill any remaining processes
        kill -9 $VOICE_PIDS 2>/dev/null
    fi
    
    if [ $GUI_COUNT -gt 0 ]; then
        echo "Terminating GUI processes..."
        kill -15 $GUI_PIDS 2>/dev/null
        sleep 1
        # Force kill any remaining processes
        kill -9 $GUI_PIDS 2>/dev/null
    fi
    
    echo "Cleanup complete. Verifying all processes were terminated..."
    
    # Check if any processes are still running
    REMAINING_PIDS=$(pgrep -f "python.*voice_control.py|python3.*voice_control.py|python.*gui_v2.py|python3.*gui_v2.py")
    if [ -z "$REMAINING_PIDS" ]; then
        echo "✅ All Voxel processes successfully terminated!"
    else
        REMAINING_COUNT=$(echo "$REMAINING_PIDS" | wc -l | tr -d ' ')
        echo "⚠️ $REMAINING_COUNT processes could not be terminated. You may need to manually kill:"
        ps -o pid,ppid,%cpu,%mem,command -p $REMAINING_PIDS
    fi
else
    echo "Operation cancelled."
fi

# Also check for any flag files that might need cleanup
echo -e "\nChecking for state flag files..."
FLAG_FILES=("typing_mode.flag" "mouse_lock.flag" "ai_editor.flag")
FLAG_COUNT=0

for flag in "${FLAG_FILES[@]}"; do
    if [ -f "$flag" ]; then
        echo "Found flag file: $flag"
        FLAG_COUNT=$((FLAG_COUNT + 1))
    fi
done

if [ $FLAG_COUNT -gt 0 ]; then
    echo -e "\nDo you want to remove these flag files? (y/n)"
    read -r answer
    
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        for flag in "${FLAG_FILES[@]}"; do
            if [ -f "$flag" ]; then
                rm "$flag"
                echo "Removed: $flag"
            fi
        done
        echo "✅ All flag files removed."
    else
        echo "Flag files not removed."
    fi
else
    echo "No flag files found."
fi

echo -e "\nVoxel cleanup completed." 