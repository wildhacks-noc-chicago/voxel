import datetime
import json
import logging
import os
import queue
import sys
import threading
import time

import google.generativeai as genai
import speech_recognition as sr
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

class MultiEngineSpeechRecognition:
    """Handles speech recognition using multiple engines in parallel"""
    
    def __init__(self, recognizer, command_timeout=5):
        self.recognizer = recognizer
        self.command_timeout = command_timeout
        self.results_queue = queue.Queue()
        
        # Check which engines are available
        self.engines_available = {
            "google": True,  # Google is always available through the API
            "sphinx": self._check_sphinx_available(),
            "vosk": self._check_vosk_available()
        }
        
        logger.info(f"Available engines: Google:{self.engines_available['google']}, "
                   f"Sphinx:{self.engines_available['sphinx']}, "
                   f"Vosk:{self.engines_available['vosk']}")
    
    def _check_sphinx_available(self):
        """Check if Sphinx is available"""
        try:
            import pocketsphinx
            return True
        except ImportError:
            logger.warning("PocketSphinx not found. Sphinx recognition will be skipped.")
            return False
    
    def _check_vosk_available(self):
        """Check if Vosk is available"""
        try:
            import vosk
            return True
        except ImportError:
            logger.warning("Vosk not found. Vosk recognition will be skipped.")
            return False
    
    def recognize_with_google(self, audio):
        """Recognize speech using Google Speech Recognition"""
        try:
            start_time = time.time()
            text = self.recognizer.recognize_google(audio).lower()
            end_time = time.time()
            processing_time = end_time - start_time
            
            logger.info(f"Google recognized: '{text}' in {processing_time:.2f} seconds")
            
            self.results_queue.put({
                "engine": "google",
                "text": text,
                "time": processing_time
            })
        except sr.UnknownValueError:
            logger.warning("Google could not understand audio")
            self.results_queue.put({
                "engine": "google",
                "text": None,
                "time": 0
            })
        except sr.RequestError as e:
            logger.error(f"Google request error: {e}")
            self.results_queue.put({
                "engine": "google",
                "text": None,
                "time": 0
            })
    
    def recognize_with_sphinx(self, audio):
        """Recognize speech using CMU Sphinx"""
        if not self.engines_available["sphinx"]:
            self.results_queue.put({
                "engine": "sphinx",
                "text": None,
                "time": 0
            })
            return
            
        try:
            start_time = time.time()
            text = self.recognizer.recognize_sphinx(audio).lower()
            end_time = time.time()
            processing_time = end_time - start_time
            
            logger.info(f"Sphinx recognized: '{text}' in {processing_time:.2f} seconds")
            
            self.results_queue.put({
                "engine": "sphinx",
                "text": text,
                "time": processing_time
            })
        except sr.UnknownValueError:
            logger.warning("Sphinx could not understand audio")
            self.results_queue.put({
                "engine": "sphinx",
                "text": None,
                "time": 0
            })
        except sr.RequestError as e:
            logger.error(f"Sphinx error: {e}")
            self.results_queue.put({
                "engine": "sphinx",
                "text": None,
                "time": 0
            })
    
    def recognize_with_vosk(self, audio):
        """Recognize speech using Vosk"""
        if not self.engines_available["vosk"]:
            self.results_queue.put({
                "engine": "vosk",
                "text": None,
                "time": 0
            })
            return
            
        try:
            import json

            # Save audio to a temporary file
            import tempfile

            import vosk
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_filename = f.name
                
            with open(temp_filename, "wb") as f:
                f.write(audio.get_wav_data())
                
            # Use Vosk for recognition
            start_time = time.time()
            
            # Load model if not loaded already
            if not hasattr(self, 'vosk_model'):
                model_path = "vosk-model-small-en-us-0.15"
                if not os.path.exists(model_path):
                    try:
                        logger.info("Downloading Vosk model...")
                        import urllib.request
                        urllib.request.urlretrieve(
                            "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
                            "vosk-model-small-en-us-0.15.zip"
                        )
                        import zipfile
                        with zipfile.ZipFile("vosk-model-small-en-us-0.15.zip", 'r') as zip_ref:
                            zip_ref.extractall(".")
                    except Exception as e:
                        logger.error(f"Failed to download Vosk model: {e}")
                        self.results_queue.put({
                            "engine": "vosk",
                            "text": None,
                            "time": 0
                        })
                        return
                self.vosk_model = vosk.Model(model_path)
                
            # Process audio file
            import wave
            wf = wave.open(temp_filename, "rb")
            rec = vosk.KaldiRecognizer(self.vosk_model, wf.getframerate())
            
            result = ""
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if rec.AcceptWaveform(data):
                    result_json = json.loads(rec.Result())
                    if 'text' in result_json:
                        result += result_json['text'] + " "
            
            # Get final result
            final_result = json.loads(rec.FinalResult())
            if 'text' in final_result:
                result += final_result['text']
                
            wf.close()
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Clean up temporary file
            os.unlink(temp_filename)
            
            text = result.lower().strip()
            
            logger.info(f"Vosk recognized: '{text}' in {processing_time:.2f} seconds")
            
            self.results_queue.put({
                "engine": "vosk",
                "text": text,
                "time": processing_time
            })
        except Exception as e:
            logger.error(f"Vosk error: {e}")
            self.results_queue.put({
                "engine": "vosk",
                "text": None,
                "time": 0
            })
    
    def listen_and_recognize(self):
        """Listen for voice input and recognize using multiple engines"""
        with sr.Microphone() as source:
            print("Listening...")
            self.recognizer.adjust_for_ambient_noise(source)
            try:
                audio = self.recognizer.listen(source, timeout=self.command_timeout)
                logger.info("Audio captured, processing with multiple engines...")
            except sr.WaitTimeoutError:
                logger.info("No speech detected within timeout")
                return None
        
        # Clear the results queue
        while not self.results_queue.empty():
            self.results_queue.get()
        
        # Start recognition threads for each engine
        threads = []
        
        # Always use Google
        t_google = threading.Thread(target=self.recognize_with_google, args=(audio,))
        threads.append(t_google)
        
        # Use Sphinx if available
        if self.engines_available["sphinx"]:
            t_sphinx = threading.Thread(target=self.recognize_with_sphinx, args=(audio,))
            threads.append(t_sphinx)
        
        # Use Vosk if available
        if self.engines_available["vosk"]:
            t_vosk = threading.Thread(target=self.recognize_with_vosk, args=(audio,))
            threads.append(t_vosk)
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
        
        # Collect results
        results = []
        while not self.results_queue.empty():
            results.append(self.results_queue.get())
        
        # Print all recognition results
        print("\nRecognition results:")
        for result in results:
            if result["text"]:
                print(f"{result['engine'].capitalize()}: '{result['text']}'")
            else:
                print(f"{result['engine'].capitalize()}: No result")
        
        return results


