import datetime
import json
import logging
import os
import queue
import sys
import threading
import time

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='pyautogui_voice_control.log'
)
logger = logging.getLogger("PyAutoGUIVoiceControl")

# Check dependencies
def check_dependencies():
    missing_deps = []
    
    try:
        import speech_recognition as sr
    except ImportError:
        missing_deps.append("SpeechRecognition")
    
    try:
        import pyautogui
    except ImportError:
        missing_deps.append("pyautogui")
    
    try:
        import google.generativeai as genai
    except ImportError:
        missing_deps.append("google-generativeai")
    
    if missing_deps:
        print("Error: Missing dependencies:")
        for dep in missing_deps:
            print(f"  - {dep}")
        print("\nPlease install them using:")
        print(f"pip install {' '.join(missing_deps)}")
        return False
    
    return True

# Only proceed if dependencies are met
if not check_dependencies():
    sys.exit(1)

import speech_recognition as sr

# Import our custom modules
try:
    from multi_engine_voice_control import (
        GeminiIntentMapper,
        MultiEngineSpeechRecognition,
        load_env_file,
    )
    from pyautogui_command_executor import PyAutoGUICommandExecutor
except ImportError as e:
    logger.error(f"Error importing custom modules: {e}")
    print(f"Error: Could not import necessary modules: {e}")
    print("Make sure you're running this script from the correct directory.")
    sys.exit(1)

class PyAutoGUIVoiceControl:
    """Main class for voice control using multi-engine recognition and PyAutoGUI execution"""
    
    def __init__(self, config_file="voice_config.json", log_file="pyautogui_voice_logs.txt", move_distance=20):
        # Load environment variables
        load_env_file()
        
        # Set up logging
        self.log_file = log_file
        
        # Initialize command executor
        self.command_executor = PyAutoGUICommandExecutor(move_distance=move_distance)
        
        # Get available commands
        self.available_commands = list(self.command_executor.commands.keys())
        
        # Get API key for Gemini
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            logger.error("No Gemini API key found. Please add GEMINI_API_KEY to your .env file.")
            print("Error: No Gemini API key found. Please add GEMINI_API_KEY to your .env file.")
            sys.exit(1)
        
        # Initialize multi-engine speech recognition
        self.speech_module = MultiEngineSpeechRecognition(
            sr.Recognizer(),
            command_timeout=5  # 5 seconds timeout for commands
        )
        
        # Initialize Gemini intent mapper (without shortcuts for now)
        try:
            self.intent_mapper = GeminiIntentMapper(
                self.api_key,
                self.available_commands,
                {}  # No shortcuts for now
            )
            logger.info("PyAutoGUI voice control initialized with Gemini")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini intent mapper: {e}")
            print(f"Error: Failed to initialize Gemini intent mapper: {e}")
            sys.exit(1)
    
    def log_command(self, recognition_results, interpreted_command):
        """Log the recognition results and the final interpretation"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.log_file, "a") as f:
                f.write(f"{timestamp} | Multi-Engine Results:\n")
                for result in recognition_results:
                    if result["text"]:
                        f.write(f"  {result['engine'].capitalize()}: '{result['text']}'\n")
                f.write(f"  Final interpretation: '{interpreted_command}'\n\n")
            logger.info(f"Command logged: Final interpretation: '{interpreted_command}'")
        except Exception as e:
            logger.error(f"Error logging command: {e}")
    
    def process_voice_command(self):
        """Process a voice command through the entire pipeline using multiple engines"""
        # STEP 1: Multi-engine speech recognition
        recognition_results = self.speech_module.listen_and_recognize()
        if not recognition_results:
            return None, True
        
        # STEP 2: Intent mapping with Gemini using all recognition results
        interpreted_command = self.intent_mapper.map_multi_engine_intent(recognition_results)
        
        if not interpreted_command:
            print("Could not interpret the command.")
            return None, True
        
        # Log the command and interpretation
        self.log_command(recognition_results, interpreted_command)
        
        # Show final interpretation
        print(f"Final interpretation: '{interpreted_command}'")
        
        # STEP 3: Execute the command using PyAutoGUI
        should_continue = self.command_executor.execute_command(interpreted_command)
        
        return interpreted_command, should_continue
    
    def run(self):
        """Run the PyAutoGUI voice control system"""
        print("PyAutoGUI Voice Control System")
        print("================================")
        print("This system uses multiple speech recognition engines in parallel:")
        
        # Show which engines are available
        print("- Google (online)")
        if self.speech_module.engines_available["sphinx"]:
            print("- CMU Sphinx (offline)")
        if self.speech_module.engines_available["vosk"]:
            print("- Vosk (offline)")
            
        print("\nAll recognition results are fed to Gemini AI for better command interpretation.")
        print("The commands are then executed using PyAutoGUI.")
        print("You can speak naturally to control your computer.")
        
        print("\nAvailable commands:")
        # Group commands by category for better readability
        command_categories = {
            "Mouse Movement": ["right", "left", "up", "down"],
            "Mouse Actions": ["click", "left click", "right click"],
            "Keyboard": ["press enter", "press tab", "press escape", "press space"],
            "Scrolling": ["scroll up", "scroll down"],
            "Browser": ["open browser", "start typing"],
            "System": ["exit", "quit", "stop listening"]
        }
        
        for category, cmds in command_categories.items():
            print(f"  {category}:")
            for cmd in cmds:
                if cmd in self.available_commands:
                    print(f"    - '{cmd}'")
        
        print("\nLogs will be saved to:")
        print(f"- Command logs: {self.log_file}")
        print(f"- PyAutoGUI logs: pyautogui_commands.log")
        print(f"- Speech recognition logs: speech_recognition.log")
        
        logger.info("PyAutoGUI voice control system started")
        
        running = True
        while running:
            _, running = self.process_voice_command()
            
        logger.info("PyAutoGUI voice control system stopped")


if __name__ == "__main__":
    try:
        voice_control = PyAutoGUIVoiceControl()
        voice_control.run()
    except KeyboardInterrupt:
        logger.info("Program terminated by user")
        print("\nProgram terminated by user")
        sys.exit(0) 