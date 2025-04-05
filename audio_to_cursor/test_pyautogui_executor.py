import time

from pyautogui_command_executor import PyAutoGUICommandExecutor


def test_basic_commands():
    """Test basic mouse and keyboard commands"""
    executor = PyAutoGUICommandExecutor()
    
    print("Starting PyAutoGUI Command Executor Test")
    print("-----------------------------------------")
    
    # Wait a moment for user to position their cursor
    print("Please position your cursor somewhere on screen.")
    print("Testing will begin in 3 seconds...")
    time.sleep(3)
    
    # Test movement commands
    print("\nTesting movement commands:")
    for direction in ["right", "down", "left", "up"]:
        print(f"Moving {direction}...")
        executor.execute_command(direction)
        time.sleep(0.5)
    
    # Test click
    print("\nTesting click (will click at current position)...")
    time.sleep(1)
    executor.execute_command("click")
    
    # Test keyboard commands
    print("\nTesting keyboard commands:")
    for key in ["press space", "press tab", "press enter"]:
        print(f"Pressing {key}...")
        executor.execute_command(key)
        time.sleep(0.5)
    
    print("\nTest complete!")

if __name__ == "__main__":
    test_basic_commands() 