import datetime
import json
import logging
import os
import queue
import sys
import tempfile
import threading
import time
from typing import Dict, List, Optional

import google.generativeai as genai
import numpy as np
import speech_recognition as sr
import vosk
from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController

# from audio_to_cursor.calibration import (
#     CalibrationError,
#     CalibrationManager,
#     NoiseFilter,
# )
from audio_to_cursor.pyautogui_command_executor import (
    MOUSE_LOCKED_STATE,
    PyAutoGUICommandExecutor,
)

# Don't configure logging here - we'll do it in the class
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

MOUSE_LOCKED_STATE = False

class MultiEngineSpeechRecognition:
    """Handles speech recognition using multiple engines in parallel"""
    
    def __init__(self, recognizer, command_timeout=5): # use_old_calibration=False
        self.recognizer = recognizer
        self.command_timeout = command_timeout
        self.results_queue = queue.Queue()
        # self.use_old_calibration = use_old_calibration

        logger.info("Initializing speech recognition with timeout: %s seconds", self.command_timeout)
        
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
            logger.debug("Starting Google speech recognition")
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
        logger.info("Listening for voice command...")
        
        with sr.Microphone() as source:
            print("Listening...")
            logger.debug("Adjusting for ambient noise")
            self.recognizer.adjust_for_ambient_noise(source)
            try:
                logger.debug("Waiting for audio input")
                audio = self.recognizer.listen(source, timeout=self.command_timeout)
                
                # NEW: Quickly check if audio is empty or just background noise
                audio_data = np.frombuffer(audio.get_raw_data(), dtype=np.int16)
                
                # If audio is very short or very quiet, skip further processing
                audio_duration = len(audio_data) / audio.sample_rate
                audio_amplitude = np.abs(audio_data).mean()
                
                logger.debug(f"Audio duration: {audio_duration:.2f}s, amplitude: {audio_amplitude:.2f}")
                
                # Exit early if the audio is too short or too quiet
                if audio_duration < 0.3 or audio_amplitude < 50:
                    logger.info(f"Empty or silent audio detected (duration: {audio_duration:.2f}s, amplitude: {audio_amplitude:.2f}), skipping recognition")
                    print("No speech detected, listening again...")
                    return None
                    
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
        engines_used = []
        
        # Always use Google
        logger.debug("Starting Google recognition thread")
        t_google = threading.Thread(target=self.recognize_with_google, args=(audio,))
        threads.append(t_google)
        engines_used.append("Google")
        
        # Use Vosk if available
        if self.engines_available["vosk"]:
            t_vosk = threading.Thread(target=self.recognize_with_vosk, args=(audio,))
            threads.append(t_vosk)
            engines_used.append("Vosk")
            
        # Use Faster Whisper if available
        if self.engines_available["faster_whisper"]:
            t_whisper = threading.Thread(target=self.recognize_with_faster_whisper, args=(audio,))
            threads.append(t_whisper)
            engines_used.append("Faster Whisper")
        
        # Start all threads
        logger.debug(f"Starting {len(threads)} recognition threads: {', '.join(engines_used)}")
        for t in threads:
            t.start()
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
        
        # Collect results
        results = []
        while not self.results_queue.empty():
            results.append(self.results_queue.get())
        
        logger.info(f"Collected {len(results)} recognition results")
        return results

    def initialize_whisper(self):
        """Initialize Faster Whisper model if available"""
        try:
            # Check if speech_module has already initialized Whisper
            if hasattr(self, 'whisper_model') and self.whisper_model is not None:
                logger.info("Whisper model already initialized")
                return True
                
            # Check if Faster Whisper is available
            if not self.engines_available.get("faster_whisper", False):
                logger.info("Faster Whisper is not available, skipping initialization")
                return False
                
            # Initialize Whisper model
            logger.info("Initializing Faster Whisper model")
            from faster_whisper import WhisperModel

            # Use small model by default (good balance of speed and accuracy)
            model_size = "small"
            logger.info(f"Loading Faster Whisper model ({model_size})...")
            
            # Initialize the model with CPU settings
            self.whisper_model = WhisperModel(
                model_size, 
                device="cpu", 
                compute_type="int8", 
                cpu_threads=4, 
                download_root="./whisper_models"
            )
            
            logger.info("Faster Whisper model initialized successfully")
            return True
        except ImportError:
            logger.warning("Faster Whisper not available - will use other engines")
            return False
        except Exception as e:
            logger.error(f"Error initializing Faster Whisper model: {e}")
            print(f"Warning: Failed to initialize Whisper model: {e}")
            return False

