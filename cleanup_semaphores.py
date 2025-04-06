#!/usr/bin/env python3
"""
Fix semaphore leaks in Python multiprocessing.
Run this script when you see warnings about leaked semaphores.
"""

import gc
import glob
import multiprocessing
import os
import sys
import tempfile
import time


def cleanup_resources():
    """Clean up multiprocessing resources and temporary files"""
    print("\n=== Cleaning up multiprocessing resources ===")
    
    # Force garbage collection first
    print("Step 1: Forcing garbage collection...")
    gc.collect()
    
    # Try to directly clear the resource tracker
    print("Step 2: Clearing multiprocessing resource tracker...")
    try:
        if hasattr(multiprocessing, 'resource_tracker') and hasattr(multiprocessing.resource_tracker, '_resource_tracker'):
            multiprocessing.resource_tracker._resource_tracker.clear()
            print("Successfully cleared resource tracker")
        else:
            print("Resource tracker not accessible")
    except Exception as e:
        print(f"Error clearing resource tracker: {e}")
    
    # On macOS, cleanup shared memory and semaphores
    if sys.platform == 'darwin':
        print("Step 3: Running macOS-specific cleanup...")
        
        # Check temp directory for multiprocessing lock files
        temp_dir = tempfile.gettempdir()
        print(f"Checking temp directory: {temp_dir}")
        
        # Look for multiprocessing lock files
        mp_locks = glob.glob(os.path.join(temp_dir, "pymp-*"))
        if mp_locks:
            print(f"Found {len(mp_locks)} multiprocessing lock files")
            for lock_file in mp_locks:
                try:
                    os.unlink(lock_file)
                    print(f"Removed: {lock_file}")
                except Exception as e:
                    print(f"Failed to remove {lock_file}: {e}")
        else:
            print("No multiprocessing lock files found")
        
        # Try to clear any SHM (shared memory) files
        try:
            user_id = os.getuid()
            shm_dir = "/dev/shm"
            if os.path.exists(shm_dir) and os.path.isdir(shm_dir):
                shm_files = glob.glob(os.path.join(shm_dir, f"sem.{user_id}_*"))
                if shm_files:
                    print(f"Found {len(shm_files)} SHM semaphore files")
                    for shm_file in shm_files:
                        try:
                            os.unlink(shm_file)
                            print(f"Removed: {shm_file}")
                        except Exception as e:
                            print(f"Failed to remove {shm_file}: {e}")
                else:
                    print("No SHM semaphore files found")
        except Exception as e:
            print(f"Error during SHM cleanup: {e}")
    
    # Check for state flag files
    print("\nStep 4: Checking for state flag files...")
    flag_files = ["typing_mode.flag", "mouse_lock.flag", "ai_editor.flag"]
    flags_found = False
    for flag_file in flag_files:
        if os.path.exists(flag_file):
            flags_found = True
            print(f"Found state flag file: {flag_file}")
    
    if not flags_found:
        print("No state flag files found")
        
    print("\n=== Cleanup complete ===")

def main():
    try:
        # Run the cleanup
        cleanup_resources()
        
        # Also trigger Python's internal cleanup
        time.sleep(0.5)  # Short delay to let things settle
        gc.collect()  # Second garbage collection pass
        
        print("\nSemaphore cleanup is complete.")
        print("If you still see semaphore warnings, try restarting the Voxel application.")
    except Exception as e:
        print(f"Error during cleanup: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 