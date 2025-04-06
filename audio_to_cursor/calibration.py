import datetime
import json
import logging
import os
import sounddevice as sd
import numpy as np
import noisereduce as nr
import librosa
import soundfile as sf
from pathlib import Path

# Set up logging
logging.basicConfig(
    filename='calibration.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CalibrationError(Exception):
    """Custom exception for calibration errors"""
    pass

class CalibrationManager:
    def __init__(self, calibration_file="audio_to_cursor/calibration.json"):
        """Initialize the calibration manager"""
        self.calibration_file = calibration_file
        self.calibration_data = {}
        self.sample_rate = 44100
        self.noise_profile = None
        
        # Create calibration directory if it doesn't exist
        self.calibration_dir = Path("audio_to_cursor/calibration_data")
        self.calibration_dir.mkdir(exist_ok=True)
        
        # Set paths for calibration files
        self.noise_file = self.calibration_dir / "background_noise.wav"
        self.voice_file = self.calibration_dir / "voice_sample.wav"
        self.filtered_file = self.calibration_dir / "filtered_voice.wav"

    def save_calibration(self, noise_profile=None, additional_settings=None):
        """Save calibration data to a file"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        self.calibration_data = {
            "timestamp": timestamp,
            "noise_file": str(self.noise_file),
            "sample_rate": self.sample_rate,
            "additional_settings": additional_settings or {}
        }
        
        try:
            with open(self.calibration_file, "w") as f:
                json.dump(self.calibration_data, f, indent=4)
            logger.info(f"Calibration data saved to {self.calibration_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving calibration data: {e}")
            return False

    def load_calibration(self):
        """Load calibration data from file"""
        if os.path.exists(self.calibration_file):
            try:
                with open(self.calibration_file, "r") as f:
                    self.calibration_data = json.load(f)
                logger.info(f"Calibration data loaded from {self.calibration_file}")
                
                # Load noise profile if it exists
                if os.path.exists(self.calibration_data["noise_file"]):
                    self.noise_profile, _ = librosa.load(
                        self.calibration_data["noise_file"],
                        sr=self.sample_rate
                    )
                    return True
            except Exception as e:
                logger.error(f"Error loading calibration data: {e}")
        return False

    def record_audio(self, duration, filename):
        """Record audio for specified duration"""
        try:
            print(f"Recording for {duration} seconds...")
            audio = sd.rec(
                int(duration * self.sample_rate),
                samplerate=self.sample_rate,
                channels=1,
                dtype='float32'
            )
            sd.wait()  # Wait until recording is finished
            sf.write(filename, audio, self.sample_rate)
            logger.info(f"Audio recorded and saved to {filename}")
            return True
        except Exception as e:
            logger.error(f"Error during recording: {e}")
            return False

    def capture_background_noise(self, duration=5):
        """Capture background noise for calibration"""
        print("\nStep 1: Capturing background noise")
        print("Please remain silent...")
        
        if self.record_audio(duration, self.noise_file):
            try:
                # Load the recorded noise profile
                self.noise_profile, _ = librosa.load(self.noise_file, sr=self.sample_rate)
                logger.info("Background noise captured successfully")
                return True
            except Exception as e:
                logger.error(f"Error loading noise profile: {e}")
                raise CalibrationError("Failed to load noise profile")
        else:
            raise CalibrationError("Failed to capture background noise")

    def capture_voice_sample(self, duration=10):
        """Capture voice sample for testing"""
        print("\nStep 2: Capturing voice sample")
        print("Please speak naturally for the next few seconds...")
        print("Suggested: Count from 1 to 10 at a normal pace")
        
        if not self.record_audio(duration, self.voice_file):
            raise CalibrationError("Failed to capture voice sample")
        logger.info("Voice sample captured successfully")
        return True

    def process_and_test(self):
        """Process the voice sample with noise reduction"""
        print("\nStep 3: Processing and testing noise reduction...")
        
        try:
            # Load the voice sample
            voice_data, _ = librosa.load(self.voice_file, sr=self.sample_rate)
            
            # Apply noise reduction
            filtered_voice = nr.reduce_noise(
                y=voice_data,
                y_noise=self.noise_profile,
                sr=self.sample_rate
            )
            
            # Save the filtered audio
            sf.write(self.filtered_file, filtered_voice, self.sample_rate)
            logger.info("Noise reduction test completed successfully")
            
            print("\nTest files saved:")
            print(f"- Original voice: {self.voice_file}")
            print(f"- Filtered voice: {self.filtered_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error during noise reduction test: {e}")
            raise CalibrationError(f"Failed to process audio: {str(e)}")

    def cleanup_test_files(self):
        """Clean up temporary test files"""
        try:
            if os.path.exists(self.voice_file):
                os.remove(self.voice_file)
            if os.path.exists(self.filtered_file):
                os.remove(self.filtered_file)
            logger.info("Test files cleaned up")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")

    def calibrate(self, keep_test_files=False):
        """Run the complete calibration process"""
        print("Starting calibration process...")
        print("This will capture background noise and test the noise reduction.")
        print("Please ensure you are in a quiet environment.")
        
        try:
            # Step 1: Capture background noise
            self.capture_background_noise()
            
            # Step 2: Capture voice sample for testing
            self.capture_voice_sample()
            
            # Step 3: Process and test
            self.process_and_test()
            
            # Step 4: Save calibration data
            if self.save_calibration():
                print("\nCalibration completed successfully!")
                print(f"Calibration data saved to {self.calibration_file}")
                
                # Cleanup test files if not needed
                if not keep_test_files:
                    self.cleanup_test_files()
                
                return True
            
            return False
            
        except CalibrationError as e:
            print(f"\nCalibration failed: {str(e)}")
            logger.error(f"Calibration failed: {str(e)}")
            return False
        except Exception as e:
            print(f"\nUnexpected error during calibration: {str(e)}")
            logger.error(f"Unexpected error during calibration: {str(e)}")
            return False

class NoiseFilter:
    """Handles noise filtering using calibration data"""
    
    def __init__(self, calibration_manager):
        self.calibration_manager = calibration_manager
        self.noise_profile = None
        self.sample_rate = 44100
        
        # Try to load existing calibration
        self.load_noise_profile()
    
    def load_noise_profile(self):
        """Load the noise profile from calibration"""
        if self.calibration_manager.load_calibration():
            self.noise_profile = self.calibration_manager.noise_profile
            return True
        return False
    
    def filter_audio(self, audio_data):
        """Filter audio data using the noise profile"""
        if self.noise_profile is None:
            logger.warning("No noise profile loaded. Cannot filter audio.")
            return audio_data
        
        try:
            # Ensure audio_data is in the correct format
            if isinstance(audio_data, np.ndarray):
                if len(audio_data.shape) == 1:
                    audio_data = audio_data.reshape(-1, 1)
                filtered_audio = nr.reduce_noise(
                    y=audio_data.flatten(),
                    y_noise=self.noise_profile,
                    sr=self.sample_rate
                )
                return filtered_audio
            return audio_data
        except Exception as e:
            logger.error(f"Error filtering audio: {e}")
            return audio_data

def main():
    """Main function to run calibration"""
    calibration_manager = CalibrationManager()
    
    print("Voice Control System Calibration")
    print("===============================")
    
    # Check if calibration already exists
    if os.path.exists(calibration_manager.calibration_file):
        print("\nExisting calibration found.")
        while True:
            choice = input("Do you want to recalibrate? (y/n): ").lower()
            if choice in ['y', 'n']:
                if choice == 'n':
                    print("Keeping existing calibration.")
                    return
                break
    
    # Run calibration
    keep_files = input("\nKeep test files after calibration? (y/n): ").lower() == 'y'
    calibration_manager.calibrate(keep_test_files=keep_files)

if __name__ == "__main__":
    main()