import argparse
import logging
import threading
import time
import traceback

from audio_to_cursor.multi_engine_voice_control import MultiEngineVoiceControl
from gui import main as gui_main
from pynosetracker import NoseTracker

# # Configure logging
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#     filename='app.log',
#     filemode='w'
# )
# logger = logging.getLogger("AppThreadManager")

def run_tracker_safely(tracker):
    """Wrapper function to catch and display exceptions in the tracker thread"""
    try:
        print("NoseTracker thread starting")
        tracker.run()
    except Exception as e:
        print(f"ERROR IN NOSETRACKER: {str(e)}")
        print(traceback.format_exc())

def run_voice_safely(voice_control):
    """Wrapper function to catch and display exceptions in the voice control thread"""
    try:
        print("VoiceControl thread starting")
        voice_control.run()
    except Exception as e:
        print(f"ERROR IN VOICE CONTROL: {str(e)}")
        print(traceback.format_exc())

def main():
    parser = argparse.ArgumentParser(description='Nose Tracking Mouse Control')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (no GUI)')
    parser.add_argument('--sensitivity', type=float, default=8.0, help='Default sensitivity (1-10)')
    # parser.add_argument('--use-old-calibration', action='store_true', help='Use existing calibration data if available')
    
    args = parser.parse_args()
    
    if args.headless:
        print("Starting application in headless mode")

        # Create instances
        tracker = NoseTracker(headless=True, default_sensitivity=args.sensitivity)
        voice_control = MultiEngineVoiceControl(move_distance=100, use_old_calibration=args.use_old_calibration)
        
        # Create threads with wrapper functions
        tracker_thread = threading.Thread(target=run_tracker_safely, args=(tracker,), daemon=True, name="NoseTracker")
        voice_thread = threading.Thread(target=run_voice_safely, args=(voice_control,), daemon=True, name="VoiceControl")
        
        # Start threads
        print("Starting nose tracker thread")
        tracker_thread.start()
        print("Starting voice control thread")
        voice_thread.start()
        
        # Keep main thread alive and monitor threads
        try:
            while True:
                print(f"NoseTracker thread is {'alive' if tracker_thread.is_alive() else 'dead'}")
                print(f"VoiceControl thread is {'alive' if voice_thread.is_alive() else 'dead'}")
                
                # Check if any thread died unexpectedly
                if not tracker_thread.is_alive():
                    print("NoseTracker thread died unexpectedly")
                
                if not voice_thread.is_alive():
                    print("VoiceControl thread died unexpectedly")
                
                time.sleep(5)  # Check every 5 seconds
        except KeyboardInterrupt:
            print("Received keyboard interrupt, shutting down...")
            print("\nShutting down. Press Ctrl+C again to force exit.")
    else:
        print("Starting application with GUI")
        gui_main()

if __name__ == '__main__':
    main()