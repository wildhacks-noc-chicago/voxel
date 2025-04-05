import datetime
import json
import logging
import os
import re
import sys
import time

import google.generativeai as genai
import pyautogui
import speech_recognition as sr
import whisper
from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController

from voice_control import VoiceControl, logger


def load_env_file():
    """Load environment variables from .env file"""
    if os.path.exists('.env'):
        with open('.env', 'r') as file:
            for line in file:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key] = value


class SpeechRecognitionModule:
    """Handles speech recognition functionality"""
    
    def __init__(self, recognizer, speech_engine="google", whisper_model="base", command_timeout=5):
        self.recognizer = recognizer
        self.speech_engine = speech_engine
        self.whisper_model = whisper_model
        self.command_timeout = command_timeout
        
        logger.info(f"Speech recognition module initialized with {speech_engine} engine")
        if speech_engine == "whisper":
            logger.info(f"Using Whisper model: {whisper_model}")
    
    def listen(self):
        """Listen for voice input and convert to text"""
        with sr.Microphone() as source:
            print("Listening for commands...")
            self.recognizer.adjust_for_ambient_noise(source)
            try:
                audio = self.recognizer.listen(source, timeout=self.command_timeout)
                logger.info("Audio captured, processing...")
            except sr.WaitTimeoutError:
                logger.info("No speech detected within timeout")
                return None
        
        # Use the appropriate recognition engine
        if self.speech_engine == "whisper":
            return self._recognize_with_whisper(audio)
        elif self.speech_engine == "sphinx":
            return self._recognize_with_sphinx(audio)
        else:  # Default to Google
            return self._recognize_with_google(audio)
    
    def _recognize_with_google(self, audio):
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
    
    def _recognize_with_whisper(self, audio):
        """Recognize speech using OpenAI's Whisper"""
        try:
            # Save audio to a temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_filename = f.name
                
            with open(temp_filename, "wb") as f:
                f.write(audio.get_wav_data())
            
            # Use Whisper model for transcription
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
            return self._recognize_with_google(audio)
    
    def _recognize_with_sphinx(self, audio):
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


class GeminiIntentMapper:
    """Maps user speech to commands using Gemini AI"""
    
    def __init__(self, api_key, available_commands, shortcuts=None):
        self.api_key = api_key
        self.available_commands = available_commands
        self.shortcuts = shortcuts or {}
        
        # Add website shortcuts to available commands
        for site in self.shortcuts.keys():
            self.available_commands.append(f"go to {site}")
            
        # Command history for context
        self.command_history = []
        self.max_history_size = 5
        
        # Initialize Gemini API
        genai.configure(api_key=self.api_key)
        
        # Set up the model
        try:
            self._setup_model()
            logger.info("Gemini intent mapper initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Gemini intent mapper: {e}")
            raise
    
    def _setup_model(self):
        """Set up the Gemini model"""
        try:
            # List available models first for debugging
            for model in genai.list_models():
                if "gemini" in model.name.lower():
                    logger.info(f"Available Gemini model: {model.name}")
            
            # Try to use an appropriate model
            self.model = genai.GenerativeModel('gemini-2.0-flash')
            logger.info("Successfully initialized Gemini model")
        except Exception as e:
            logger.error(f"Error setting up Gemini model: {e}")
            raise
    
    def map_intent(self, text):
        """Map user speech to an available command using Gemini AI"""
        if not text:
            return None
        
        # Create command descriptions for better matching
        commands_with_descriptions = self._create_command_descriptions()
        
        # Convert to JSON for prompt
        commands_json = json.dumps(commands_with_descriptions)
        
        # Add recent command history for context
        history_context = ""
        if self.command_history:
            history_json = json.dumps(self.command_history)
            history_context = f"\nRecent command history (newest to oldest): {history_json}"
        
        # Create the prompt for Gemini
        prompt = f"""
        Task: You are a voice command interpreter for a computer control system. You will be fed a list of recognisied voice commands from different voice recognition engines.
        If any of the voice commands, have a keyword from the list fed to you below, just map to that command. Otherwise, if there are multiple matches,
        do a simple voting system to determine the best match.
        
        Available commands with descriptions:
        {commands_json}
        
        Guidelines:
        1. Your ONLY task is to identify the closest matching command from the available list based on the user's spoken input.
        2. Understand variations and natural language. For example, "move right" should match to "move cursor right".
        3. Return ONLY the exact command string as listed in the available commands.
        4. If there is no reasonable match, return only the word "unknown".
        5. Do not add any explanations, formatting, or extra text in your response.{history_context}
        
        User's voice input: "{text}"
        
        Your response (exact command string only):
        """
        
        logger.info(f"Sending request to Gemini API for text: '{text}'")
        
        try:
            # Using similar syntax to test.py
            generation_config = {
                "temperature": 0.1,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 32,
            }
            
            # Generate content using the Gemini model
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            # Clean up the response
            matched_command = response.text.strip()
            matched_command = re.sub(r'^["\'`]|["\'`]$', '', matched_command)  # Remove quotes if present
            logger.info(f"Gemini matched '{text}' to '{matched_command}'")
            
            # Handle unknown response
            if matched_command.lower() == "unknown":
                logger.info("Gemini returned 'unknown' match")
                return text
            
            # Check if this is in our available commands
            if matched_command in self.available_commands:
                # Update command history
                self.command_history.insert(0, matched_command)
                if len(self.command_history) > self.max_history_size:
                    self.command_history.pop()
                return matched_command
            else:
                logger.warning(f"Gemini returned '{matched_command}' which is not in available commands")
                return text
                
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            print(f"Error calling Gemini API: {e}")
            return text
    
    def _create_command_descriptions(self):
        """Create keywords to command mapping"""
        return {
            # Mouse commands with descriptions
            "right": "move cursor right",
            "left": "move cursor left",
            "up": "move cursor up",
            "down": "move cursor down",
            "click": "click",
            "enter": "click",
            "left click": "left click",
            "right click": "right click",
            **{f"go to {site}": f"Navigate to the {site} website" for site in self.shortcuts.keys()}
        }


