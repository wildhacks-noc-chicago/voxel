import logging
import os
import sys
import time

import pyautogui

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='pyautogui_commands.log'
)
logger = logging.getLogger("PyAutoGUICommandExecutor")

class PyAutoGUICommandExecutor:
    """Executes voice commands using PyAutoGUI to control mouse and keyboard"""
    
    def __init__(self, move_distance=100):
        """Initialize with default movement distance"""
        self.move_distance = move_distance
        
        # Configure PyAutoGUI safety features
        pyautogui.PAUSE = 0.5  # 500ms pause between commands
        pyautogui.FAILSAFE = True  # Move mouse to top-left to abort
        
        # Store current mouse position for relative movements
        self.current_x, self.current_y = pyautogui.position()
        
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
            "enter": self.left_click,
            "left click": self.left_click,
            "right click": self.right_click,
            
            # Exit command
            "exit": self.exit_program,
            "quit": self.exit_program,
            "stop listening": self.exit_program,
        }
        
        logger.info("PyAutoGUI Command Executor initialized with simplified mouse commands")
    
    def execute_command(self, command):
        """Execute a voice command using PyAutoGUI"""
        # Update current mouse position
        self.current_x, self.current_y = pyautogui.position()
        
        # Check if command exists
        if command in self.commands:
            logger.info(f"Executing command: {command}")
            
            # Execute the command function
            should_continue = self.commands[command]()
            
            # Return whether the program should continue running
            return should_continue
        else:
            logger.warning(f"Unknown command: {command}")
            print(f"Unknown command: {command}")
            return True
    
    # Mouse movement commands
    def move_right(self):
        """Move cursor to the right"""
        pyautogui.moveRel(self.move_distance, 0)
        logger.info(f"Moved cursor right by {self.move_distance}px")
        return True
    
    def move_left(self):
        """Move cursor to the left"""
        pyautogui.moveRel(-self.move_distance, 0)
        logger.info(f"Moved cursor left by {self.move_distance}px")
        return True
    
    def move_up(self):
        """Move cursor up"""
        pyautogui.moveRel(0, -self.move_distance)
        logger.info(f"Moved cursor up by {self.move_distance}px")
        return True
    
    def move_down(self):
        """Move cursor down"""
        pyautogui.moveRel(0, self.move_distance)
        logger.info(f"Moved cursor down by {self.move_distance}px")
        return True
    
    # Mouse click commands
    def left_click(self):
        """Perform left click at current position"""
        pyautogui.click()
        logger.info(f"Left click at ({self.current_x}, {self.current_y})")
        return True
    
    def right_click(self):
        """Perform right click at current position"""
        pyautogui.rightClick()
        logger.info(f"Right click at ({self.current_x}, {self.current_y})")
        return True
    
    # Exit command
    def exit_program(self):
        """Exit the program"""
        logger.info("Exit command received")
        print("Exiting program...")
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