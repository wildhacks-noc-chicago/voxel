import argparse
from pynosetracker import NoseTracker

def main():
    parser = argparse.ArgumentParser(description='Nose Tracking Mouse Control')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (no GUI)')
    parser.add_argument('--sensitivity', type=float, default=8.0, help='Default sensitivity (1-10)')
    
    args = parser.parse_args()
    
    # Create and run the nose tracker
    tracker = NoseTracker(headless=args.headless, default_sensitivity=args.sensitivity)
    tracker.run()

if __name__ == '__main__':
    main() 