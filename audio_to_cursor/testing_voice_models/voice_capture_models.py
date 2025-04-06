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

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("multi_recognition_logs.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("MultiVoiceRecognition")

def load_env_file():
    """Load environment variables from .env file"""
    if os.path.exists('.env'):
        with open('.env', 'r') as file:
            for line in file:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key] = value

class MultiEngineRecognizer:
    """Class to handle multiple voice recognition engines in parallel"""
    
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.results_queue = queue.Queue()
        
        # Check which engines are available
        self.engines_available = {
            "google": True,  # Google is always available through the API
            "sphinx": self._check_sphinx_available(),
            "vosk": self._check_vosk_available(),
            "faster_whisper": self._check_faster_whisper_available()
        }
        
        # Load Gemini for processing
        load_env_file()
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("No Gemini API key found. Will use simple voting instead.")
            self.gemini_available = False
        else:
            self._setup_gemini()
            self.gemini_available = True
            
        logger.info(f"Available engines: Google:{self.engines_available['google']}, "
                   f"Sphinx:{self.engines_available['sphinx']}, "
                   f"Vosk:{self.engines_available['vosk']}, "
                   f"Faster Whisper:{self.engines_available['faster_whisper']}")
    
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
    
    def _check_faster_whisper_available(self):
        """Check if Faster Whisper is available"""
        try:
            from faster_whisper import WhisperModel
            return True
        except ImportError:
            logger.warning("Faster Whisper not found. Faster Whisper recognition will be skipped.")
            return False
    
    def _setup_gemini(self):
        """Set up the Gemini model"""
        try:
            genai.configure(api_key=self.api_key)
            
            # List available models first for debugging
            for model in genai.list_models():
                if "gemini" in model.name.lower():
                    logger.info(f"Available Gemini model: {model.name}")
            
            # Use appropriate model
            self.model = genai.GenerativeModel('gemini-2.0-flash')
            logger.info("Successfully initialized Gemini model")
        except Exception as e:
            logger.error(f"Error setting up Gemini model: {e}")
            self.gemini_available = False
    
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
    
    def process_with_gemini(self, results):
        """Use Gemini to select the best recognition from multiple engines"""
        if not self.gemini_available or not results:
            return self._simple_voting(results)
            
        # Create a prompt for Gemini
        prompt = """
        Task: You are a speech recognition accuracy analyzer. 
        You need to identify the most accurate transcription from multiple speech recognition engines.
        
        Here are the transcriptions from different engines:
        """
        
        for result in results:
            if result["text"]:
                prompt += f"\n{result['engine'].capitalize()}: '{result['text']}'"
        
        prompt += """
        
        Guidelines:
        1. Analyze all the transcriptions and select the one that appears most accurate.
        2. Consider that engines might mishear words or have different errors.
        3. If all transcriptions are similar, choose the most complete and grammatically correct one.
        4. If transcriptions are very different, choose the one that seems most contextually coherent.
        5. Return ONLY the corrected text of your selected transcription, don't add the engine name.
        6. Make minor corrections if necessary for spelling or grammar.
        7. Do not add any explanations or extra text.
        
        Your response (corrected text only):
        """
        
        try:
            # Generate content using the Gemini model
            generation_config = {
                "temperature": 0.2,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 128,
            }
            
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            # Clean up the response
            selected_text = response.text.strip()
            logger.info(f"Gemini selected: '{selected_text}'")
            return selected_text
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            return self._simple_voting(results)
    
    def _simple_voting(self, results):
        """Simple voting mechanism when Gemini is not available"""
        # Filter out None results
        valid_results = [r for r in results if r["text"]]
        
        if not valid_results:
            return None
            
        # If only one result, return it
        if len(valid_results) == 1:
            return valid_results[0]["text"]
            
        # Prioritize Faster Whisper if available
        for r in valid_results:
            if r["engine"] == "faster_whisper":
                return r["text"]
                
        # Then Google as backup
        for r in valid_results:
            if r["engine"] == "google":
                return r["text"]
                
        # Otherwise return the first result
        return valid_results[0]["text"]
    
    def listen_and_recognize(self):
        """Listen for voice input and recognize using multiple engines"""
        with sr.Microphone() as source:
            print("Listening...")
            self.recognizer.adjust_for_ambient_noise(source)
            try:
                audio = self.recognizer.listen(source, timeout=5)
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
        
        # Print all results
        print("\nRecognition results:")
        for result in results:
            if result["text"]:
                print(f"{result['engine'].capitalize()}: '{result['text']}'")
            else:
                print(f"{result['engine'].capitalize()}: No result")
        
        # Process results with Gemini or simple voting
        final_text = self.process_with_gemini(results)
        if final_text:
            print(f"\nFinal selection: '{final_text}'")
        
        return final_text, results
    
    def run(self):
        """Run the multi-engine recognition system"""
        print("Multi-Engine Voice Recognition")
        print("=============================")
        print("\nThis system uses multiple speech recognition engines in parallel:")
        
        # Show which engines are available
        print("- Google (online)")
        if self.engines_available["sphinx"]:
            print("- CMU Sphinx (offline)")
        if self.engines_available["vosk"]:
            print("- Vosk (offline)")
        if self.engines_available["faster_whisper"]:
            print("- Faster Whisper (offline)")
            
        if self.gemini_available:
            print("\nGemini AI is available and will select the best recognition.")
        else:
            print("\nGemini AI is not available. Will use simple selection logic.")
        
        print("\nPress Ctrl+C to exit.")
        
        while True:
            try:
                final_text, results = self.listen_and_recognize()
                print("\n" + "-" * 50 + "\n")
            except KeyboardInterrupt:
                print("\nExiting...")
                break

if __name__ == "__main__":
    try:
        multi_engine = MultiEngineRecognizer()
        multi_engine.run()
    except KeyboardInterrupt:
        logger.info("Program terminated by user")
        print("\nProgram terminated by user")
        sys.exit(0)