class GeminiIntentMapper:
    """Maps user speech to commands using Gemini AI with multiple recognition inputs"""
    
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
    
    def map_multi_engine_intent(self, recognition_results):
        """Map multiple recognition results to a command using Gemini AI"""
        if not recognition_results:
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
        
        # Build a string of recognition results
        recognition_results_str = ""
        for result in recognition_results:
            if result["text"]:
                recognition_results_str += f"{result['engine'].capitalize()}: '{result['text']}'\n"
        
        # Create the prompt for Gemini
        prompt = f"""
        Task: You are a voice command interpreter for a computer control system. You will be fed a list of recognisied voice commands from different voice recognition engines.
        If any of the voice commands, have a keyword from the list fed to you below, just map to that command. Otherwise, if there are multiple matches,
        do a simple voting system to determine the best match.
        
        Available keyword to command mapping:
        {commands_json}
        
        Speech recognition engine results:
        {recognition_results_str}
        
        Guidelines:
        1. Your task is to analyze all transcriptions from different engines and identify the most likely command.
        2. Different engines may have different errors or misinterpretations.
        3. Match to the closest available command from the list based on all the keywords from the different engines.
        4. Understand variations and natural language. For example, "move right" should match to "move cursor right".
        5. Return ONLY the exact command string as listed in the available commands.
        6. Do not add any explanations, formatting, or extra text in your response.{history_context}
        
        Your response (exact command string only):
        """
        
        logger.info(f"Sending request to Gemini API for multi-engine recognition")
        
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
            matched_command = matched_command.strip('"\'`')  # Remove quotes if present
            logger.info(f"Gemini matched multi-engine results to '{matched_command}'")
            
            # Handle unknown response
            if matched_command.lower() == "unknown":
                logger.info("Gemini returned 'unknown' match")
                # Use the Google result as fallback
                for result in recognition_results:
                    if result["engine"] == "google" and result["text"]:
                        return result["text"]
                # Or the first available result
                for result in recognition_results:
                    if result["text"]:
                        return result["text"]
                return None
            
            # Check if this is in our available commands
            if matched_command in self.available_commands:
                # Update command history
                self.command_history.insert(0, matched_command)
                if len(self.command_history) > self.max_history_size:
                    self.command_history.pop()
                return matched_command
            else:
                logger.warning(f"Gemini returned '{matched_command}' which is not in available commands")
                # Use the Google result as fallback
                for result in recognition_results:
                    if result["engine"] == "google" and result["text"]:
                        return result["text"]
                # Or the first available result
                for result in recognition_results:
                    if result["text"]:
                        return result["text"]
                return None
                
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            print(f"Error calling Gemini API: {e}")
            
            # Fallback to the Google result
            for result in recognition_results:
                if result["engine"] == "google" and result["text"]:
                    return result["text"]
            # Or the first available result
            for result in recognition_results:
                if result["text"]:
                    return result["text"]
            return None
    
    def _create_command_descriptions(self):
        """Create descriptive explanations for each command"""
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



