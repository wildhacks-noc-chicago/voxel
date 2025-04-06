#!/usr/bin/env python3
"""
Fix semaphore leaks in Python multiprocessing.
Run this script when you see warnings about leaked semaphores.
"""

import atexit
import gc
import glob
import multiprocessing
import os
import signal
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
            
    # Check for any Python processes running voice control or GUI
    print("\nStep 4: Checking for running Voxel processes...")
    try:
        import psutil
        voxel_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.cmdline())
                if 'voice_control.py' in cmdline or 'gui_v2.py' in cmdline:
                    voxel_processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
                
        if voxel_processes:
            print(f"Found {len(voxel_processes)} running Voxel processes:")
            for proc in voxel_processes:
                print(f"PID {proc.pid}: {' '.join(proc.cmdline())}")
            
            choice = input("\nWould you like to terminate these processes? (y/n): ")
            if choice.lower() == 'y':
                for proc in voxel_processes:
                    try:
                        pid = proc.pid
                        proc.terminate()
                        print(f"Terminated process {pid}")
                    except Exception as e:
                        print(f"Failed to terminate process {proc.pid}: {e}")
        else:
            print("No running Voxel processes found")
    except ImportError:
        print("psutil module not available; can't check for running processes")
        print("Install with: pip install psutil")

    # Check for state flag files
    print("\nStep 5: Checking for state flag files...")
    flag_files = ["typing_mode.flag", "mouse_lock.flag", "ai_editor.flag"]
    flags_found = False
    for flag_file in flag_files:
        if os.path.exists(flag_file):
            flags_found = True
            try:
                os.remove(flag_file)
                print(f"Removed state flag file: {flag_file}")
            except Exception as e:
                print(f"Failed to remove {flag_file}: {e}")
    
    if not flags_found:
        print("No state flag files found")
        
    print("\n=== Cleanup complete ===")

def handle_signal(signum, frame):
    """Handle termination signals"""
    print(f"\nReceived signal {signum}, cleaning up...")
    cleanup_resources()
    sys.exit(0)

def main():
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # Register cleanup function
    atexit.register(cleanup_resources)
    
    # Print header
    print("\n=== Voxel Semaphore Leak Fixer ===")
    print("This script will clean up any leaked multiprocessing semaphores")
    print("Run this when you see the warning: 'There appear to be X leaked semaphore objects'")
    
    try:
        # Run the cleanup
        cleanup_resources()
        
        # Print instructions
        print("\nCleanup is complete. You can now restart the Voxel system.")
        print("Run: ./run_gui_v2.sh")
    except Exception as e:
        print(f"Error during cleanup: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 