import datetime
import json
import logging
import os
import queue
import sys
import threading
import time

import google.generativeai as genai
import numpy as np
import speech_recognition as sr
from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController

# from audio_to_cursor.calibration import (
#     CalibrationError,
#     CalibrationManager,
#     NoiseFilter,
# )
from audio_to_cursor.pyautogui_command_executor import PyAutoGUICommandExecutor

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
    
    def __init__(self, recognizer, command_timeout=5): # use_old_calibration=False
        self.recognizer = recognizer
        self.command_timeout = command_timeout
        self.results_queue = queue.Queue()
        # self.use_old_calibration = use_old_calibration

        # Initialize calibration
        # self.calibration_manager = CalibrationManager()
        # self.noise_filter = NoiseFilter(self.calibration_manager)
        
        # Check which engines are available
        self.engines_available = {
            "google": True,  # Google is always available through the API
            "vosk": self._check_vosk_available(),
            "faster_whisper": self._check_faster_whisper_available()
        }
        
        logger.info(f"Available engines: Google:{self.engines_available['google']}, "
                   f"Vosk:{self.engines_available['vosk']}, "
                   f"Faster Whisper:{self.engines_available['faster_whisper']}")
        
        # Handle initial calibration
        # self.initialize_calibration()

    # def initialize_calibration(self):
    #     """Initialize calibration once during startup"""
    #     calibration_exists = os.path.exists(self.calibration_manager.calibration_file)
    #     logger.info(f"Calibration file exists: {calibration_exists}, use_old_calibration: {self.use_old_calibration}")
        
    #     if calibration_exists and self.use_old_calibration:
    #         print("\nUsing existing calibration...")
    #         if self.noise_filter.load_noise_profile():
    #             logger.info("Successfully loaded existing calibration")
    #             return True
    #         else:
    #             logger.warning("Failed to load existing calibration, running new calibration...")
    #             return self._run_calibration()
    #     else:
    #         if calibration_exists:
    #             logger.info("Calibration exists but use_old_calibration is False, running new calibration...")
    #         else:
    #             logger.info("No calibration found, running new calibration...")
    #         return self._run_calibration()

    # def _run_calibration(self):
    #     """Run the calibration process"""
    #     try:
    #         logger.info("Starting calibration process...")
    #         if not self.calibration_manager.calibrate():
    #             logger.warning("Calibration failed. Voice recognition may be less accurate.")
    #             return False
    #         logger.info("Calibration completed successfully")
    #         return True
    #     except Exception as e:
    #         logger.error(f"Calibration error: {e}")
    #         return False

    
    def _check_vosk_available(self):
        """Check if Vosk is available"""
        try:
            import vosk
            return True
        except ImportError:
            logger.warning("Vosk not found. Vosk recognition will be skipped.")
            return False
    
    def _check_faster_whisper_available(self):
        """Check if Faster Whisper is available"""
        try:
            from faster_whisper import WhisperModel
            return True
        except ImportError:
            logger.warning("Faster Whisper not found. Faster Whisper recognition will be skipped.")
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
    
    def recognize_with_faster_whisper(self, audio):
        """Recognize speech using Faster Whisper"""
        if not self.engines_available["faster_whisper"]:
            self.results_queue.put({
                "engine": "faster_whisper",
                "text": None,
                "time": 0
            })
            return
            
        try:
            import tempfile

            from faster_whisper import WhisperModel

            # Save audio to a temporary WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_filename = f.name
                
            with open(temp_filename, "wb") as f:
                f.write(audio.get_wav_data())
                
            # Initialize Faster Whisper model if not already loaded
            start_time = time.time()
            
            if not hasattr(self, 'whisper_model'):
                # Use "small" model by default for a good balance of speed and accuracy
                # Can be "tiny", "base", "small", "medium", "large-v1", "large-v2", or "large-v3"
                model_size = "small"
                logger.info(f"Loading Faster Whisper model ({model_size})...")
                
                # Use CPU with 4 threads by default
                # For GPU, set compute_type="float16" and device="cuda"
                self.whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8", 
                                              cpu_threads=4, download_root="./whisper_models")
            
            # Transcribe audio
            segments, info = self.whisper_model.transcribe(temp_filename, beam_size=5)
            
            # Combine all segments
            text = " ".join([segment.text for segment in segments]).strip().lower()
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Clean up temporary file
            os.unlink(temp_filename)
            
            logger.info(f"Faster Whisper recognized: '{text}' in {processing_time:.2f} seconds")
            
            self.results_queue.put({
                "engine": "faster_whisper",
                "text": text,
                "time": processing_time
            })
        except Exception as e:
            logger.error(f"Faster Whisper error: {e}")
            self.results_queue.put({
                "engine": "faster_whisper",
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

                # # Apply noise reduction if calibration exists
                # if self.noise_filter.noise_profile is not None:
                #     try:
                #         # Convert audio to numpy array
                #         audio_data = np.frombuffer(audio.get_raw_data(), dtype=np.int16)
                #         audio_data = audio_data.astype(np.float32) / 32768.0  # Convert to float32

                #         # Apply noise reduction
                #         filtered_audio = self.noise_filter.filter_audio(audio_data)

                #         # Convert back to audio data
                #         filtered_audio = (filtered_audio * 32768.0).astype(np.int16)
                #         audio = sr.AudioData(
                #             filtered_audio.tobytes(),
                #             sample_rate=self.calibration_manager.sample_rate,
                #             sample_width=2  # 16-bit audio
                #         )
                #         logger.info("Applied noise reduction to audio")
                #     except Exception as e:
                #         logger.error(f"Error applying noise reduction: {e}")
                #         # Continue with original audio if noise reduction fails

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
        
        # Use Vosk if available
        if self.engines_available["vosk"]:
            t_vosk = threading.Thread(target=self.recognize_with_vosk, args=(audio,))
            threads.append(t_vosk)
            
        # Use Faster Whisper if available
        if self.engines_available["faster_whisper"]:
            t_whisper = threading.Thread(target=self.recognize_with_faster_whisper, args=(audio,))
            threads.append(t_whisper)
        
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
        
        # Process each recognition result sequentially
        for result in recognition_results:
            if not result["text"]:
                continue
                
            # Direct keyword matching first (fast path)
            if result["text"] in self.available_commands:
                logger.info(f"Direct match found in {result['engine']}: '{result['text']}'")
                self.command_history.insert(0, result["text"])
                if len(self.command_history) > self.max_history_size:
                    self.command_history.pop()
                return result["text"]
                
            # Create the prompt for Gemini with just this one result
            recognition_result_str = f"{result['engine'].capitalize()}: '{result['text']}'"
            
            prompt = f"""
            Task: You are a voice command interpreter for a computer control system. Map the speech recognition result to the correct command.
            
            Available commands:
            {commands_json}
            
            Speech recognition result:
            {recognition_result_str}

            RULES (in priority order):
            1. If the recognition EXACTLY matches a command from the available commands list, use that command.
            2. If the recognition is within 1-2 characters of a command (like "clik" vs "click"), use the command.
            3. Only if no match is found, look for semantic matches or substrings.
            4. Give more priority to commands with lower processing time and clearer recognition (i.e., simpler phrases, high confidence if available).
            5. Match command based on majority of recognition engines. for example, if 2 out of 3 engines recognize "click", then return "click".
        
            Examples:
            - If engines recognized: ["clip", "click", null] → return "click" (exact match to available command)
            - If engines recognized: ["write", "right", "rite"] → return "right" (exact match to available command)
            - If engines recognized: ["moved own", "move down", null] → return "down" (semantic match to command)
            - If engines recognized: ["click", "click", "clique"] → return "click" (majority of engines recognized "click")


            IMPORTANT: If multiple engines recognized valid commands, prioritize the exact matches in the available commands list.
            Return ONLY the exact command string from the available commands list. Return "NO_MATCH" if no match can be made.
            
            Command:
            """
            
            logger.info(f"Sending request to Gemini API for {result['engine']} recognition")
            
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
                logger.info(f"Gemini matched {result['engine']} result to '{matched_command}'")
                
                # Handle empty or unknown responses
                if not matched_command or matched_command.lower() in ["unknown", "none", "n/a", "", "no_match"]:
                    logger.info(f"No match found for {result['engine']} result, trying next engine")
                    continue
                
                # Check if this is in our available commands
                if matched_command in self.available_commands:
                    # Update command history
                    self.command_history.insert(0, matched_command)
                    if len(self.command_history) > self.max_history_size:
                        self.command_history.pop()
                    return matched_command
                else:
                    logger.warning(f"Gemini returned '{matched_command}' which is not in available commands")
                    # Try to find close matches
                    closest_command = self._find_closest_command([result])
                    if closest_command:
                        logger.info(f"Found closest command match: {closest_command}")
                        return closest_command
                    
            except Exception as e:
                logger.error(f"Error calling Gemini API for {result['engine']}: {e}")
                print(f"Error calling Gemini API for {result['engine']}: {e}")
        
        # If we've tried all engines and found no match, try a fallback approach
        logger.info("No matches found from any engine, trying fallback approach")
        
        # Fallback to direct text matching and edit distance
        for result in recognition_results:
            if not result["text"]:
                continue
                
            # Check for direct match again
            if result["text"] in self.available_commands:
                return result["text"]
        
        # If no direct match, try the closest match with edit distance
        closest_command = self._find_closest_command(recognition_results)
        if closest_command:
            logger.info(f"Found closest command match as fallback: {closest_command}")
            return closest_command
                
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
    
    def __init__(self, config_file="voice_config.json", log_file="multi_voice_logs.txt", move_distance=100): # use_old_calibration=False
        # Load environment variables
        load_env_file()
        
        # Set up logging
        self.log_file = log_file

        # Set up logging with path in audio_to_cursor directory
        self.log_file = os.path.join(os.path.dirname(__file__), log_file)
        
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
            command_timeout=command_timeout,
            # use_old_calibration=use_old_calibration
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
        
        # STEP 2: Process each engine sequentially with Gemini
        print("\nProcessing engines sequentially...")
        
        # STEP 3: Intent mapping with Gemini
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
        print("This system uses multiple speech recognition engines sequentially:")
        
        # Show which engines are available
        print("- Google (online)")
        if self.speech_module.engines_available["vosk"]:
            print("- Vosk (offline)")
        if self.speech_module.engines_available["faster_whisper"]:
            print("- Faster Whisper (offline)")
            
        print("\nEach engine's output is processed individually with Gemini AI.")
        print("If a command is found from one engine, we stop processing and execute it immediately.")
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