class MultiEngineVoiceControl:
    """Main class for voice control using multiple speech recognition engines"""
    
    def __init__(self, config_file="voice_config.json", log_file="multi_voice_logs.txt"):
        # Load environment variables
        load_env_file()
        
        # Initialize base voice control (used for command execution)
        self.voice_control = VoiceControl(config_file)
        
        # Set up logging
        self.log_file = log_file
        
        # Get API key for Gemini
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            logger.error("No Gemini API key found. Please add GEMINI_API_KEY to your .env file.")
            print("Error: No Gemini API key found. Please add GEMINI_API_KEY to your .env file.")
            sys.exit(1)
        
        # Initialize multi-engine speech recognition
        self.speech_module = MultiEngineSpeechRecognition(
            sr.Recognizer(),
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
            logger.info("Multi-engine voice control initialized with Gemini")
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
        
        # STEP 3: Execute the command using voice_control.py
        should_continue = self.voice_control.execute_command(interpreted_command)
        
        return interpreted_command, should_continue
    
    def run(self):
        """Run the multi-engine voice control system"""
        print("Multi-Engine Voice Control System")
        print("================================")
        print("This system uses multiple speech recognition engines in parallel:")
        
        # Show which engines are available
        print("- Google (online)")
        if self.speech_module.engines_available["sphinx"]:
            print("- CMU Sphinx (offline)")
        if self.speech_module.engines_available["vosk"]:
            print("- Vosk (offline)")
            
        print("\nAll recognition results are fed to Gemini AI for better command interpretation.")
        print("You can speak naturally to control your computer.")
        
        print("\nExamples:")
        print("  - 'Move the cursor to the right' or 'Go right'")
        print("  - 'Click here' or 'Select this'")
        print("  - 'Open a new tab' or 'Create tab'")
        print("  - 'Close the program' or 'Exit'")
        
        if self.voice_control.shortcuts:
            print("\nCan navigate to these websites:")
            for name in self.voice_control.shortcuts.keys():
                print(f"  - '{name}' (say 'go to {name}' or 'open {name}')")
        
        print("\nLogs will be saved to:")
        print(f"- Command logs: {self.log_file}")
        print(f"- Speech recognition logs: speech_recognition.log")
        
        logger.info("Multi-engine voice control system started")
        
        running = True
        while running:
            _, running = self.process_voice_command()
            
        logger.info("Multi-engine voice control system stopped")


if __name__ == "__main__":
    try:
        voice_control = MultiEngineVoiceControl()
        voice_control.run()
    except KeyboardInterrupt:
        logger.info("Program terminated by user")
        print("\nProgram terminated by user")
        sys.exit(0) 