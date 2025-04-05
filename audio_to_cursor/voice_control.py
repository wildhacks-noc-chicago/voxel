import datetime
import json
import logging
import os
import sys
import time

import pyautogui
import speech_recognition as sr
from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("speech_recognition.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("VoiceControl")

class VoiceControl:
    def __init__(self, config_file="voice_config.json"):
        # Configure PyAutoGUI
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1
        
        # Initialize controllers
        self.keyboard = KeyboardController()
        self.mouse = MouseController()
        
        # Default settings
        self.move_distance = 20
        self.command_timeout = 5
        self.speech_engine = "google"  # Options: "google", "whisper", "sphinx"
        self.whisper_model = "base"    # Options: "tiny", "base", "small", "medium", "large"
        
        # Load configuration if exists
        self.config_file = config_file
        self.commands = {
            # Mouse commands
            "move cursor right": self.move_right,
            "move cursor left": self.move_left,
            "move cursor up": self.move_up,
            "move cursor down": self.move_down,
            "click": self.press_enter,
            "left click": self.left_click,
            "right click": self.right_click,
            "double click": self.double_click,
            # Exit command
            "exit": self.exit_program,
            "quit": self.exit_program,
            "stop": self.exit_program
        }
        
        # Custom website shortcuts
        self.shortcuts = {}
        
        self.load_config()
        
        # Speech recognition setup
        self.recognizer = sr.Recognizer()
        
        # Check if required packages are installed based on selected engine
        self._check_required_packages()
        
        # Log startup
        logger.info(f"Voice control initialized with {self.speech_engine} speech engine")
        
    def _check_required_packages(self):
        """Check if required packages for the selected speech engine are installed"""
        if self.speech_engine == "whisper":
            try:
                import whisper
            except ImportError:
                logger.error("OpenAI Whisper not found. Installing...")
                try:
                    import subprocess
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai-whisper"])
                    logger.info("Whisper installed successfully")
                except Exception as e:
                    logger.error(f"Failed to install Whisper: {e}")
                    logger.info("Falling back to Google speech recognition")
                    self.speech_engine = "google"
        
        elif self.speech_engine == "sphinx":
            try:
                import pocketsphinx
            except ImportError:
                logger.error("PocketSphinx not found. Installing...")
                try:
                    import subprocess
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "pocketsphinx"])
                    logger.info("PocketSphinx installed successfully")
                except Exception as e:
                    logger.error(f"Failed to install PocketSphinx: {e}")
                    logger.info("Falling back to Google speech recognition")
                    self.speech_engine = "google"
        
    def load_config(self):
        """Load configuration from JSON file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                
                # Update settings
                self.move_distance = config.get('move_distance', self.move_distance)
                self.command_timeout = config.get('command_timeout', self.command_timeout)
                self.speech_engine = config.get('speech_engine', self.speech_engine)
                self.whisper_model = config.get('whisper_model', self.whisper_model)
                
                # Update shortcuts
                if 'shortcuts' in config:
                    self.shortcuts = config['shortcuts']
                    
                logger.info(f"Configuration loaded from {self.config_file}")
            except Exception as e:
                logger.error(f"Error loading configuration: {e}")
    
    def save_config(self):
        """Save current configuration to JSON file"""
        config = {
            'move_distance': self.move_distance,
            'command_timeout': self.command_timeout,
            'speech_engine': self.speech_engine,
            'whisper_model': self.whisper_model,
            'shortcuts': self.shortcuts
        }
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
            logger.info(f"Configuration saved to {self.config_file}")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
    
    # Mouse movement methods
    def move_right(self):
        self.mouse.move(self.move_distance, 0)
        return "Moving cursor right"
        
    def move_left(self):
        self.mouse.move(-self.move_distance, 0)
        return "Moving cursor left"
        
    def move_up(self):
        self.mouse.move(0, -self.move_distance)
        return "Moving cursor up"
        
    def move_down(self):
        self.mouse.move(0, self.move_distance)
        return "Moving cursor down"
    
    # Click methods
    def press_enter(self):
        self.keyboard.press(Key.enter)
        self.keyboard.release(Key.enter)
        return "Pressing Enter key"
        
    def left_click(self):
        self.mouse.click(Button.left)
        return "Left clicking"
        
    def right_click(self):
        self.mouse.click(Button.right)
        return "Right clicking"
        
    def double_click(self):
        self.mouse.click(Button.left)
        self.mouse.click(Button.left)
        return "Double clicking"
    
    # Program control
    def exit_program(self):
        return "exit"
    
    # Add browser command capabilities (to be implemented)
    def open_new_tab(self):
        pyautogui.hotkey('command', 't')  # For Mac
        # pyautogui.hotkey('ctrl', 't')  # For Windows/Linux
        return "Opening new tab"
    
    def close_tab(self):
        pyautogui.hotkey('command', 'w')  # For Mac
        # pyautogui.hotkey('ctrl', 'w')  # For Windows/Linux
        return "Closing tab"
    
    def open_incognito(self):
        pyautogui.hotkey('command', 'shift', 'n')  # For Mac Chrome
        # pyautogui.hotkey('ctrl', 'shift', 'n')  # For Windows/Linux Chrome
        return "Opening incognito window"
    
    def navigate_to_website(self, url):
        # Open a new tab and navigate to URL
        self.open_new_tab()
        time.sleep(0.5)
        pyautogui.write(url)
        self.keyboard.press(Key.enter)
        self.keyboard.release(Key.enter)
        return f"Navigating to {url}"
    
    def recognize_with_google(self, audio):
        """Recognize speech using Google Speech Recognition"""
        try:
            text = self.recognizer.recognize_google(audio).lower()
            logger.info(f"Google recognized: '{text}'")
            return text
        except sr.UnknownValueError:
            logger.warning("Google could not understand audio")
        except sr.RequestError as e:
            logger.error(f"Google request error: {e}")
        return None
    
    def recognize_with_whisper(self, audio):
        """Recognize speech using OpenAI's Whisper"""
        try:
            # Save audio to a temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_filename = f.name
                
            with open(temp_filename, "wb") as f:
                f.write(audio.get_wav_data())
            
            # Use Whisper model for transcription
            import whisper
            model = whisper.load_model(self.whisper_model)
            result = model.transcribe(temp_filename)
            text = result["text"].lower().strip()
            
            # Clean up temporary file
            os.unlink(temp_filename)
            
            logger.info(f"Whisper recognized: '{text}'")
            return text
        except Exception as e:
            logger.error(f"Whisper error: {e}")
            # Fall back to Google if Whisper fails
            logger.info("Falling back to Google recognition")
            return self.recognize_with_google(audio)
    
    def recognize_with_sphinx(self, audio):
        """Recognize speech using CMU Sphinx (offline)"""
        try:
            text = self.recognizer.recognize_sphinx(audio).lower()
            logger.info(f"Sphinx recognized: '{text}'")
            return text
        except sr.UnknownValueError:
            logger.warning("Sphinx could not understand audio")
        except sr.RequestError as e:
            logger.error(f"Sphinx error: {e}")
        return None
    
    def listen_for_command(self):
        """Listen for voice commands and return recognized text"""
        with sr.Microphone() as source:
            print("Listening for commands...")
            self.recognizer.adjust_for_ambient_noise(source)
            try:
                audio = self.recognizer.listen(source, timeout=self.command_timeout)
            except sr.WaitTimeoutError:
                logger.info("No speech detected within timeout")
                return None
        
        # Choose recognition engine based on configuration
        if self.speech_engine == "whisper":
            return self.recognize_with_whisper(audio)
        elif self.speech_engine == "sphinx":
            return self.recognize_with_sphinx(audio)
        else:  # Default to Google
            return self.recognize_with_google(audio)
    
    def execute_command(self, command):
        """Execute the given voice command"""
        if not command:
            return True
        
        logger.info(f"Executing command: '{command}'")
        
        # Check for direct commands
        if command in self.commands:
            result = self.commands[command]()
            if result == "exit":
                return False
            logger.info(result)
            print(result)
            return True
        
        # Check for commands that contain keywords
        for cmd, func in self.commands.items():
            if cmd in command:
                result = func()
                if result == "exit":
                    return False
                logger.info(result)
                print(result)
                return True
        
        # Check for website shortcuts
        for shortcut, url in self.shortcuts.items():
            if f"go to {shortcut}" in command:
                result = self.navigate_to_website(url)
                logger.info(result)
                print(result)
                return True
        
        # Browser commands
        if "open new tab" in command:
            result = self.open_new_tab()
            logger.info(result)
            print(result)
            return True
        elif "close this tab" in command or "close tab" in command:
            result = self.close_tab()
            logger.info(result)
            print(result)
            return True
        elif "open incognito" in command or "open an incognito window" in command:
            result = self.open_incognito()
            logger.info(result)
            print(result)
            return True
        
        logger.warning(f"Command not recognized: '{command}'")
        print("Command not recognized")
        return True
    
    def add_shortcut(self, name, url):
        """Add a new website shortcut"""
        self.shortcuts[name] = url
        self.save_config()
        logger.info(f"Added shortcut: {name} -> {url}")
        print(f"Added shortcut: {name} -> {url}")
    
    def set_speech_engine(self, engine_name, whisper_model=None):
        """Set the speech recognition engine"""
        if engine_name in ["google", "whisper", "sphinx"]:
            self.speech_engine = engine_name
            if whisper_model and engine_name == "whisper":
                self.whisper_model = whisper_model
            self.save_config()
            self._check_required_packages()
            logger.info(f"Speech engine set to {engine_name}")
            if engine_name == "whisper":
                logger.info(f"Whisper model set to {self.whisper_model}")
            return True
        return False
    
    def run(self):
        """Run the voice control system"""
        print("Voice Control System starting...")
        print(f"Using {self.speech_engine} speech recognition engine")
        if self.speech_engine == "whisper":
            print(f"Whisper model: {self.whisper_model}")
            
        print("Available commands:")
        print("  - 'Move cursor right/left/up/down'")
        print("  - 'Click' (presses Enter key)")
        print("  - 'Left click'")
        print("  - 'Right click'")
        print("  - 'Double click'")
        print("  - 'Open new tab'")
        print("  - 'Close this tab'")
        print("  - 'Open an incognito window'")
        
        if self.shortcuts:
            print("Website shortcuts:")
            for name, url in self.shortcuts.items():
                print(f"  - 'Go to {name}' -> {url}")
        
        print("  - 'Exit/Quit/Stop'")
        
        logger.info("Voice control system started")
        
        running = True
        while running:
            command = self.listen_for_command()
            running = self.execute_command(command)
        
        logger.info("Voice control system stopped")

if __name__ == "__main__":
    try:
        voice_control = VoiceControl()
        
        # Example of setting a different speech engine
        # voice_control.set_speech_engine("whisper", "base")
        
        voice_control.run()
    except KeyboardInterrupt:
        logger.info("Program terminated by user")
        print("\nProgram terminated by user")
        sys.exit(0) 