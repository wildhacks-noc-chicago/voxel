import argparse
from gui import main as gui_main

def main():
    parser = argparse.ArgumentParser(description='Nose Tracking Mouse Control')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (no GUI)')
    parser.add_argument('--sensitivity', type=float, default=8.0, help='Default sensitivity (1-10)')
    
    args = parser.parse_args()
    
    if args.headless:
        from pynosetracker import NoseTracker
        tracker = NoseTracker(headless=True, default_sensitivity=args.sensitivity)
        tracker.run()
    else:
        gui_main()

if __name__ == '__main__':
    main()