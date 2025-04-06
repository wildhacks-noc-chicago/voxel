import atexit
import logging
import multiprocessing
import os
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser

import pyautogui
import speech_recognition as sr

# Try to import sound libraries
try:
    from playsound import playsound
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False
    logging.warning("playsound module not available. Sound effects will be disabled.")

# Try to import Gemini for AI editing
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("Google Generative AI (Gemini) not available. AI editor feature will be disabled.")

TYPING_TIMEOUT = 5

# Mouse lock state - accessible by other modules
MOUSE_LOCKED_STATE = False
# Typing mode state - accessible by other modules
TYPING_MODE_ACTIVE = False
# AI editor state - accessible by other modules
AI_EDITOR_ACTIVE = False

# File-based state flags
TYPING_MODE_FILE = "typing_mode.flag"
MOUSE_LOCK_FILE = "mouse_lock.flag"  # Same file used by nose tracker
AI_EDITOR_FILE = "ai_editor.flag"  # New flag for AI editor

# Sound effects paths
SOUND_DIR = "assets/sounds"
COMMAND_SUCCESS_SOUND = os.path.join(SOUND_DIR, "command_success.mp3")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='pyautogui_commands.log'
)
logger = logging.getLogger("PyAutoGUICommandExecutor")

# Register a cleanup function to handle resource tracker cleanup
def cleanup_multiprocessing_resources():
    """Try to clean up multiprocessing resources on exit"""
    try:
        multiprocessing.resource_tracker._resource_tracker.clear()
        logger.info("Multiprocessing resources cleaned up at exit")
    except Exception as e:
        logger.error(f"Error cleaning up multiprocessing resources: {e}")

# Register the cleanup function to run at exit
atexit.register(cleanup_multiprocessing_resources)

# Sound effect helper function
def play_sound_effect(sound_file=None):
    """Play a sound effect if the sound module is available"""
    if not SOUND_AVAILABLE:
        return False
        
    try:
        sound_to_play = sound_file if sound_file else COMMAND_SUCCESS_SOUND
        if os.path.exists(sound_to_play):
            # Play in a separate thread to prevent blocking
            threading.Thread(target=playsound, args=(sound_to_play,), daemon=True).start()
            logger.debug(f"Playing sound effect: {sound_to_play}")
            return True
        else:
            logger.warning(f"Sound file not found: {sound_to_play}")
            return False
    except Exception as e:
        logger.error(f"Error playing sound effect: {e}")
        return False

# Helper functions for typing mode state
def set_typing_mode(active=True):
    """Set the typing mode state using both global variable and file flag"""
    global TYPING_MODE_ACTIVE
    TYPING_MODE_ACTIVE = active
    
    if active:
        # Create typing mode flag file
        with open(TYPING_MODE_FILE, "w") as f:
            f.write(str(time.time()))
        logger.info("Typing mode activated - created flag file")
    else:
        # Remove typing mode flag file if it exists
        if os.path.exists(TYPING_MODE_FILE):
            os.remove(TYPING_MODE_FILE)
            logger.info("Typing mode deactivated - removed flag file")

def is_typing_mode_active():
    """Check if typing mode is active by checking both global var and file flag"""
    global TYPING_MODE_ACTIVE
    file_flag = os.path.exists(TYPING_MODE_FILE)
    
    # If there's a mismatch, the file is the source of truth
    if file_flag != TYPING_MODE_ACTIVE:
        TYPING_MODE_ACTIVE = file_flag
        logger.info(f"Synchronized typing mode state from file: {TYPING_MODE_ACTIVE}")
    
    return TYPING_MODE_ACTIVE

