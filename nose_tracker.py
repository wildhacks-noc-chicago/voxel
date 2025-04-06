#!/usr/bin/env python3
"""
Nose Tracker Module
------------------
This module provides the NoseTracker class for controlling the mouse using nose movements.
"""

import argparse

from pynosetracker.nose_tracking import NoseTracker

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Nose Tracking Mouse Control')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (no GUI)')
    parser.add_argument('--sensitivity', type=float, default=8.0, help='Default sensitivity (1-10)')

    args = parser.parse_args()

    tracker = NoseTracker(headless=True, default_sensitivity=args.sensitivity)
    tracker.run() 