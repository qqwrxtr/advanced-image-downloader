import os
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtGui import QIcon

# This is the section to modify in your image_downloader.py file
# Find the ImageDownloader class and update the __init__ method

class ImageDownloader(QMainWindow):
    # ... existing code ...
    
    def __init__(self):
        super().__init__()
        
        # Load settings
        self.settings = Settings.load()
        
        # Setup UI
        self.setWindowTitle("Image Downloader")
        self.setMinimumSize(600, 550)
        self.setStyleSheet(StyleHelper.get_stylesheet())
        
        # Set custom icon
        self.set_application_icon()
        
        # ... rest of your existing initialization code ...
    
    def set_application_icon(self):
        """Set the application icon from available icon files"""
        # Look for icon in different formats
        icon_paths = [
            "app_icon.ico",  # Converted from webp
            "icon.webp",     # Original webp file
            "icon.png",      # In case you have PNG
            "icon.ico"       # In case you have ICO directly
        ]
        
        for icon_path in icon_paths:
            if os.path.exists(icon_path):
                try:
                    app_icon = QIcon(icon_path)
                    self.setWindowIcon(app_icon)
                    # Also set for the application
                    QApplication.setWindowIcon(app_icon)
                    break
                except Exception as e:
                    print(f"Error setting icon from {icon_path}: {e}")
    
    # ... rest of your class code ...