# Helper functions for AI editor state
def set_ai_editor(active=True):
    """Set the AI editor state using both global variable and file flag"""
    global AI_EDITOR_ACTIVE
    AI_EDITOR_ACTIVE = active
    
    if active:
        # Create AI editor flag file
        with open(AI_EDITOR_FILE, "w") as f:
            f.write(str(time.time()))
        logger.info("AI editor activated - created flag file")
    else:
        # Remove AI editor flag file if it exists
        if os.path.exists(AI_EDITOR_FILE):
            os.remove(AI_EDITOR_FILE)
            logger.info("AI editor deactivated - removed flag file")

def is_ai_editor_active():
    """Check if AI editor is active by checking both global var and file flag"""
    global AI_EDITOR_ACTIVE
    file_flag = os.path.exists(AI_EDITOR_FILE)
    
    # If there's a mismatch, the file is the source of truth
    if file_flag != AI_EDITOR_ACTIVE:
        AI_EDITOR_ACTIVE = file_flag
        logger.info(f"Synchronized AI editor state from file: {AI_EDITOR_ACTIVE}")
    
    return AI_EDITOR_ACTIVE

# Helper functions for mouse lock state
def set_mouse_locked(locked=True):
    """Set the mouse lock state using both global variable and file flag"""
    global MOUSE_LOCKED_STATE
    MOUSE_LOCKED_STATE = locked
    
    if locked:
        # Create mouse lock flag file
        with open(MOUSE_LOCK_FILE, "w") as f:
            f.write(str(time.time()))
        logger.info("Mouse locked - created flag file")
    else:
        # Remove mouse lock flag file if it exists
        if os.path.exists(MOUSE_LOCK_FILE):
            os.remove(MOUSE_LOCK_FILE)
            logger.info("Mouse unlocked - removed flag file")

def is_mouse_locked():
    """Check if mouse is locked by checking both global var and file flag"""
    global MOUSE_LOCKED_STATE
    file_flag = os.path.exists(MOUSE_LOCK_FILE)
    
    # If there's a mismatch, the file is the source of truth
    if file_flag != MOUSE_LOCKED_STATE:
        MOUSE_LOCKED_STATE = file_flag
        logger.info(f"Synchronized mouse lock state from file: {MOUSE_LOCKED_STATE}")
    
    return MOUSE_LOCKED_STATE

