import argparse
import logging
import os
import traceback

from audio_to_cursor.multi_engine_voice_control import MultiEngineVoiceControl


def run_voice_safely(voice_control):
    """Wrapper function to catch and display exceptions in the voice control process"""
    try:
        print("Voice Control starting")
        print("\n🔥 NEW FEATURE: AI Editor 🔥")
        print("Say 'enable AI' to turn on the AI editor")
        print("When typing mode is active and AI is enabled, your text will be automatically")
        print("enhanced when you say 'stop typing'")
        print("Say 'disable AI' to turn off this feature")
        
        print("\n🔊 NEW FEATURE: Sound Effects 🔊")
        print("A sound will play when commands are successfully executed")
        print("This provides audio feedback for command recognition\n")
        
        voice_control.run()
    except Exception as e:
        print(f"ERROR IN VOICE CONTROL: {str(e)}")
        print(traceback.format_exc())

def main():
    parser = argparse.ArgumentParser(description='Voice Control for Cursor Movement')
    parser.add_argument('--move-distance', type=int, default=100, 
                        help='Default movement distance for cursor commands (pixels)')
    parser.add_argument('--config', type=str, default="./audio_to_cursor/voice_config.json",
                        help='Path to voice control configuration file')
    parser.add_argument('--log-file', type=str, default="multi_engine_voice_control.log",
                        help='Path to log file for voice commands')
    
    args = parser.parse_args()
    
    # Convert relative paths to absolute paths
    if not os.path.isabs(args.log_file):
        # If it's a relative path, make it relative to the current working directory
        args.log_file = os.path.abspath(args.log_file)
    
    print(f"Starting voice control with:")
    print(f"- Move distance: {args.move_distance}")
    print(f"- Log file: {args.log_file}")
    
    voice_control = MultiEngineVoiceControl(
        config_file=args.config,
        log_file=args.log_file,
        move_distance=args.move_distance
    )
    
    # Run the voice control directly in this process
    run_voice_safely(voice_control)

if __name__ == '__main__':
    main() 