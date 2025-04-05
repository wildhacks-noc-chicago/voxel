# Voice Control System

A Python-based voice control system for controlling mouse movements and browser actions using voice commands.

## Features

- **Mouse Control**: Move cursor, perform clicks
- **Browser Control**: Open/close tabs, navigate to websites
- **Custom Shortcuts**: Create voice shortcuts to frequently visited websites
- **Configurable**: Easy to customize through configuration file
- **Agentic Voice Control**: Understand natural language instructions without requiring exact command phrases
- **Command Logging**: Track voice commands and system interpretations
- **Gemini AI Integration**: Leverages Google's Gemini AI for advanced natural language understanding
- **Multiple Speech Recognition Engines**: Choose between Google, Whisper, or Sphinx for speech recognition

## Requirements

- Python 3.6+
- Required Python packages:
  - SpeechRecognition
  - PyAutoGUI
  - pynput
  - pyaudio (for microphone access)
  - requests (for Gemini API calls)
  - openai-whisper (optional, for Whisper speech recognition)
  - pocketsphinx (optional, for Sphinx speech recognition)
- For Gemini-powered mode: Google Gemini API key

## Installation

1. Clone this repository
2. Install required packages:
```
pip install SpeechRecognition pyautogui pynput pyaudio requests
```

Note: On macOS, you may need to install the PortAudio library first:
```
brew install portaudio
```

3. For Gemini-powered mode, create a `.env` file in the project directory with your API key:
```
GEMINI_API_KEY=your_api_key_here
```

4. For enhanced speech recognition, install additional packages:
```
# For OpenAI Whisper (better accuracy but requires more resources)
pip install openai-whisper

# For CMU Sphinx (works offline but less accurate)
pip install pocketsphinx
```

## Voice Control Modes

### Basic Mode
Run the standard voice control system that requires exact command phrases:
```
python voice_control.py
```

### Agentic Mode (Pattern-Based)
Run the enhanced voice control system that can understand natural language using regex patterns:
```
python agentic_voice_control.py
```

The agentic mode includes:
- Natural language understanding for commands
- Fuzzy matching for similar phrases
- Command logging and intent recognition
- Support for conversational voice commands

### Gemini Mode (AI-Powered)
Run the AI-powered voice control system using Google's Gemini API:
```
python gemini_voice_control.py
```

Features of Gemini mode:
- Advanced natural language understanding with Google's Generative AI
- Contextual awareness with command history tracking
- Improved intent mapping with detailed command descriptions
- Enhanced accuracy through optimized prompt engineering
- Handles variations, misspellings, and ambiguous commands
- Automatically uses the API key from your `.env` file

### Testing Mode
To test the voice control systems without using a microphone:
```
python test_agentic_voice.py  # For pattern-based agentic mode
python test_gemini_voice.py   # For Gemini AI-powered mode
```

## Speech Recognition Engines

You can choose between different speech recognition engines:

### Google Speech Recognition (Default)
- Good accuracy for most use cases
- Requires internet connection
- Fast and reliable

### OpenAI Whisper
- Better accuracy, especially in noisy environments
- Can handle accents and different speaking styles better
- More resource-intensive
- Slightly slower response time

### CMU Sphinx
- Works completely offline
- Lower accuracy than cloud-based solutions
- Good for privacy-conscious users

To change the speech engine in the config file:
```json
{
    "speech_engine": "whisper",  // Options: "google", "whisper", "sphinx"
    "whisper_model": "base"      // Options: "tiny", "base", "small", "medium", "large"
}
```

Or programmatically:
```python
voice_control.set_speech_engine("whisper", "base")
```

## Available Voice Commands

### Mouse Commands:
- **Basic**: "Move cursor right/left/up/down", "Click", "Left click", "Right click", "Double click"
- **Natural Language**: "Go right", "Take it to the left", "Higher please", "Lower it", "Press here", etc.

### Browser Commands:
- **Basic**: "Open new tab", "Close this tab", "Open an incognito window"
- **Natural Language**: "Create tab", "New tab please", "Close current tab", "Go incognito", etc.

### Website Navigation:
- **Basic**: "Go to [shortcut]"
- **Natural Language**: "Open [shortcut]", "Take me to [shortcut]", "Visit [shortcut]", etc.

### System Commands:
- **Basic**: "Exit" / "Quit" / "Stop"
- **Natural Language**: "Close the program", "End session", "Shut down", etc.

## Configuration

The system is configured through `voice_config.json`:

- `move_distance`: Distance in pixels for cursor movement (default: 20)
- `command_timeout`: Timeout for voice command detection in seconds (default: 5)
- `speech_engine`: Speech recognition engine to use (default: "google")
- `whisper_model`: Whisper model size to use (default: "base")
- `shortcuts`: Dictionary of website shortcuts (e.g., "google": "google.com")

## Adding Custom Website Shortcuts

You can add shortcuts in two ways:

1. Edit the `voice_config.json` file directly
2. Use the helper script:
```
python add_shortcut.py add google google.com
```

To list all shortcuts:
```
python add_shortcut.py list
```

To remove a shortcut:
```
python add_shortcut.py remove google
```

## Logging

The system now provides comprehensive logging:

### Speech Recognition Log
- Located at: `speech_recognition.log`
- Contains detailed information about:
  - Raw speech recognition results
  - Engine performance and errors
  - Command execution

### Command Interpretation Log
- Located at: `voice_logs.txt` (Gemini mode)
- Contains:
  - Timestamp
  - Raw voice command
  - Interpreted command after AI processing

These logs can be analyzed to improve command recognition and understand user patterns.

## Comparing Agentic vs. Gemini Modes

| Feature | Agentic Mode | Gemini Mode |
|---------|-------------|------------|
| Natural language | ✓ (Pattern-based) | ✓ (AI-powered) |
| Contextual awareness | ✗ | ✓ (Command history) |
| Works offline | ✓ | ✗ (Requires API) |
| Handles variations | Limited | Extensive |
| Handles misspellings | Limited | Extensive |
| Command descriptions | ✗ | ✓ |
| Setup complexity | Simple | Requires API key |
| Response speed | Fast | Depends on API |
| Cost | Free | API usage fees |
| Model used | N/A | Google Generative AI |

## Comparing Speech Recognition Engines

| Feature | Google | Whisper | Sphinx |
|---------|--------|---------|--------|
| Accuracy | Good | Excellent | Fair |
| Works offline | ✗ | ✓ | ✓ |
| Resource usage | Low | High | Medium |
| Response time | Fast | Medium | Fast |
| Language support | Many | Many | Limited |

## Troubleshooting

- Ensure your microphone is working properly
- Check that you have an active internet connection (needed for Google speech recognition and Gemini API)
- If using macOS, ensure your terminal/application has microphone permissions
- Review the voice logs to see how your commands are being interpreted
- For Gemini mode, make sure your `.env` file contains a valid API key
- For API errors, verify that your API endpoint URL is correct
- Check speech_recognition.log for detailed error messages

## Future Enhancements

- System-wide hotkey to activate/deactivate voice control
- Support for more offline speech recognition engines
- Advanced mouse gestures and patterns
- Machine learning for personalized command recognition
- Multi-language support
- Browser extension integration