class PyAutoGUICommandExecutor:
    """Executes voice commands using PyAutoGUI to control mouse and keyboard"""
    
    def __init__(self, move_distance=100):
        """Initialize with default movement distance"""
        self.move_distance = move_distance
        
        # Configure PyAutoGUI safety features
        pyautogui.PAUSE = 0  # 500ms pause between commands
        pyautogui.FAILSAFE = True  # Move mouse to top-left to abort
        
        # Store current mouse position for relative movements
        self.current_x, self.current_y = pyautogui.position()
        
        # Typing mode flag and thread
        self.typing_thread = None
        self.stop_typing_event = threading.Event()
        
        # Continuous scrolling thread
        self.scroll_thread = None
        self.stop_scroll_event = threading.Event()
        
        # Speech recognizer as instance variable to better manage its lifecycle
        self.recognizer = None
        
        # For AI processing - keep track of what was typed
        self.current_typing_buffer = ""
        
        # Create sounds directory if it doesn't exist
        if SOUND_AVAILABLE and not os.path.exists(SOUND_DIR):
            os.makedirs(SOUND_DIR, exist_ok=True)
            logger.info(f"Created sounds directory: {SOUND_DIR}")
        
        # Remove any stale state files
        for file in [TYPING_MODE_FILE, MOUSE_LOCK_FILE, AI_EDITOR_FILE]:
            if os.path.exists(file):
                os.remove(file)
                logger.info(f"Removed stale flag file on startup: {file}")
        
        # Initialize Gemini if available
        if GEMINI_AVAILABLE:
            self._setup_gemini()
        
        # Try to import Faster Whisper if available
        self.faster_whisper_available = False
        self.whisper_model = None
        try:
            from faster_whisper import WhisperModel
            self.faster_whisper_available = True
            # Initialize the model with smaller size for faster typing
            self.whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=4)
            logger.info("Faster Whisper initialized for typing mode")
        except ImportError:
            logger.warning("Faster Whisper not available - typing mode will use Google Speech Recognition")
            
        # Command mapping - simplified to just basic mouse commands
        self.commands = {
            # Mouse movement commands
            "move cursor right": self.move_right,
            "right": self.move_right,
            "move cursor left": self.move_left,
            "left": self.move_left,
            "move cursor up": self.move_up,
            "up": self.move_up,
            "move cursor down": self.move_down,
            "down": self.move_down,
            
            # Mouse click commands
            "click": self.left_click,
            "left click": self.left_click,
            "right click": self.right_click,
            
            # Mouse lock commands
            "lock": self.lock_mouse,
            "unlock": self.unlock_mouse,
            
            # Typing commands
            "start typing": self.start_typing,
            "stop typing": self.stop_typing,
            
            # AI editor commands
            "enable AI": self.enable_ai_editor,
            "disable AI": self.disable_ai_editor,
            "AI editor enabled": self.enable_ai_editor,
            "AI editor disabled": self.disable_ai_editor,
            
            # Scroll commands
            "scroll up": self.scroll_up,
            "scroll down": self.scroll_down,
            "page up": self.page_up,
            "page down": self.page_down,
            "keep scrolling up": self.start_scrolling_up,
            "keep scrolling down": self.start_scrolling_down,
            "stop scrolling": self.stop_scrolling,
            
            # Exit command
            "exit": self.exit_program,
            "quit": self.exit_program,
            "stop listening": self.exit_program,

            # Browser commands
            "open browser": self.open_browser,
            "enter": self.enter,
            "clear text": self.clear_text  # Add new command
        }
        
        logger.info("PyAutoGUI Command Executor initialized with simplified mouse commands")
        
        # Check if sound is available and log status
        if SOUND_AVAILABLE:
            logger.info(f"Sound effects enabled. Success sound: {COMMAND_SUCCESS_SOUND}")
            
            # Check if default sound file exists, if not create a note about it
            if not os.path.exists(COMMAND_SUCCESS_SOUND):
                logger.warning(f"Default sound file not found: {COMMAND_SUCCESS_SOUND}. Please add a sound file to this location.")
                print(f"Note: For sound effects to work, please add an MP3 file at: {COMMAND_SUCCESS_SOUND}")
        else:
            logger.warning("Sound effects disabled. Install 'playsound' package to enable.")
            
    def __del__(self):
        """Clean up resources when this object is destroyed"""
        try:
            # Clean up any multiprocessing resources
            cleanup_multiprocessing_resources()
            
            # Stop the typing thread if it's running
            if hasattr(self, 'stop_typing_event'):
                self.stop_typing_event.set()
                
            # Stop the scroll thread if it's running
            if hasattr(self, 'stop_scroll_event'):
                self.stop_scroll_event.set()
                
            # Clean up whisper model if initialized
            if hasattr(self, 'whisper_model') and self.whisper_model:
                del self.whisper_model
                
            # Clean up recognizer 
            if hasattr(self, 'recognizer') and self.recognizer:
                del self.recognizer
                
            logger.info("PyAutoGUI Command Executor resources cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up resources: {e}")
    
    def _setup_gemini(self):
        """Set up the Gemini API if available"""
        if not GEMINI_AVAILABLE:
            logger.warning("Gemini API not available, skipping setup")
            return False
            
        try:
            # Get API key from environment
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                logger.error("No Gemini API key found in environment. AI editor will be disabled.")
                return False
                
            # Configure the API
            genai.configure(api_key=api_key)
            
            # Initialize the model
            self.gemini_model = genai.GenerativeModel('gemini-2.0-flash')
            logger.info("Gemini API initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Error setting up Gemini API: {e}")
            return False
    
    def execute_command(self, command):
        """Execute a voice command using PyAutoGUI"""
        # Update current mouse position
        self.current_x, self.current_y = pyautogui.position()
        
        # Special handling for 'stop typing' command during typing mode
        if command.lower() == "stop typing" and is_typing_mode_active():
            logger.info("Stop typing command received during typing mode")
            return self.stop_typing()
        
        # Check if we're in typing mode and this is not a stop command
        if is_typing_mode_active() and command.lower() != "stop typing":
            logger.info(f"Ignoring command '{command}' - in typing mode")
            return True
        
        # Check if command exists
        if command in self.commands:
            logger.info(f"Executing command: {command}")
            
            # Execute the command function
            should_continue = self.commands[command]()
            
            # Play success sound if available
            if should_continue:  # Only play if command was successful
                play_sound_effect()
            
            # Return whether the program should continue running
            return should_continue
        else:
            logger.warning(f"Unknown command: {command}")
            print(f"Unknown command: {command}")
            return True
    
    # AI editor commands
    def enable_ai_editor(self):
        """Enable the AI editor"""
        set_ai_editor(True)
        logger.info("AI editor enabled")
        print("🤖 AI editor enabled. Your text will be enhanced when typing mode ends.")
        play_sound_effect()  # Play sound for successful command
        return True
    
    def disable_ai_editor(self):
        """Disable the AI editor"""
        set_ai_editor(False)
        logger.info("AI editor disabled")
        print("🚫 AI editor disabled. Your text will not be processed.")
        play_sound_effect()  # Play sound for successful command
        return True
    
    def ai_enhance_text(self, text):
        """Use Gemini to enhance the given text"""
        if not GEMINI_AVAILABLE or not hasattr(self, 'gemini_model'):
            logger.warning("Gemini not available for AI text enhancement")
            return text
            
        if not text or len(text.strip()) < 3:
            logger.info("Text too short for AI enhancement")
            return text
            
        try:
            logger.info(f"Enhancing text with AI: '{text[:50]}...'")
            print("🤖 AI is enhancing your text...")
            
            prompt = f"""
            Please improve the following text. Fix any grammar, spelling, punctuation, and sentence structure issues.
            Make it clear and concise while preserving the original meaning.
            
            Text to improve: "{text}"
            
            Return ONLY the improved text without quotes, explanation, or additional comments.
            """
            
            # Configure generation parameters
            generation_config = {
                "temperature": 0.2,  # Lower temperature for more predictable output
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 1024,  # Allow longer responses
            }
            
            # Generate the enhanced text
            response = self.gemini_model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            # Get the enhanced text
            enhanced_text = response.text.strip()
            
            # Log the enhancement
            logger.info(f"Original ({len(text)} chars) vs Enhanced ({len(enhanced_text)} chars)")
            logger.info(f"Enhanced text: '{enhanced_text[:50]}...'")
            
            print(f"✅ Text enhanced: {len(text)} → {len(enhanced_text)} characters")
            play_sound_effect()  # Play sound for successful AI enhancement
            return enhanced_text
            
        except Exception as e:
            logger.error(f"Error enhancing text with AI: {e}")
            print(f"❌ Error enhancing text: {e}")
            return text  # Return original text if enhancement fails
    
    # Mouse lock commands
    def lock_mouse(self):
        """Lock mouse movement"""
        set_mouse_locked(True)
        logger.info("Mouse movement locked")
        print("🔒 Mouse movement locked. Say 'unlock' to enable movement.")
        play_sound_effect()  # Play sound for successful command
        return True
    
    def unlock_mouse(self):
        """Unlock mouse movement"""
        set_mouse_locked(False)
        logger.info("Mouse movement unlocked")
        print("🔓 Mouse movement unlocked.")
        play_sound_effect()  # Play sound for successful command
        return True
    
    # Mouse movement commands
    def move_right(self):
        """Move cursor to the right"""
        if is_mouse_locked():
            print("🔒 Mouse is locked. Say 'unlock' to enable movement.")
            return True
            
        pyautogui.moveRel(self.move_distance, 0)
        logger.info(f"Moved cursor right by {self.move_distance}px")
        play_sound_effect()  # Play sound for successful command
        return True
    
    def move_left(self):
        """Move cursor to the left"""
        if is_mouse_locked():
            print("🔒 Mouse is locked. Say 'unlock' to enable movement.")
            return True
            
        pyautogui.moveRel(-self.move_distance, 0)
        logger.info(f"Moved cursor left by {self.move_distance}px")
        play_sound_effect()  # Play sound for successful command
        return True
    
    def move_up(self):
        """Move cursor up"""
        if is_mouse_locked():
            print("🔒 Mouse is locked. Say 'unlock' to enable movement.")
            return True
            
        pyautogui.moveRel(0, -self.move_distance)
        logger.info(f"Moved cursor up by {self.move_distance}px")
        play_sound_effect()  # Play sound for successful command
        return True
    
    def move_down(self):
        """Move cursor down"""
        if is_mouse_locked():
            print("🔒 Mouse is locked. Say 'unlock' to enable movement.")
            return True
            
        pyautogui.moveRel(0, self.move_distance)
        logger.info(f"Moved cursor down by {self.move_distance}px")
        play_sound_effect()  # Play sound for successful command
        return True
    
    # Mouse click commands
    def left_click(self):
        """Perform left click at current position"""
        pyautogui.click()
        logger.info(f"Left click at ({self.current_x}, {self.current_y})")
        play_sound_effect()  # Play sound for successful command
        return True
    
    def right_click(self):
        """Perform right click at current position"""
        pyautogui.rightClick()
        logger.info(f"Right click at ({self.current_x}, {self.current_y})")
        play_sound_effect()  # Play sound for successful command
        return True
    
    # Scroll commands
    def scroll_up(self):
        """Scroll up"""
        if is_mouse_locked():
            print("🔒 Mouse is locked. Say 'unlock' to enable movement.")
            return True
            
        # In pyautogui, positive values scroll up
        pyautogui.scroll(10)  # Adjust this value to control scroll speed
        logger.info("Scrolled up")
        play_sound_effect()  # Play sound for successful command
        return True
    
    def scroll_down(self):
        """Scroll down"""
        if is_mouse_locked():
            print("🔒 Mouse is locked. Say 'unlock' to enable movement.")
            return True
            
        # In pyautogui, negative values scroll down
        pyautogui.scroll(-10)  # Adjust this value to control scroll speed
        logger.info("Scrolled down")
        play_sound_effect()  # Play sound for successful command
        return True
    
    def page_up(self):
        """Scroll up a full page"""
        if is_mouse_locked():
            print("🔒 Mouse is locked. Say 'unlock' to enable movement.")
            return True
            
        # Use the Page Up key to scroll up a full page
        pyautogui.press('pageup')
        logger.info("Page up")
        play_sound_effect()
        return True
    
    def page_down(self):
        """Scroll down a full page"""
        if is_mouse_locked():
            print("🔒 Mouse is locked. Say 'unlock' to enable movement.")
            return True
            
        # Use the Page Down key to scroll down a full page
        pyautogui.press('pagedown')
        logger.info("Page down")
        play_sound_effect()
        return True
    
    def _scroll_thread_function(self, direction="up"):
        """Thread function for continuous scrolling"""
        scroll_value = 1 if direction == "up" else -1
        logger.info(f"Starting continuous scrolling {direction}")
        print(f"🔄 Continuous scrolling {direction}. Say 'stop scrolling' to stop.")
        
        try:
            # Play sound to indicate start of continuous scrolling
            play_sound_effect()
            
            # Continuous scroll until stopped
            while not self.stop_scroll_event.is_set():
                pyautogui.scroll(scroll_value)
                time.sleep(0.1)  # Adjust delay between scrolls
        except Exception as e:
            logger.error(f"Error in scroll thread: {e}")
        finally:
            logger.info("Continuous scrolling stopped")
            print("Continuous scrolling stopped")
    
    def start_scrolling_up(self):
        """Start continuous scrolling up"""
        if is_mouse_locked():
            print("🔒 Mouse is locked. Say 'unlock' to enable movement.")
            return True
            
        # Stop any existing scroll thread
        self.stop_scrolling()
        
        # Reset event
        self.stop_scroll_event.clear()
        
        # Start new thread
        logger.info("Starting continuous scroll up")
        self.scroll_thread = threading.Thread(target=self._scroll_thread_function, args=("up",))
        self.scroll_thread.daemon = True
        self.scroll_thread.start()
        
        return True
    
    def start_scrolling_down(self):
        """Start continuous scrolling down"""
        if is_mouse_locked():
            print("🔒 Mouse is locked. Say 'unlock' to enable movement.")
            return True
            
        # Stop any existing scroll thread
        self.stop_scrolling()
        
        # Reset event
        self.stop_scroll_event.clear()
        
        # Start new thread
        logger.info("Starting continuous scroll down")
        self.scroll_thread = threading.Thread(target=self._scroll_thread_function, args=("down",))
        self.scroll_thread.daemon = True
        self.scroll_thread.start()
        
        return True
    
    def stop_scrolling(self):
        """Stop continuous scrolling"""
        if hasattr(self, 'scroll_thread') and self.scroll_thread and self.scroll_thread.is_alive():
            logger.info("Stopping continuous scrolling")
            self.stop_scroll_event.set()
            self.scroll_thread.join(timeout=1.0)
            play_sound_effect()  # Play sound for stopping
            return True
        else:
            logger.info("No scrolling to stop")
            return True
    
    # Browser commands
    def open_browser(self):
        """Open the default browser"""
        webbrowser.open_new('https://www.google.com')  # Opens default browser with google 
        logger.info("Opened default browser with google")
        play_sound_effect()  # Play sound for successful command
        return True
    
    def _typing_thread_function(self):
        """Background thread for continuous typing mode"""
        logger.info("Typing mode thread started")
        print("🔤 Typing mode activated. Start speaking to type. Say 'stop typing' to exit typing mode.")
        
        # Play sound to indicate typing mode started successfully
        play_sound_effect()
        
        # Initialize speech recognizer only once for the entire thread
        self.recognizer = sr.Recognizer()
        
        # Reset the current typing buffer
        self.current_typing_buffer = ""
        
        # Get a microphone instance
        mic = sr.Microphone()
        
        # Temp files to clean up
        temp_files = []
        
        try:
            # Main typing loop
            while not self.stop_typing_event.is_set():
                try:
                    print("Listening for text to type...")
                    with mic as source:
                        # Listen for speech with timeout
                        try:
                            audio = self.recognizer.listen(source, timeout=TYPING_TIMEOUT, phrase_time_limit=10)
                        except sr.WaitTimeoutError:
                            # No speech detected, continue listening
                            continue
                        
                    # Process the audio with Whisper if available
                    if self.faster_whisper_available and self.whisper_model:
                        try:
                            # Save to temporary file for Whisper
                            temp_filename = None
                            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                                temp_filename = f.name
                                temp_files.append(temp_filename)  # Add to cleanup list
                                
                            with open(temp_filename, "wb") as f:
                                f.write(audio.get_wav_data())
                            
                            # Process with Whisper
                            logger.info("Processing typing input with Whisper")
                            segments, info = self.whisper_model.transcribe(temp_filename, beam_size=1)
                            
                            # Get the text
                            text = " ".join([segment.text for segment in segments]).strip()
                            
                            # Remove the temp file immediately after use
                            try:
                                os.unlink(temp_filename)
                                temp_files.remove(temp_filename)
                            except:
                                pass
                        except Exception as e:
                            logger.error(f"Whisper error: {e}")
                            # Fall back to Google
                            text = self.recognizer.recognize_google(audio)
                    else:
                        # Use Google Speech Recognition
                        text = self.recognizer.recognize_google(audio)
                    
                    # Log the recognized text
                    logger.info(f"Typing mode recognized: '{text}'")
                    
                    # Enhanced check for stop commands - use startswith to handle trailing punctuation
                    text_lower = text.lower().strip()
                    stop_phrases = ["stop typing", "stop", "exit typing", "exit typing mode"]
                    
                    if any(text_lower.startswith(phrase) for phrase in stop_phrases):
                        logger.info(f"Stop typing command detected: '{text}'")
                        print("🛑 Exiting typing mode")
                        break
                    
                    logger.info(f"Typing: '{text}'")
                    print(f"Typing: '{text}'")
                    
                    # Add to the typing buffer
                    self.current_typing_buffer += text + " "
                    
                    # Type the recognized text
                    pyautogui.write(text + " ")  # Add space after
                    
                    # Play sound for each successful typing recognition
                    play_sound_effect()
                    
                except sr.UnknownValueError:
                    logger.warning("Could not understand audio in typing mode")
                    print("Could not understand, please try again")
                except sr.RequestError as e:
                    logger.error(f"Recognition error in typing mode: {e}")
                    print(f"Error with speech recognition: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error in typing mode: {e}")
                    print(f"Error: {e}")
        finally:
            # Set event to ensure we exit the loop
            self.stop_typing_event.set()
            
            # Clean up temp files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
                        logger.info(f"Cleaned up temp file: {temp_file}")
                except Exception as e:
                    logger.error(f"Error cleaning up temp file {temp_file}: {e}")
            
            # Free microphone resources
            try:
                del mic
            except:
                pass
                
            # Clean up speech recognizer
            try:
                if self.recognizer:
                    # Explicitly delete the recognizer to free resources
                    del self.recognizer
                    self.recognizer = None
            except:
                pass
                
            # Process the text with AI if enabled before exiting
            if is_ai_editor_active() and self.current_typing_buffer.strip():
                # First delete the existing text
                text_to_enhance = self.current_typing_buffer.strip()
                char_count = len(text_to_enhance)
                
                # Press backspace for each character to remove the text
                # We add spaces so typically need to delete one extra character per word
                estimated_chars = char_count + (text_to_enhance.count(' '))
                logger.info(f"Deleting approximately {estimated_chars} characters to replace with AI-enhanced text")
                
                for _ in range(estimated_chars):
                    pyautogui.press('backspace')
                    time.sleep(0.01)  # Small delay to avoid overwhelming the system
                
                # Now enhance the text and type the enhanced version
                enhanced_text = self.ai_enhance_text(text_to_enhance)
                
                # Type the enhanced text
                pyautogui.write(enhanced_text)
                logger.info(f"Typed AI-enhanced text: '{enhanced_text[:50]}...'")
                
            # Reset typing mode flag using helper function
            set_typing_mode(False)
            
            # Force multiprocessing cleanup
            try:
                # Force garbage collection
                import gc
                gc.collect()
                
                # Try to directly clear the resource tracker
                multiprocessing.resource_tracker._resource_tracker.clear()
                logger.info("Cleared multiprocessing resource tracker after typing mode")
            except Exception as e:
                logger.error(f"Error clearing multiprocessing resources: {e}")
            
            # Run the external cleanup script if available
            try:
                if os.path.exists("./cleanup_semaphores.py"):
                    logger.info("Running semaphore cleanup script from typing thread")
                    subprocess.run(["python3", "./cleanup_semaphores.py"], 
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                logger.error(f"Failed to run semaphore cleanup script from thread: {e}")
            
            logger.info("Typing mode thread ended")
            print("Typing mode deactivated")
            
            # Play sound when typing mode exits 
            play_sound_effect()
    
    def start_typing(self):
        """Start continuous typing mode"""
        # Check current state using helper function
        if is_typing_mode_active():
            logger.info("Typing mode already active")
            print("Typing mode is already active")
            play_sound_effect()  # Still play sound for feedback
            return True
        
        # Set flag and create thread using helper function
        set_typing_mode(True)
        self.stop_typing_event.clear()
        
        logger.info("Starting typing mode")
        self.typing_thread = threading.Thread(target=self._typing_thread_function)
        self.typing_thread.daemon = True
        self.typing_thread.start()
        
        # Run semaphore cleanup script to prevent leaks
        try:
            if os.path.exists("./cleanup_semaphores.py"):
                logger.info("Running semaphore cleanup script after starting typing mode")
                subprocess.run(["python3", "./cleanup_semaphores.py"], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.error(f"Failed to run semaphore cleanup script: {e}")
        
        # Note: We don't play sound here because _typing_thread_function will play it
        return True
    
    def stop_typing(self):
        """Stop continuous typing mode"""
        # Check if typing is active using helper function
        if is_typing_mode_active() and self.typing_thread and self.typing_thread.is_alive():
            logger.info("Stopping typing mode")
            print("Stopping typing mode...")
            
            # Signal thread to stop
            self.stop_typing_event.set()
            
            # Wait for thread to finish (with timeout)
            self.typing_thread.join(timeout=2.0)
            
            # Force resource cleanup
            cleanup_multiprocessing_resources()
            
            # Reset flag using helper function
            set_typing_mode(False)
            
            # Run semaphore cleanup script to prevent leaks
            try:
                if os.path.exists("./cleanup_semaphores.py"):
                    logger.info("Running semaphore cleanup script after stopping typing mode")
                    subprocess.run(["python3", "./cleanup_semaphores.py"], 
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                logger.error(f"Failed to run semaphore cleanup script: {e}")
            
            logger.info("Typing mode stopped")
            play_sound_effect()  # Play sound for successful command
        else:
            logger.info("Typing mode not active")
            print("Typing mode is not active")
            play_sound_effect()  # Still play sound for feedback
        
        return True
    
    def enter(self):
        """Press Enter key"""
        pyautogui.press('enter')
        logger.info("Pressed enter")
        play_sound_effect()  # Play sound for successful command
        return True
    
    def clear_text(self):
        """Clear all text by selecting all and deleting"""
        logger.info("Clearing text")
        try:
            # Select all text (Cmd+A on macOS, Ctrl+A on Windows/Linux)
            if sys.platform == "darwin":
                pyautogui.hotkey("command", "a")
            else:
                pyautogui.hotkey("ctrl", "a")
            
            # Delete selected text
            pyautogui.press("delete")
            
            # Play success sound
            play_sound_effect()
            
            logger.info("Text cleared successfully")
            return True
        except Exception as e:
            logger.error(f"Error clearing text: {e}")
            return False
    
    # Exit command
    def exit_program(self):
        """Exit the program"""
        # First stop typing if active
        if is_typing_mode_active():
            self.stop_typing()
            
        # Stop scrolling if active
        if hasattr(self, 'scroll_thread') and self.scroll_thread and self.scroll_thread.is_alive():
            self.stop_scrolling()
            
        logger.info("Exit command received")
        print("Exiting program...")
        play_sound_effect()  # Play sound for successful command
        
        # Force cleanup of multiprocessing resources
        cleanup_multiprocessing_resources()
        
        return False  # Return False to stop the program


# Example usage if run directly
if __name__ == "__main__":
    executor = PyAutoGUICommandExecutor()
    
    # Test a few commands
    print("Testing PyAutoGUI Command Executor")
    print("Moving cursor right")
    executor.execute_command("right")
    time.sleep(1)
    
    print("Moving cursor down")
    executor.execute_command("down")
    time.sleep(1)
    
    print("Left click")
    executor.execute_command("click")
    
    print("Test complete") 