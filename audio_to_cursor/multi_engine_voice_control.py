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
from pyautogui_command_executor import PyAutoGUICommandExecutor
from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='multi_engine_voice_control.log'
)
logger = logging.getLogger("MultiEngineVoiceControl")

# Try to import PyAutoGUI command executor
try:
    pyautogui_available = True
    logger.info("PyAutoGUI command executor imported successfully")
except ImportError:
    pyautogui_available = False
    logger.warning("PyAutoGUI command executor not available. Will use fallback methods.")

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
        Task: You are a voice command interpreter for a computer control system. Map speech recognition results to the correct command.
        
        Available commands:
        {commands_json}
        
        Speech recognition results from multiple engines:
        {recognition_results_str}

        RULES (in priority order):
        1. If ANY recognition engine exactly matches a command from the available commands list, use that command.
        2. If ANY recognition engine's result is within 1-2 characters of a command (like "clik" vs "click"), use the command.
        3. Only if no match is found, look for semantic matches or substrings.
        
        Examples:
        - If engines recognized: ["clip", "click", null] → return "click" (exact match to available command)
        - If engines recognized: ["write", "right", "rite"] → return "right" (exact match to available command)
        - If engines recognized: ["moved own", "move down", null] → return "down" (semantic match to command)
        
        IMPORTANT: If multiple engines recognized valid commands, prioritize the exact matches in the available commands list.
        
        Return ONLY the exact command string from the available commands list. Return nothing if no match can be made.
        
        Command:
        """
        #random comment
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
            
            # Handle empty or unknown responses
            if not matched_command or matched_command.lower() in ["unknown", "none", "n/a", ""]:
                logger.info("Gemini returned no valid match")
                # Try direct exact matching as fallback
                for result in recognition_results:
                    if result["text"] and result["text"] in self.available_commands:
                        logger.info(f"Direct matching found command: {result['text']}")
                        return result["text"]
                
                # If no direct match, try the closest match with edit distance
                closest_command = self._find_closest_command(recognition_results)
                if closest_command:
                    logger.info(f"Found closest command match: {closest_command}")
                    return closest_command
                    
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
                # Try direct exact matching as fallback
                for result in recognition_results:
                    if result["text"] and result["text"] in self.available_commands:
                        logger.info(f"Direct matching found command: {result['text']}")
                        return result["text"]
                
                # If no direct match, try the closest match with edit distance
                closest_command = self._find_closest_command(recognition_results)
                if closest_command:
                    logger.info(f"Found closest command match: {closest_command}")
                    return closest_command
                
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
            # Mouse movement commands
            "right": "move cursor right",
            "left": "move cursor left",
            "up": "move cursor up",
            "down": "move cursor down",
            
            # Mouse click commands
            "click": "click the mouse",
            "enter": "click the mouse",
            "left click": "left click the mouse",
            "right click": "right click the mouse",
            
            # Exit commands
            "exit": "exit the program",
            "quit": "quit the program",
            "stop listening": "stop the program",

            # Browser commands
            "open browser": "open the browser",
            "start typing": "start typing in the browser",
            "stop typing": "stop typing in the browser",
            
            # Website shortcuts
            **{f"go to {site}": f"Navigate to the {site} website" for site in self.shortcuts.keys()}
        }

    def _find_closest_command(self, recognition_results):
        """Find the closest command match using edit distance"""
        best_command = None
        min_distance = float('inf')
        
        # For each recognition result
        for result in recognition_results:
            if not result["text"]:
                continue
                
            # Find the closest command from available commands
            input_text = result["text"].lower()
            for cmd in self.available_commands:
                cmd_lower = cmd.lower()
                distance = self._levenshtein_distance(input_text, cmd_lower)
                
                # Only consider close matches (<=2 edits)
                if distance <= 2 and distance < min_distance:
                    min_distance = distance
                    best_command = cmd
        
        return best_command
    
    def _levenshtein_distance(self, s1, s2):
        """Calculate the Levenshtein edit distance between two strings"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
            
        if len(s2) == 0:
            return len(s1)
            
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
            
        return previous_row[-1]


