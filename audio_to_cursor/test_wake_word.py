import logging
import time

import speech_recognition as sr

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='wake_word_test.log'
)
logger = logging.getLogger("WakeWordTest")

def listen_for_wake_word(recognizer, timeout=3, phrase_time_limit=3, verbose=True):
    """Listen for the wake word 'Hey Voxel'"""
    print("\r👂 Listening for 'Hey Voxel'...", end="", flush=True)
    logger.info("Listening for wake word")
    
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source)
            try:
                audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                logger.info("Captured potential audio, checking...")
            except sr.WaitTimeoutError:
                # Timeout is expected, just return False
                return False
            
            # Try to recognize any speech
            try:
                text = recognizer.recognize_google(audio).lower()
                
                # Always log what was heard
                logger.info(f"Heard: '{text}'")
                
                # Check if the wake word is in the text
                if "hey voxel" in text or "hay voxel" in text or "hey vocal" in text or "hi voxel" in text:
                    print("\n🎧 Wake word 'Hey Voxel' detected! Heard: '{}'".format(text))
                    logger.info("Wake word detected in: '{}'".format(text))
                    return True
                else:
                    # Log that we heard something, but it wasn't the wake word
                    logger.info(f"Not wake word: '{text}'")
                    if verbose:
                        print(f"\n👀 Heard: '{text}' (not wake word)")
                    else:
                        # Just reset the prompt line if not verbose
                        print("\r👂 Listening for 'Hey Voxel'...", end="", flush=True)
                    return False
            except sr.UnknownValueError:
                logger.info("Could not understand audio")
                if verbose:
                    print("\n❓ Could not understand audio")
                return False
            except sr.RequestError as e:
                logger.error(f"Error with Google speech recognition service: {e}")
                if verbose:
                    print(f"\n🌐 Error with Google speech recognition service: {e}")
                return False
    except Exception as e:
        logger.error(f"Error in wake word detection: {e}")
        if verbose:
            print(f"\n⚠️ Error: {e}")
        return False

def main():
    print("Wake Word Detection Test")
    print("=======================")
    print("Say 'Hey Voxel' to test wake word detection")
    print("All detected speech will be logged to 'wake_word_test.log'")
    print("Press Ctrl+C to exit")
    
    # Ask user if they want verbose mode
    verbose = input("Show all detected speech in console? (y/n): ").lower() == 'y'
    
    recognizer = sr.Recognizer()
    
    try:
        while True:
            if listen_for_wake_word(recognizer, verbose=verbose):
                print("✅ Wake word detected! Would now activate command listening...")
                print("🔄 Going back to wake word detection in 2 seconds...")
                time.sleep(2)
            time.sleep(0.1)  # Prevent excessive CPU usage
    except KeyboardInterrupt:
        print("\nTest terminated by user.")
        print("Check wake_word_test.log for a record of all detected speech.")

if __name__ == "__main__":
    main() 