class GeminiVoiceControl:
    """Main class for voice control using Gemini AI for intent mapping"""
    
    def __init__(self, config_file="voice_config.json", log_file="voice_logs.txt", api_key=None):
        # Load environment variables
        load_env_file()
        
        # Initialize base voice control (used for command execution)
        self.voice_control = VoiceControl(config_file)
        
        # Set up logging
        self.log_file = log_file
        
        # Get API key
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            logger.error("No Gemini API key found. Please add GEMINI_API_KEY to your .env file.")
            print("Error: No Gemini API key found. Please add GEMINI_API_KEY to your .env file.")
            sys.exit(1)
        
        # Initialize speech recognition module
        self.speech_module = SpeechRecognitionModule(
            sr.Recognizer(),
            speech_engine=self.voice_control.speech_engine,
            whisper_model=self.voice_control.whisper_model,
            command_timeout=self.voice_control.command_timeout
        )
        
        # Get all available commands
        self.available_commands = list(self.voice_control.commands.keys()) + [
            "open new tab", 
            "close this tab", 
            "open an incognito window"
        ]
        
        # Initialize Gemini intent mapper
        try:
            self.intent_mapper = GeminiIntentMapper(
                self.api_key,
                self.available_commands,
                self.voice_control.shortcuts
            )
            logger.info("Gemini voice control initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini intent mapper: {e}")
            print(f"Error: Failed to initialize Gemini intent mapper: {e}")
            sys.exit(1)
    
    def log_command(self, raw_text, interpreted_command):
        """Log the raw voice command and its interpretation"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.log_file, "a") as f:
                f.write(f"{timestamp} | Raw: '{raw_text}' | Interpreted as: '{interpreted_command}'\n")
            logger.info(f"Command logged: Raw: '{raw_text}' | Interpreted as: '{interpreted_command}'")
        except Exception as e:
            logger.error(f"Error logging command: {e}")
    
    def process_voice_command(self):
        """Process a voice command through the entire pipeline"""
        # STEP 1: Speech recognition
        raw_text = self.speech_module.listen()
        if not raw_text:
            return None, True
        
        logger.info(f"Speech recognized: '{raw_text}'")
        
        # STEP 2: Intent mapping with Gemini
        interpreted_command = self.intent_mapper.map_intent(raw_text)
        
        # Log the command and interpretation
        self.log_command(raw_text, interpreted_command)
        
        # Show interpretation if different from raw text
        if interpreted_command and interpreted_command != raw_text:
            logger.info(f"Interpreted as: '{interpreted_command}'")
            print(f"Interpreted as: '{interpreted_command}'")
        
        # STEP 3: Execute the command using voice_control.py
        should_continue = self.voice_control.execute_command(interpreted_command)
        
        return interpreted_command, should_continue
    
    def run(self):
        """Run the Gemini-powered voice control system"""
        print("Gemini Voice Control System starting...")
        print(f"Using {self.voice_control.speech_engine} speech recognition engine")
        if self.voice_control.speech_engine == "whisper":
            print(f"Whisper model: {self.voice_control.whisper_model}")
            
        print("You can speak naturally to control your computer.")
        print("Examples:")
        print("  - 'Move the cursor to the right' or 'Go right'")
        print("  - 'Click here' or 'Select this'")
        print("  - 'Open a new tab' or 'Create tab'")
        print("  - 'Take me to Google' or 'Open YouTube'")
        print("  - 'Close the program' or 'Exit'")
        
        if self.voice_control.shortcuts:
            print("\nCan navigate to these websites:")
            for name in self.voice_control.shortcuts.keys():
                print(f"  - '{name}' (say 'go to {name}' or 'open {name}')")
        
        print("\nLogs will be saved to:")
        print(f"- Command logs: {self.log_file}")
        print(f"- Speech recognition logs: speech_recognition.log")
        
        logger.info("Gemini voice control system started")
        
        running = True
        while running:
            _, running = self.process_voice_command()
            
        logger.info("Gemini voice control system stopped")


if __name__ == "__main__":
    try:
        voice_control = GeminiVoiceControl()
        
        # Example of setting a different speech engine
        # voice_control.voice_control.set_speech_engine("whisper", "base")
        
        voice_control.run()
    except KeyboardInterrupt:
        logger.info("Program terminated by user")
        print("\nProgram terminated by user")
        sys.exit(0) 