class MultiEngineVoiceControl:
    """Main class for voice control using multiple speech recognition engines"""
    
    def __init__(self, config_file="voice_config.json", log_file="multi_voice_logs.txt", move_distance=100):
        # Load environment variables
        load_env_file()
        
        # Set up logging
        self.log_file = log_file
        
        # Check if PyAutoGUI command executor is available
        self.pyautogui_executor = None
        if pyautogui_available:
            try:
                self.pyautogui_executor = PyAutoGUICommandExecutor(move_distance=move_distance)
                logger.info("PyAutoGUI command executor initialized")
            except Exception as e:
                logger.error(f"Failed to initialize PyAutoGUI command executor: {e}")
                print(f"Warning: Failed to initialize PyAutoGUI command executor: {e}")
                print("Falling back to pynput for mouse and keyboard control.")
        
    
                
        # Get API key for Gemini
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            logger.error("No Gemini API key found. Please add GEMINI_API_KEY to your .env file.")
            print("Error: No Gemini API key found. Please add GEMINI_API_KEY to your .env file.")
            sys.exit(1)
        
        # Initialize multi-engine speech recognition
        command_timeout = 10  # Default timeout
        if hasattr(self, 'voice_control') and hasattr(self.voice_control, 'command_timeout'):
            command_timeout = self.voice_control.command_timeout
            
        self.speech_module = MultiEngineSpeechRecognition(
            sr.Recognizer(),
            command_timeout=command_timeout
        )
        
        # Get all available commands
        if self.pyautogui_executor:
            self.available_commands = list(self.pyautogui_executor.commands.keys())
            self.shortcuts = {}  # No shortcuts with PyAutoGUI for now
        else:
            self.available_commands = list(self.voice_control.commands.keys()) + [
                "open new tab", 
                "close this tab", 
                "open an incognito window"
            ]
            self.shortcuts = self.voice_control.shortcuts
        
        # Initialize Gemini intent mapper
        try:
            self.intent_mapper = GeminiIntentMapper(
                self.api_key,
                self.available_commands,
                self.shortcuts
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
            print("No speech detected or timeout occurred.")
            return None, True
        
        # Print what was recognized by each engine
        print("\nRecognition results:")
        for result in recognition_results:
            if result["text"]:
                print(f"  {result['engine'].capitalize()}: '{result['text']}'")
            else:
                print(f"  {result['engine'].capitalize()}: No result")
        
        # STEP 2: Check for direct matches first (optimization)
        for result in recognition_results:
            if result["text"] and result["text"].lower() in [cmd.lower() for cmd in self.available_commands]:
                interpreted_command = next(cmd for cmd in self.available_commands if cmd.lower() == result["text"].lower())
                print(f"\n✅ Direct match found: '{interpreted_command}'")
                
                # Log the command
                self.log_command(recognition_results, interpreted_command)
                
                # Execute the command
                if self.pyautogui_executor:
                    should_continue = self.pyautogui_executor.execute_command(interpreted_command)
                else:
                    should_continue = self.voice_control.execute_command(interpreted_command)
                
                return interpreted_command, should_continue
        
        # STEP 3: Intent mapping with Gemini for more complex cases
        print("\nProcessing with AI interpretation...")
        interpreted_command = self.intent_mapper.map_multi_engine_intent(recognition_results)
        
        if not interpreted_command:
            print("❌ Could not interpret the command. Try again with a clearer command.")
            return None, True
        
        # Log the command and interpretation
        self.log_command(recognition_results, interpreted_command)
        
        # Show final interpretation
        print(f"\n🎯 Final interpretation: '{interpreted_command}'")
        
        # STEP 4: Execute the command
        print(f"Executing: '{interpreted_command}'")
        if self.pyautogui_executor:
            # Use PyAutoGUI command executor if available
            should_continue = self.pyautogui_executor.execute_command(interpreted_command)
        else:
            # Fall back to traditional voice control
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
        
        # Show command execution method
        if self.pyautogui_executor:
            print("\nUsing PyAutoGUI for mouse and keyboard control.")
        else:
            print("\nUsing pynput for mouse and keyboard control.")
        
        print("\nAvailable commands:")
        # Group commands by category for better readability
        command_categories = {
            "Mouse Movement": ["right", "left", "up", "down"],
            "Mouse Actions": ["click", "left click", "right click"],
            "System": ["exit", "quit", "stop listening"]
        }
        
        for category, cmds in command_categories.items():
            matching_cmds = [cmd for cmd in cmds if cmd in self.available_commands]
            if matching_cmds:
                print(f"  {category}:")
                for cmd in matching_cmds:
                    print(f"    - '{cmd}'")
        
        # Show website shortcuts if any
        if self.shortcuts:
            print("\nCan navigate to these websites:")
            for name in self.shortcuts.keys():
                print(f"  - '{name}' (say 'go to {name}' or 'open {name}')")
        
        print("\nLogs will be saved to:")
        print(f"- Command logs: {self.log_file}")
        print(f"- Speech recognition logs: speech_recognition.log")
        if self.pyautogui_executor:
            print(f"- PyAutoGUI logs: pyautogui_commands.log")
        
        logger.info("Multi-engine voice control system started")
        
        running = True
        while running:
            _, running = self.process_voice_command()
            
        logger.info("Multi-engine voice control system stopped")


if __name__ == "__main__":
    try:
        voice_control = MultiEngineVoiceControl(move_distance=100)
        voice_control.run()
    except KeyboardInterrupt:
        logger.info("Program terminated by user")
        print("\nProgram terminated by user")
        sys.exit(0) 