class GeminiIntentMapper:
    """Maps user speech to commands using Gemini AI with multiple recognition inputs"""
    
    def __init__(self, api_key, available_commands, shortcuts=None):
        self.api_key = api_key
        self.available_commands = available_commands
        self.shortcuts = shortcuts or {}
        
        logger.info(f"Initializing GeminiIntentMapper with {len(available_commands)} available commands")
        logger.debug(f"Available commands: {', '.join(available_commands)}")
        
        # Command aliases - multiple ways to say the same command
        self.command_aliases = {
            # Movement commands
            "right": ["move right", "go right", "cursor right", "shift right"],
            "left": ["move left", "go left", "cursor left", "shift left"],
            "up": ["move up", "go up", "cursor up", "shift up"],
            "down": ["move down", "go down", "cursor down", "shift down"],
            
            # Click commands
            "click": ["mouse click", "press click", "do click", "quick click"],
            "left click": ["mouse click", "press click", "left mouse click"],
            "right click": ["right mouse click", "context click", "secondary click"],
            
            # Lock commands
            "lock": ["lock mouse", "freeze mouse", "stop mouse", "lock cursor", "freeze cursor"],
            "unlock": ["unlock mouse", "unfreeze mouse", "free mouse", "unlock cursor", "unfreeze cursor"],
            
            # Typing commands
            "start typing": ["begin typing", "type mode", "typing mode", "dictate text", "dictation mode"],
            "stop typing": ["end typing", "exit typing", "stop dictation", "end dictation", "finish typing"],
            
            # AI editor commands
            "enable AI": ["turn on AI", "activate AI", "AI on", "AI editor on", "enable AI editor", "start AI editor"],
            "disable AI": ["turn off AI", "deactivate AI", "AI off", "AI editor off", "disable AI editor", "stop AI editor"],
            
            # Browser commands
            "open browser": ["launch browser", "start browser", "open web", "launch internet", "web browser"],
            
            # System commands
            "exit": ["close program", "exit program", "quit program", "terminate"],
            "quit": ["exit", "close program", "stop program"],

            # Delete
            "clear text": ["clear text", "clear search bar", "delete text", "erase text", "clear text field", "delete text field", "erase text field"]
        }
        
        # Create reverse alias mapping for lookup
        self.reverse_aliases = {}
        for cmd, aliases in self.command_aliases.items():
            self.reverse_aliases[cmd] = cmd  # Command maps to itself
            for alias in aliases:
                self.reverse_aliases[alias] = cmd
        
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

    def preprocess_text(self, text):
        """Preprocess text to improve command matching"""
        if not text:
            return ""
            
        # Convert to lowercase
        text = text.lower()
        
        # Remove common filler words that might confuse command matching
        filler_words = ["please", "hey", "ok", "okay", "um", "uh", "like", "just", "the", "a", "an"]
        for word in filler_words:
            text = text.replace(f" {word} ", " ")
        
        # Remove punctuation
        for char in ".,;:!?\"'":
            text = text.replace(char, "")
            
        # Normalize spaces
        text = " ".join(text.split())
        
        return text.strip()
    
    def direct_match(self, text):
        """Try to match a command directly including aliases"""
        preprocessed = self.preprocess_text(text)
        
        # Check for exact match with commands
        if preprocessed in self.available_commands:
            return preprocessed
            
        # Check for matches with aliases
        if preprocessed in self.reverse_aliases:
            cmd = self.reverse_aliases[preprocessed]
            if cmd in self.available_commands:
                return cmd
                
        return None
    
    def fuzzy_match(self, text, threshold=0.8):
        """Try to match a command using fuzzy matching with a threshold"""
        preprocessed = self.preprocess_text(text)
        if not preprocessed:
            return None
            
        # Split into words to look for command components
        words = preprocessed.split()
        
        # Check if any words in the input contain commands
        best_match = None
        best_score = 0
        
        # First check command aliases
        for alias, cmd in self.reverse_aliases.items():
            if cmd not in self.available_commands:
                continue
                
            # Use ratio of overlap for multi-word commands
            alias_words = alias.split()
            cmd_words = cmd.split()
            
            # Command in text?
            if alias in preprocessed:
                score = 1.0
            else:
                # Calculate word overlap
                alias_word_count = len(alias_words)
                matching_words = sum(1 for word in alias_words if any(word in input_word for input_word in words))
                score = matching_words / alias_word_count if alias_word_count > 0 else 0
                
                # Boost for commands that are multiple words
                if len(alias_words) > 1 and score > 0:
                    score += 0.1
                    
                # Check for Levenshtein distance for single-word commands
                if len(alias_words) == 1 and len(alias_words[0]) > 2:
                    for word in words:
                        lev_score = 1 - (self._levenshtein_distance(word, alias_words[0]) / max(len(word), len(alias_words[0])))
                        if lev_score > score:
                            score = lev_score
            
            if score > best_score and score >= threshold:
                best_score = score
                best_match = cmd
                
        return best_match
    
    def map_multi_engine_intent(self, recognition_results):
        """Map multiple recognition results to a command using Gemini AI"""
        if not recognition_results:
            logger.warning("No recognition results to process")
            return None
        
        logger.info(f"Processing {len(recognition_results)} recognition results with fast matching methods first")
        
        # STEP 1: Try direct matching (fastest) on all results
        logger.info("Stage 1: Attempting direct matching")
        for result in recognition_results:
            if not result["text"]:
                continue
                
            # Try direct matching (exact match and aliases)
            logger.debug(f"Trying direct match for: '{result['text']}'")
            direct_match = self.direct_match(result["text"])
            if direct_match:
                logger.info(f"Direct match found for '{result['text']}': '{direct_match}'")
                self.command_history.insert(0, direct_match)
                if len(self.command_history) > self.max_history_size:
                    self.command_history.pop()
                return direct_match
        
        # STEP 2: If no direct matches, try fuzzy matching on all results
        logger.info("Stage 2: Attempting fuzzy matching")
        for result in recognition_results:
            if not result["text"]:
                continue
                
            # Try fuzzy matching
            logger.debug(f"Trying fuzzy match for: '{result['text']}'")
            fuzzy_match = self.fuzzy_match(result["text"])
            if fuzzy_match:
                logger.info(f"Fuzzy match found for '{result['text']}': '{fuzzy_match}'")
                self.command_history.insert(0, fuzzy_match)
                if len(self.command_history) > self.max_history_size:
                    self.command_history.pop()
                return fuzzy_match
        
        # STEP 3: If no fuzzy matches, try simple substring matching
        logger.info("Stage 3: Attempting substring matching")
        for result in recognition_results:
            if not result["text"]:
                continue
                
            logger.debug(f"Trying substring match for: '{result['text']}'")
            # Try simple substring matching
            for cmd in self.available_commands:
                if cmd.lower() in result["text"].lower():
                    matched_command = cmd
                    logger.info(f"Substring match found: '{matched_command}' in '{result['text']}'")
                    
                    # Update command history
                    self.command_history.insert(0, matched_command)
                    if len(self.command_history) > self.max_history_size:
                        self.command_history.pop()
                    return matched_command
        
        # STEP 4: If all faster methods fail, try Gemini API as last resort
        logger.info("Stage 4: All fast matching methods failed, attempting Gemini API")
        
        # Create command descriptions for better matching
        commands_with_descriptions = self._create_command_descriptions()
        
        # Convert to JSON for prompt
        commands_json = json.dumps(commands_with_descriptions)
        
        # Add recent command history for context
        history_context = ""
        if self.command_history:
            history_json = json.dumps(self.command_history)
            history_context = f"\nRecent command history (newest to oldest): {history_json}"
        
        # Try each engine one at a time with Gemini
        for result in recognition_results:
            if not result["text"]:
                logger.debug(f"Skipping empty result from {result['engine']}")
                continue
                
            logger.debug(f"Processing result with Gemini from {result['engine']}: '{result['text']}'")
            print(f"Fast matching failed, trying Gemini API with: '{result['text']}'")     
            
            matched_command = self._process_with_gemini(result, commands_json, history_context)
            if matched_command:
                return matched_command
        
        # STEP 5: Final fallback - Levenshtein distance
        logger.info("Stage 5: All methods failed, attempting final Levenshtein fallback")
        
        # If no direct match, try the closest match with edit distance
        closest_command = self._find_closest_command(recognition_results)
        if closest_command:
            logger.info(f"Found closest command match as fallback: {closest_command}")
            return closest_command
                
        return None
    
    def _process_with_gemini(self, result, commands_json, history_context):
        """Process a single recognition result with Gemini API"""
        # Create the prompt for Gemini with just this one result
        recognition_result_str = f"{result['engine'].capitalize()}: '{result['text']}'"
        
        # Include aliases information in the prompt
        aliases_info = {}
        for cmd, aliases in self.command_aliases.items():
            if cmd in self.available_commands:
                aliases_info[cmd] = aliases
                
        aliases_json = json.dumps(aliases_info)
        
        prompt = f"""
        Task: You are a voice command interpreter for a computer control system. Map the speech recognition result to the correct command.
        
        Available commands:
        {commands_json}
        
        Command aliases (alternative ways to say each command):
        {aliases_json}
        
        Speech recognition result:
        {recognition_result_str}

        RULES (in priority order):
        1. If the recognition EXACTLY matches a command from the available commands list, use that command.
        2. If the recognition exactly matches any alias from the command aliases, use the corresponding command.
        3. If the recognition is within 1-2 characters of a command (like "clik" vs "click"), use the command.
        4. If the recognition contains the command as a substring, use the command.
        5. If no exact match is found, look for semantic matches or similar-sounding words.
        6. Give more priority to commands with lower processing time and clearer recognition.
        
        Examples:
        - If engines recognized: ["clip", "click", null] → return "click" (similar to command)
        - If engines recognized: ["write", "right", "rite"] → return "right" (exact match to command)
        - If engines recognized: ["moved own", "move down", null] → return "down" (contains command)
        - If engines recognized: ["click", "click", "clique"] → return "click" (majority of engines recognized)
        - If engines recognized: ["lock the mouse", "lock mouse", null] → return "lock" (matches alias "lock mouse")

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
            logger.debug("Sending prompt to Gemini API")
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            # Clean up the response
            matched_command = response.text.strip()
            matched_command = matched_command.strip('"\'`')  # Remove quotes if present
            logger.info(f"Gemini matched {result['engine']} result to '{matched_command}'")
            
            # Check if it's a valid command
            if matched_command in self.available_commands:
                # Update command history
                self.command_history.insert(0, matched_command)
                if len(self.command_history) > self.max_history_size:
                    self.command_history.pop()
                return matched_command
            
            # Handle empty or unknown responses
            if not matched_command or matched_command.lower() in ["unknown", "none", "n/a", "", "no_match"]:
                logger.info(f"No match found for {result['engine']} result")
                return None
            
            # Try to find close matches if Gemini returned an invalid command
            closest_command = self._find_closest_command([result])
            if closest_command:
                logger.info(f"Found closest command match: {closest_command}")
                return closest_command
                
        except Exception as e:
            logger.error(f"Error calling Gemini API for {result['engine']}: {e}")
            print(f"Error calling Gemini API for {result['engine']}: {e}")
            
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

            # Browser commands
            "open browser": "open the browser",
            "start typing": "start typing in the browser",
            "stop typing": "stop typing in the browser",

            #Lock Commands
            "lock": "lock mouse movement",
            "unlock": "unlock mouse movement",

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
        
        # Set up proper logging
        self.log_file = log_file

        # Make sure the directory exists
        log_dir = os.path.dirname(self.log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        # Configure logging to use the specified file
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            filename=self.log_file,
            filemode='a'  # Append mode
        )
        logger.info(f"Logging configured to write to {os.path.abspath(self.log_file)}")
        
        # Also log to console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        # Print confirmation to stdout
        print(f"Logging to file: {os.path.abspath(self.log_file)}")
        
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
        command_timeout = 5  # Default timeout
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
            
    def cleanup(self):
        """Clean up resources used by the voice control system"""
        logger.info("Cleaning up voice control resources")
        
        try:
            # Clean up speech module resources
            if hasattr(self, 'speech_module'):
                # Clean up Whisper models
                if hasattr(self.speech_module, 'whisper_model'):
                    try:
                        del self.speech_module.whisper_model
                        logger.info("Cleaned up Whisper model")
                    except Exception as e:
                        logger.error(f"Error cleaning up Whisper model: {e}")
                
                # Clean up Vosk models
                if hasattr(self.speech_module, 'vosk_model'):
                    try:
                        del self.speech_module.vosk_model
                        logger.info("Cleaned up Vosk model")
                    except Exception as e:
                        logger.error(f"Error cleaning up Vosk model: {e}")
            
            # Clean up multiprocessing resources
            try:
                import multiprocessing
                multiprocessing.resource_tracker._resource_tracker.clear()
                logger.info("Cleared multiprocessing resource tracker")
            except Exception as e:
                logger.error(f"Error clearing multiprocessing resources: {e}")
                
            # Force Python garbage collection
            import gc
            gc.collect()
            logger.info("Triggered garbage collection")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            
        logger.info("Voice control cleanup completed")
    
    def log_command(self, recognition_results, interpreted_command):
        """Log the recognition results and the final interpretation"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Command logged: Final interpretation: '{interpreted_command}'")
        
        try:
            with open(self.log_file, "a") as f:
                f.write(f"{timestamp} | Multi-Engine Results:\n")
                for result in recognition_results:
                    if result["text"]:
                        f.write(f"  {result['engine'].capitalize()}: '{result['text']}'\n")
                f.write(f"  Final interpretation: '{interpreted_command}'\n\n")
            logger.debug(f"Command details written to {self.log_file}")
        except Exception as e:
            logger.error(f"Error logging command to file: {e}")
    
    def _is_audio_empty(self, audio):
        """Check if audio is empty or contains only background noise"""
        try:
            # Get the raw audio data
            audio_data = np.frombuffer(audio.get_raw_data(), dtype=np.int16)
            
            # Calculate audio duration and amplitude
            audio_duration = len(audio_data) / audio.sample_rate if hasattr(audio, 'sample_rate') else 0.0
            audio_amplitude = np.abs(audio_data).mean()
            
            logger.debug(f"Audio check - Duration: {audio_duration:.2f}s, Amplitude: {audio_amplitude:.2f}")
            
            # Return true if audio is too short or too quiet
            if audio_duration < 0.3 or audio_amplitude < 50:
                logger.info(f"Empty audio detected (duration: {audio_duration:.2f}s, amplitude: {audio_amplitude:.2f})")
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error checking if audio is empty: {e}")
            return False  # Assume not empty on error
            
    def _process_typing_input(self):
        """Process audio input while in typing mode, with early exit for empty audio"""
        # Use only speech recognition for typing mode
        with sr.Microphone() as source:
            logger.info("Listening for text in typing mode...")
            print("Listening for text to type...")
            
            recognizer = sr.Recognizer()
            recognizer.adjust_for_ambient_noise(source)
            
            try:
                # Listen for speech with timeout
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
                
                # Check if audio is empty before processing (early exit)
                if self._is_audio_empty(audio):
                    logger.info("Empty audio detected in typing mode, skipping processing")
                    print("No speech detected, listening again...")
                    return None, True
                
                logger.info("Audio captured in typing mode")
                
                # Process with Faster Whisper if available (more accurate for typing)
                if self.speech_module.engines_available["faster_whisper"]:
                    try:
                        # Initialize whisper model if needed
                        if (not hasattr(self.speech_module, 'whisper_model') 
                                or self.speech_module.whisper_model is None):
                            # Initialize Whisper
                            try:
                                # Initialize directly with same parameters
                                from faster_whisper import WhisperModel
                                model_size = "small"
                                logger.info(f"Initializing Whisper model for typing mode ({model_size})...")
                                self.speech_module.whisper_model = WhisperModel(
                                    model_size, 
                                    device="cpu", 
                                    compute_type="int8", 
                                    cpu_threads=4, 
                                    download_root="./whisper_models"
                                )
                                logger.info("Whisper model initialized for typing mode")
                            except Exception as e:
                                logger.error(f"Error initializing Whisper model for typing mode: {e}")
                                print(f"Error initializing speech recognition: {e}")
                                return None, True
                        
                        # Process with Whisper directly, saving to a temp file
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                            temp_filename = f.name
                            
                        with open(temp_filename, "wb") as f:
                            f.write(audio.get_wav_data())
                        
                        # Use Whisper for transcription
                        segments, info = self.speech_module.whisper_model.transcribe(temp_filename, beam_size=1)
                        text = " ".join([segment.text for segment in segments]).strip()
                        
                        # Clean up the temp file immediately
                        os.unlink(temp_filename)
                        
                        # Check for stop commands
                        if text.lower() in ["stop typing", "stop", "exit typing", "exit typing mode"]:
                            logger.info(f"Stop typing command detected in typing mode: '{text}'")
                            return "stop typing", True
                        
                        # Return the text for typing
                        if text:
                            logger.info(f"Typing mode text recognized: '{text}'")
                            print(f"Typing: '{text}'")
                            return text, True
                        else:
                            logger.info("No text recognized in typing mode")
                            return None, True
                    except Exception as e:
                        logger.error(f"Error using Faster Whisper in typing mode: {e}")
                
                # Fall back to Google if Whisper fails or isn't available
                try:
                    text = recognizer.recognize_google(audio).lower()
                    
                    # Check for stop commands
                    if text.lower() in ["stop typing", "stop", "exit typing", "exit typing mode"]:
                        logger.info(f"Stop typing command detected (Google fallback): '{text}'")
                        return "stop typing", True
                    
                    # Return the text for typing
                    if text:
                        logger.info(f"Typing mode text recognized (Google fallback): '{text}'")
                        print(f"Typing: '{text}'")
                        return text, True
                except Exception as e:
                    logger.error(f"Error with Google recognition in typing mode: {e}")
                    return None, True
            except sr.WaitTimeoutError:
                logger.info("No speech detected in typing mode")
                return None, True
                
        return None, True
    
    def process_voice_command(self):
        """Process a voice command using the appropriate recognition method"""
        # Check if we're in typing mode first
        if hasattr(self.pyautogui_executor, 'is_typing_mode_active'):
            from audio_to_cursor.pyautogui_command_executor import is_typing_mode_active
            typing_mode = is_typing_mode_active()
        else:
            typing_mode = os.path.exists("typing_mode.flag")
            
        # If in typing mode, use a simplified recognition approach
        if typing_mode:
            logger.info("In typing mode, using optimized recognition process")
            return self._process_typing_input()
        
        # Not in typing mode - use the full multi-engine pipeline
        logger.info("Starting voice command processing")
        recognition_results = self.speech_module.listen_and_recognize()
        if not recognition_results:
            logger.info("No valid speech detected")
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
        logger.info("Interpreting command with Gemini")
        print("\nProcessing engines sequentially...")
        
        # STEP 3: Intent mapping with Gemini
        start_time = time.time()
        interpreted_command = self.intent_mapper.map_multi_engine_intent(recognition_results)
        processing_time = time.time() - start_time
        logger.debug(f"Command interpretation took {processing_time:.2f} seconds")
        
        if not interpreted_command:
            logger.warning("Failed to interpret command")
            print("❌ Could not interpret the command. Try again with a clearer command.")
            return None, True
        
        # Log the command and interpretation
        self.log_command(recognition_results, interpreted_command)
        
        # Show final interpretation
        logger.info(f"Final interpretation: '{interpreted_command}'")
        print(f"\n🎯 Final interpretation: '{interpreted_command}'")
        
        # STEP 4: Execute the command
        logger.info(f"Executing command: '{interpreted_command}'")
        print(f"Executing: '{interpreted_command}'")
        
        # Execute the command directly using the PyAutoGUI executor
        try:
            if self.pyautogui_executor:
                # Use PyAutoGUI command executor if available
                logger.debug("Using PyAutoGUI executor")
                should_continue = self.pyautogui_executor.execute_command(interpreted_command)
            else:
                # Fall back to traditional voice control
                logger.debug("Using traditional voice control executor")
                should_continue = self.voice_control.execute_command(interpreted_command)
            
            logger.info(f"Command execution complete. Continue: {should_continue}")
            return interpreted_command, should_continue
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            print(f"Error: {e}")
            return interpreted_command, True
    
    def run(self):
        """Run the multi-engine voice control system"""
        logger.info("Starting multi-engine voice control system")
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
        
        logger.info("Voice control system entering main command loop")
        running = True
        command_count = 0
        
        try:
            while running:
                try:
                    command_count += 1
                    logger.info(f"Waiting for command #{command_count}")
                    interpreted_command, running = self.process_voice_command()
                    
                    if not running:
                        logger.info("Received exit command")
                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt received, shutting down")
                    running = False
                except Exception as e:
                    logger.error(f"Error in command processing loop: {e}")
                    print(f"Error: {e}")
                    # Continue running despite errors
        finally:
            # Ensure resources are cleaned up properly
            self.cleanup()
            
        logger.info("Multi-engine voice control system stopped")

    def initialize_whisper(self):
        """Initialize Faster Whisper model if available"""
        try:
            # Check if speech_module has already initialized Whisper
            if hasattr(self.speech_module, 'whisper_model') and self.speech_module.whisper_model is not None:
                logger.info("Whisper model already initialized")
                return True
                
            # Check if Faster Whisper is available
            if not self.speech_module.engines_available.get("faster_whisper", False):
                logger.info("Faster Whisper is not available, skipping initialization")
                return False
                
            # Initialize Whisper model
            logger.info("Initializing Faster Whisper model")
            from faster_whisper import WhisperModel

            # Use small model by default (good balance of speed and accuracy)
            model_size = "small"
            logger.info(f"Loading Faster Whisper model ({model_size})...")
            
            # Initialize the model with CPU settings
            self.speech_module.whisper_model = WhisperModel(
                model_size, 
                device="cpu", 
                compute_type="int8", 
                cpu_threads=4, 
                download_root="./whisper_models"
            )
            
            logger.info("Faster Whisper model initialized successfully")
            return True
        except ImportError:
            logger.warning("Faster Whisper not available - will use other engines")
            return False
        except Exception as e:
            logger.error(f"Error initializing Faster Whisper model: {e}")
            print(f"Warning: Failed to initialize Whisper model: {e}")
            return False

if __name__ == "__main__":
    try:
        # Set multiprocessing start method to help prevent resource leaks
        import multiprocessing
        if hasattr(multiprocessing, 'set_start_method'):
            try:
                multiprocessing.set_start_method('spawn')
            except RuntimeError:
                # Method might already be set
                pass
                
        voice_control = MultiEngineVoiceControl(move_distance=100)
        
        try:
            voice_control.run()
        finally:
            # Ensure cleanup happens even if an error occurs
            voice_control.cleanup()
    except KeyboardInterrupt:
        logger.info("Program terminated by user")
        print("\nProgram terminated by user")
        
        # Force cleanup of multiprocessing resources
        try:
            import multiprocessing
            multiprocessing.resource_tracker._resource_tracker.clear()
        except:
            pass
            
        sys.exit(0) 