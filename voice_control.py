import argparse
import logging
import traceback

from audio_to_cursor.multi_engine_voice_control import MultiEngineVoiceControl

def run_voice_safely(voice_control):
    """Wrapper function to catch and display exceptions in the voice control process"""
    try:
        print("Voice Control starting")
        voice_control.run()
    except Exception as e:
        print(f"ERROR IN VOICE CONTROL: {str(e)}")
        print(traceback.format_exc())

def main():
    parser = argparse.ArgumentParser(description='Voice Control for Cursor Movement')
    parser.add_argument('--move-distance', type=int, default=100, 
                        help='Default movement distance for cursor commands (pixels)')
    parser.add_argument('--config', type=str, default="voice_config.json",
                        help='Path to voice control configuration file')
    parser.add_argument('--log-file', type=str, default="multi_voice_logs.txt",
                        help='Path to log file for voice commands')
    
    args = parser.parse_args()
    
    print(f"Starting voice control with move distance: {args.move_distance}")
    voice_control = MultiEngineVoiceControl(
        config_file=args.config,
        log_file=args.log_file,
        move_distance=args.move_distance
    )
    
    # Run the voice control directly in this process
    run_voice_safely(voice_control)

if __name__ == '__main__':
    main() 