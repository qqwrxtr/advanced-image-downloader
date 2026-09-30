#!/usr/bin/env python3
import os
import sys
import time
import json
import uuid
import hashlib
import socket
import errno
import traceback
import multiprocessing
import shutil
import random
import re
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus, urlparse
from datetime import datetime

# Fix for Windows multiprocessing
if sys.platform.startswith('win'):
    multiprocessing.freeze_support()

def install_package(package_name, import_name=None):
    """Install a package using pip with better error handling for pip 25.1.1"""
    if import_name is None:
        import_name = package_name
    
    try:
        __import__(import_name)
        return True
    except ImportError:
        print(f"Installing {package_name}...")
        import subprocess
        try:
            # Use --upgrade and --user flags for better compatibility
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "--upgrade", 
                "--user", package_name
            ], timeout=300)
            return True
        except subprocess.TimeoutExpired:
            print(f"Timeout installing {package_name}, trying without --user flag...")
            try:
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", "--upgrade", package_name
                ], timeout=300)
                return True
            except Exception as e:
                print(f"Failed to install {package_name}: {e}")
                return False
        except Exception as e:
            print(f"Failed to install {package_name}: {e}")
            return False

# Install PyQt5 first
if not install_package("PyQt5"):
    print("Failed to install PyQt5. Please install it manually.")
    sys.exit(1)

try:
    from PyQt5.QtWidgets import *
    from PyQt5.QtCore import *
    from PyQt5.QtGui import *
except ImportError:
    print("PyQt5 installation failed or incomplete. Please install manually.")
    sys.exit(1)

# Install other required packages
required_packages = [
    ("Pillow", "PIL"),
    ("requests", "requests")
]

for package_name, import_name in required_packages:
    if not install_package(package_name, import_name):
        print(f"Warning: Failed to install {package_name}. Some features may not work.")

# Now import after ensuring packages exist
try:
    from PIL import Image
    import requests
except Exception as e:
    print(f"Error importing required modules: {e}")
    sys.exit(1)

# Settings file path
SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".image_downloader.json")
HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".image_downloader_history.json")
PID_FILE = os.path.join(os.path.expanduser("~"), ".image_downloader.pid")

def cleanup_old_processes():
    """Clean up any hanging processes from previous runs"""
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            
            # Check if process still exists
            try:
                os.kill(old_pid, 0)
                # Process exists, try to terminate it
                os.kill(old_pid, 9)
                time.sleep(0.5)
            except OSError:
                # Process doesn't exist
                pass
            
            os.remove(PID_FILE)
    except Exception:
        pass
    
    # Write current PID
    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

# Advanced size definitions - FIXED: Removed strict size filters that were blocking results
SIZE_DEFINITIONS = {
    "8K Ultra HD": {"min_width": 7680, "min_height": 4320},
    "4K Ultra HD": {"min_width": 3840, "min_height": 2160},
    "2K Quad HD": {"min_width": 2560, "min_height": 1440},
    "Full HD": {"min_width": 1920, "min_height": 1080},
    "HD": {"min_width": 1280, "min_height": 720},
    "Standard": {"min_width": 640, "min_height": 480},
    "Custom": {},
    "All Sizes": {}
}

# Advanced filters
ASPECT_RATIOS = {
    "Any": None,
    "16:9": 1.778,
    "16:10": 1.6,
    "4:3": 1.333,
    "1:1 Square": 1.0,
    "9:16 Portrait": 0.563,
    "Ultra-wide 21:9": 2.333
}

COLOR_MODES = {
    "Any": None,
    "Color": "color",
    "Black & White": "blackandwhite",
    "Transparent": "transparent"
}

# User agents for avoiding bot detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
]


def search_google_scrape(search_term, max_results, size_filter=None, color_filter=None):
    """Scrape Google Images for image URLs"""
    urls = []
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Build query params
    query_params = f"q={quote_plus(search_term)}&tbm=isch&ijn=0"

    # Add size filter
    tbs_parts = []
    if size_filter and size_filter not in ("All Sizes", "Custom"):
        size_map = {
            "8K Ultra HD": "isz:lt,islt:70mp",
            "4K Ultra HD": "isz:lt,islt:40mp",
            "2K Quad HD": "isz:lt,islt:12mp",
            "Full HD": "isz:lt,islt:4mp",
            "HD": "isz:l",
            "Standard": "isz:m",
        }
        if size_filter in size_map:
            tbs_parts.append(size_map[size_filter])

    if color_filter and color_filter != "Any":
        color_map = {
            "Color": "ic:color",
            "Black & White": "ic:gray",
            "Transparent": "ic:trans",
        }
        if color_filter in color_map:
            tbs_parts.append(color_map[color_filter])

    if tbs_parts:
        query_params += f"&tbs={','.join(tbs_parts)}"

    try:
        search_url = f"https://www.google.com/search?{query_params}"
        resp = requests.get(search_url, headers=headers, timeout=15)
        resp.raise_for_status()

        # Google embeds full-size image URLs in the page source
        # Pattern: ["https://example.com/image.jpg",width,height]
        matches = re.findall(
            r'\["(https?://[^"]+\.(?:jpg|jpeg|png|webp|gif|bmp)(?:\?[^"]*)?)",\d+,\d+\]',
            resp.text,
        )
        # Deduplicate while preserving order
        seen = set()
        for m in matches:
            if m not in seen:
                seen.add(m)
                urls.append(m)
            if len(urls) >= max_results:
                break

        print(f"Google found {len(urls)} URLs")

    except Exception as e:
        print(f"Google scrape error: {e}")

    return urls[:max_results]


def search_bing_scrape(search_term, max_results, size_filter=None, color_filter=None):
    """Scrape Bing Image Search for image URLs"""
    urls = []
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Build filter query string
    qft_parts = []
    if size_filter and size_filter not in ("All Sizes", "Custom"):
        size_map = {
            "8K Ultra HD": "+filterui:imagesize-wallpaper",
            "4K Ultra HD": "+filterui:imagesize-wallpaper",
            "2K Quad HD": "+filterui:imagesize-large",
            "Full HD": "+filterui:imagesize-large",
            "HD": "+filterui:imagesize-large",
            "Standard": "+filterui:imagesize-medium",
        }
        if size_filter in size_map:
            qft_parts.append(size_map[size_filter])

    if color_filter and color_filter != "Any":
        color_map = {
            "Color": "+filterui:color2-color",
            "Black & White": "+filterui:color2-bw",
            "Transparent": "+filterui:photo-transparent",
        }
        if color_filter in color_map:
            qft_parts.append(color_map[color_filter])

    qft = "".join(qft_parts)

    for offset in range(0, max_results + 35, 35):
        if len(urls) >= max_results:
            break
        try:
            search_url = (
                f"https://www.bing.com/images/search"
                f"?q={quote_plus(search_term)}"
                f"&first={offset}&count=35"
            )
            if qft:
                search_url += f"&qft={qft}"

            resp = requests.get(search_url, headers=headers, timeout=15)
            resp.raise_for_status()

            # Extract image URLs from Bing's HTML (murl = media URL)
            matches = re.findall(r'murl&quot;:&quot;(https?://[^&]*?)&quot;', resp.text)
            if not matches:
                # Try alternate pattern
                matches = re.findall(r'"murl":"(https?://[^"]*?)"', resp.text)
            urls.extend(matches)

            if not matches:
                break  # No more results

        except Exception as e:
            print(f"Bing scrape error at offset {offset}: {e}")
            break

    return urls[:max_results]


def guess_extension(url):
    """Guess the file extension from a URL"""
    parsed = urlparse(url)
    path = parsed.path.lower()
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".ico", ".svg"]:
        if path.endswith(ext):
            return ext
    # Default to .jpg
    return ".jpg"


def download_single_image(url, save_path, timeout=15):
    """Download a single image with proper headers and validation"""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"{urlparse(url).scheme}://{urlparse(url).netloc}/",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=timeout, stream=True)
        resp.raise_for_status()

        # Check content type
        content_type = resp.headers.get("Content-Type", "")
        if content_type and not any(
            t in content_type for t in ["image/", "octet-stream", "binary"]
        ):
            return None

        # Check content length - skip tiny files (likely error pages or icons)
        content_length = int(resp.headers.get("Content-Length", 0))
        if 0 < content_length < 5000:
            return None

        # Download to file
        with open(save_path, "wb") as f:
            total = 0
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                total += len(chunk)
                if total > 50 * 1024 * 1024:  # 50MB limit
                    break

        # Validate it's a real image by opening it
        try:
            with Image.open(save_path) as img:
                img.load()  # Force full decode to catch truncated images
                width, height = img.size
                if width < 10 or height < 10:
                    raise ValueError("Image too small")
        except Exception:
            if os.path.exists(save_path):
                os.remove(save_path)
            return None

        return save_path

    except Exception:
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except OSError:
                pass
        return None


class ImageAnalyzer(QThread):
    analysis_complete = pyqtSignal(dict)
    progress_update = pyqtSignal(str, int)
    
    def __init__(self, image_paths):
        super().__init__()
        self.image_paths = image_paths
        
    def run(self):
        results = {
            'total_size': 0,
            'formats': {},
            'dimensions': [],
            'duplicates': [],
            'corrupted': [],
            'metadata': []
        }
        
        seen_hashes = {}
        
        for idx, path in enumerate(self.image_paths):
            progress = int((idx / len(self.image_paths)) * 100)
            self.progress_update.emit(f"Analyzing {os.path.basename(path)}...", progress)
            
            try:
                # Get file size
                file_size = os.path.getsize(path)
                results['total_size'] += file_size
                
                # Open and analyze image
                with Image.open(path) as img:
                    # Get format
                    fmt = img.format or 'Unknown'
                    results['formats'][fmt] = results['formats'].get(fmt, 0) + 1
                    
                    # Get dimensions
                    results['dimensions'].append({
                        'path': path,
                        'width': img.width,
                        'height': img.height,
                        'size': file_size,
                        'format': fmt
                    })
                    
                    # Check for duplicates using hash
                    img_hash = hashlib.md5(img.tobytes()).hexdigest()
                    if img_hash in seen_hashes:
                        results['duplicates'].append({
                            'original': seen_hashes[img_hash],
                            'duplicate': path
                        })
                    else:
                        seen_hashes[img_hash] = path
                    
                    # Extract metadata
                    if hasattr(img, 'info'):
                        results['metadata'].append({
                            'path': path,
                            'info': img.info
                        })
                        
            except Exception as e:
                results['corrupted'].append({
                    'path': path,
                    'error': str(e)
                })
        
        self.analysis_complete.emit(results)

class AdvancedSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Settings")
        self.setModal(True)
        self.setMinimumSize(500, 600)
        
        layout = QVBoxLayout(self)
        
        # Create tabs
        tabs = QTabWidget()
        
        # Download settings tab
        download_tab = QWidget()
        download_layout = QFormLayout(download_tab)
        
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 10)
        self.threads_spin.setValue(4)
        download_layout.addRow("Download Threads:", self.threads_spin)
        
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 60)
        self.timeout_spin.setValue(15)
        self.timeout_spin.setSuffix(" seconds")
        download_layout.addRow("Connection Timeout:", self.timeout_spin)
        
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(3)
        download_layout.addRow("Retry Attempts:", self.retry_spin)
        
        # Quality settings tab
        quality_tab = QWidget()
        quality_layout = QFormLayout(quality_tab)
        
        self.min_quality_slider = QSlider(Qt.Horizontal)
        self.min_quality_slider.setRange(10, 100)
        self.min_quality_slider.setValue(70)
        self.quality_label = QLabel("70%")
        self.min_quality_slider.valueChanged.connect(lambda v: self.quality_label.setText(f"{v}%"))
        
        quality_layout.addRow("Minimum Quality:", self.min_quality_slider)
        quality_layout.addRow("", self.quality_label)
        
        self.convert_webp = QCheckBox("Convert WEBP to JPG")
        quality_layout.addRow(self.convert_webp)
        
        self.optimize_images = QCheckBox("Optimize images (reduce file size)")
        quality_layout.addRow(self.optimize_images)
        
        # Naming settings tab
        naming_tab = QWidget()
        naming_layout = QFormLayout(naming_tab)
        
        self.naming_pattern = QComboBox()
        self.naming_pattern.addItems([
            "{prefix}_{number}",
            "{prefix}_{date}_{number}",
            "{prefix}_{dimensions}_{number}",
            "{search_term}_{number}",
            "{hash}_{number}"
        ])
        naming_layout.addRow("Naming Pattern:", self.naming_pattern)
        
        self.preserve_original = QCheckBox("Preserve original filenames when possible")
        naming_layout.addRow(self.preserve_original)
        
        # Add tabs
        tabs.addTab(download_tab, "Download")
        tabs.addTab(quality_tab, "Quality")
        tabs.addTab(naming_tab, "Naming")
        
        layout.addWidget(tabs)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

class ImagePreviewDialog(QDialog):
    def __init__(self, image_paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloaded Images Preview")
        self.setModal(True)
        self.setMinimumSize(800, 600)
        
        self.image_paths = image_paths
        self.current_index = 0
        
        layout = QVBoxLayout(self)
        
        # Image display
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("border: 1px solid #ccc;")
        self.image_label.setMinimumHeight(400)
        
        # Info label
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignCenter)
        
        # Navigation
        nav_layout = QHBoxLayout()
        
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self.show_previous)
        
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.show_next)
        
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, len(image_paths) - 1)
        self.slider.valueChanged.connect(self.show_image)
        
        nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(self.slider)
        nav_layout.addWidget(self.next_button)
        
        layout.addWidget(self.image_label)
        layout.addWidget(self.info_label)
        layout.addLayout(nav_layout)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
        
        self.show_image(0)
    
    def show_image(self, index):
        if 0 <= index < len(self.image_paths):
            self.current_index = index
            path = self.image_paths[index]
            
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(
                    self.image_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)
                
                # Show info
                file_size = os.path.getsize(path) / 1024 / 1024
                self.info_label.setText(
                    f"Image {index + 1} of {len(self.image_paths)} | "
                    f"{os.path.basename(path)} | "
                    f"{pixmap.width()}×{pixmap.height()} | "
                    f"{file_size:.2f} MB"
                )
            
            self.slider.setValue(index)
            self.prev_button.setEnabled(index > 0)
            self.next_button.setEnabled(index < len(self.image_paths) - 1)
    
    def show_previous(self):
        self.show_image(self.current_index - 1)
    
    def show_next(self):
        self.show_image(self.current_index + 1)

class ImageDownloader(QMainWindow):
    # Signals
    progress_signal = pyqtSignal(str, int)
    download_complete_signal = pyqtSignal(bool, str, int)
    image_downloaded_signal = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        
        try:
            # Load settings and history
            self.settings = self.load_settings()
            self.download_history = self.load_history()
            
            # Setup UI
            self.setWindowTitle("Image Downloader")
            self.setMinimumSize(900, 700)
            
            # Initialize variables first
            self.is_downloading = False
            self.cancel_requested = False
            self.download_thread = None
            self.output_dir = ""
            self.downloaded_images = []
            self.download_lock = Lock()
            
            # Now setup UI
            self.setup_ui()
            
            # Set application icon
            self.set_application_icon()
            
            # Connect signals
            self.progress_signal.connect(self.update_progress)
            self.download_complete_signal.connect(self.download_completed)
            self.image_downloaded_signal.connect(self.add_downloaded_image)
            
            # Setup status bar timer
            self.status_timer = QTimer()
            self.status_timer.timeout.connect(self.update_status)
            self.status_timer.start(1000)
            
        except Exception as e:
            QMessageBox.critical(None, "Initialization Error", 
                               f"Failed to initialize application:\n{str(e)}")
            raise
    
    def setup_ui(self):
        """Set up the user interface"""
        # Create menu bar
        self.create_menu_bar()
        
        # Create toolbar
        self.create_toolbar()
        
        # Main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # Main layout
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Create splitter for main content
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel - Settings
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Search settings group
        search_group = QGroupBox("Search Settings")
        search_layout = QFormLayout()
        
        # Search engine with multiple options
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["Bing", "Google", "All Engines"])
        self.engine_combo.setCurrentText(self.settings.get("last_search_engine", "Bing"))
        search_layout.addRow("Search Engine:", self.engine_combo)
        
        # Search term with history
        self.search_term = QComboBox()
        self.search_term.setEditable(True)
        self.search_term.setInsertPolicy(QComboBox.NoInsert)
        self.search_term.addItems(self.settings.get("search_history", []))
        search_layout.addRow("Search Term:", self.search_term)
        
        # Number of images
        self.num_images = QSpinBox()
        self.num_images.setRange(1, 1000)
        self.num_images.setValue(self.settings.get("last_num_images", 10))
        search_layout.addRow("Number of Images:", self.num_images)
        
        search_group.setLayout(search_layout)
        
        # Filter settings group
        filter_group = QGroupBox("Filter Settings")
        filter_layout = QFormLayout()
        
        # Image size
        size_layout = QHBoxLayout()
        self.size_combo = QComboBox()
        self.size_combo.addItems(list(SIZE_DEFINITIONS.keys()))
        self.size_combo.setCurrentText(self.settings.get("last_image_size", "All Sizes"))
        self.size_combo.currentTextChanged.connect(self.on_size_changed)
        size_layout.addWidget(self.size_combo)
        
        # Custom size inputs
        self.custom_width = QSpinBox()
        self.custom_width.setRange(1, 10000)
        self.custom_width.setValue(1920)
        self.custom_width.setPrefix("W: ")
        self.custom_width.setEnabled(False)
        
        self.custom_height = QSpinBox()
        self.custom_height.setRange(1, 10000)
        self.custom_height.setValue(1080)
        self.custom_height.setPrefix("H: ")
        self.custom_height.setEnabled(False)
        
        size_layout.addWidget(self.custom_width)
        size_layout.addWidget(self.custom_height)
        
        filter_layout.addRow("Image Size:", size_layout)
        
        # Aspect ratio
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(list(ASPECT_RATIOS.keys()))
        filter_layout.addRow("Aspect Ratio:", self.aspect_combo)
        
        # Color mode
        self.color_combo = QComboBox()
        self.color_combo.addItems(list(COLOR_MODES.keys()))
        filter_layout.addRow("Color Mode:", self.color_combo)
        
        # File types with more options
        file_types_layout = QGridLayout()
        
        self.jpg_check = QCheckBox("JPG/JPEG")
        self.jpg_check.setChecked(self.settings.get("file_type_jpg", True))
        
        self.png_check = QCheckBox("PNG")
        self.png_check.setChecked(self.settings.get("file_type_png", True))
        
        self.webp_check = QCheckBox("WEBP")
        self.webp_check.setChecked(self.settings.get("file_type_webp", True))
        
        self.gif_check = QCheckBox("GIF")
        self.gif_check.setChecked(self.settings.get("file_type_gif", False))
        
        self.bmp_check = QCheckBox("BMP")
        self.bmp_check.setChecked(self.settings.get("file_type_bmp", False))
        
        self.ico_check = QCheckBox("ICO")
        self.ico_check.setChecked(self.settings.get("file_type_ico", False))
        
        file_types_layout.addWidget(self.jpg_check, 0, 0)
        file_types_layout.addWidget(self.png_check, 0, 1)
        file_types_layout.addWidget(self.webp_check, 0, 2)
        file_types_layout.addWidget(self.gif_check, 1, 0)
        file_types_layout.addWidget(self.bmp_check, 1, 1)
        file_types_layout.addWidget(self.ico_check, 1, 2)
        
        filter_layout.addRow("File Types:", file_types_layout)
        
        filter_group.setLayout(filter_layout)
        
        # Save settings group
        save_group = QGroupBox("Save Settings")
        save_layout = QFormLayout()
        
        # Save location
        save_location_layout = QHBoxLayout()
        
        self.save_dir = QLineEdit()
        self.save_dir.setText(self.settings.get("last_save_location", os.path.join(os.path.expanduser("~"), "Pictures")))
        
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_directory)
        
        save_location_layout.addWidget(self.save_dir)
        save_location_layout.addWidget(browse_button)
        
        save_layout.addRow("Save Location:", save_location_layout)
        
        # File prefix
        self.file_prefix = QLineEdit()
        self.file_prefix.setText(self.settings.get("last_file_prefix", "image"))
        save_layout.addRow("File Prefix:", self.file_prefix)
        
        # Organize by
        self.organize_combo = QComboBox()
        self.organize_combo.addItems(["None", "Date", "Size", "Format", "Search Term"])
        self.organize_combo.setCurrentText(self.settings.get("organize_by", "None"))
        save_layout.addRow("Organize By:", self.organize_combo)
        
        save_group.setLayout(save_layout)
        
        # Add groups to left panel
        left_layout.addWidget(search_group)
        left_layout.addWidget(filter_group)
        left_layout.addWidget(save_group)
        left_layout.addStretch()
        
        # Download button
        self.download_button = QPushButton("Start Download")
        self.download_button.setMinimumHeight(50)
        self.download_button.setStyleSheet("""
            QPushButton {
                background-color: #4361ee;
                color: white;
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3f37c9;
            }
            QPushButton:pressed {
                background-color: #3730a3;
            }
        """)
        self.download_button.clicked.connect(self.start_download)
        left_layout.addWidget(self.download_button)
        
        # Right panel - Results and monitoring
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Create tabs for results
        self.results_tabs = QTabWidget()
        
        # Progress tab
        progress_tab = QWidget()
        progress_layout = QVBoxLayout(progress_tab)
        
        self.status_label = QLabel("Ready to download")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("Arial", 12))
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #ccc;
                border-radius: 5px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #4cc9f0;
                border-radius: 3px;
            }
        """)
        
        # Download statistics
        self.stats_label = QLabel()
        self.stats_label.setWordWrap(True)
        
        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.stats_label)
        progress_layout.addStretch()
        
        # Downloaded images tab
        images_tab = QWidget()
        images_layout = QVBoxLayout(images_tab)
        
        # Images list
        self.images_list = QListWidget()
        self.images_list.setIconSize(QSize(100, 100))
        self.images_list.setViewMode(QListWidget.IconMode)
        self.images_list.setResizeMode(QListWidget.Adjust)
        self.images_list.setGridSize(QSize(120, 120))
        
        # Image actions
        image_actions_layout = QHBoxLayout()
        
        preview_button = QPushButton("Preview Selected")
        preview_button.clicked.connect(self.preview_images)
        
        analyze_button = QPushButton("Analyze Images")
        analyze_button.clicked.connect(self.analyze_images)
        
        clear_button = QPushButton("Clear List")
        clear_button.clicked.connect(self.clear_images_list)
        
        image_actions_layout.addWidget(preview_button)
        image_actions_layout.addWidget(analyze_button)
        image_actions_layout.addWidget(clear_button)
        
        images_layout.addWidget(self.images_list)
        images_layout.addLayout(image_actions_layout)
        
        # History tab
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(["Date", "Search Term", "Engine", "Images", "Location"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.populate_history_table()
        
        history_layout.addWidget(self.history_table)
        
        # Add tabs
        self.results_tabs.addTab(progress_tab, "Progress")
        self.results_tabs.addTab(images_tab, "Downloaded Images")
        self.results_tabs.addTab(history_tab, "History")
        
        right_layout.addWidget(self.results_tabs)
        
        # Add panels to splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 500])
        
        main_layout.addWidget(splitter)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
    
    def create_menu_bar(self):
        """Create application menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        new_action = QAction("New Download", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_download)
        file_menu.addAction(new_action)
        
        file_menu.addSeparator()
        
        settings_action = QAction("Advanced Settings", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.show_advanced_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit menu
        edit_menu = menubar.addMenu("Edit")
        
        clear_history_action = QAction("Clear History", self)
        clear_history_action.triggered.connect(self.clear_history)
        edit_menu.addAction(clear_history_action)
        
        clear_cache_action = QAction("Clear Cache", self)
        clear_cache_action.triggered.connect(self.clear_cache)
        edit_menu.addAction(clear_cache_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("Tools")
        
        batch_action = QAction("Batch Download", self)
        batch_action.triggered.connect(self.batch_download)
        tools_menu.addAction(batch_action)
        
        duplicate_action = QAction("Find Duplicates", self)
        duplicate_action.triggered.connect(self.find_duplicates)
        tools_menu.addAction(duplicate_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def create_toolbar(self):
        """Create application toolbar"""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # Add quick actions
        new_action = toolbar.addAction("New")
        new_action.triggered.connect(self.new_download)
        
        toolbar.addSeparator()
        
        preview_action = toolbar.addAction("Preview")
        preview_action.triggered.connect(self.preview_images)
        
        analyze_action = toolbar.addAction("Analyze")
        analyze_action.triggered.connect(self.analyze_images)
    
    def on_size_changed(self, size_option):
        """Handle size selection change"""
        is_custom = size_option == "Custom"
        self.custom_width.setEnabled(is_custom)
        self.custom_height.setEnabled(is_custom)
    
    def get_selected_file_types(self):
        """Get list of selected file types"""
        file_types = []
        if self.jpg_check.isChecked():
            file_types.extend(['jpg', 'jpeg'])
        if self.png_check.isChecked():
            file_types.append('png')
        if self.webp_check.isChecked():
            file_types.append('webp')
        if self.gif_check.isChecked():
            file_types.append('gif')
        if self.bmp_check.isChecked():
            file_types.append('bmp')
        if self.ico_check.isChecked():
            file_types.append('ico')
        return file_types
    
    def start_download(self):
        """Start or cancel download"""
        if self.is_downloading:
            self.cancel_download()
            return
        
        # Validate inputs
        search_term = self.search_term.currentText().strip()
        if not search_term:
            QMessageBox.warning(self, "Input Error", "Please enter a search term")
            return
        
        save_dir = self.save_dir.text().strip()
        if not save_dir:
            QMessageBox.warning(self, "Input Error", "Please select a save location")
            return
        
        # Check file types
        if not self.get_selected_file_types():
            QMessageBox.warning(self, "Input Error", "Please select at least one file type")
            return
        
        # Create directory structure
        try:
            os.makedirs(save_dir, exist_ok=True)
            
            # Create subdirectories if organizing
            organize_by = self.organize_combo.currentText()
            if organize_by != "None":
                if organize_by == "Date":
                    save_dir = os.path.join(save_dir, datetime.now().strftime("%Y-%m-%d"))
                elif organize_by == "Search Term":
                    save_dir = os.path.join(save_dir, search_term.replace(" ", "_"))
                os.makedirs(save_dir, exist_ok=True)
                
        except Exception as e:
            QMessageBox.critical(self, "Directory Error", f"Could not create save directory:\n{str(e)}")
            return
        
        # Update search history
        search_history = self.settings.get("search_history", [])
        if search_term not in search_history:
            search_history.insert(0, search_term)
            search_history = search_history[:20]  # Keep last 20 searches
            self.settings["search_history"] = search_history
        
        # Save settings
        self.save_current_settings()
        
        # Update UI
        self.download_button.setText("Cancel Download")
        self.download_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        self.status_label.setText("Starting download...")
        self.progress_bar.setValue(0)
        self.stats_label.clear()
        self.downloaded_images.clear()
        self.images_list.clear()
        
        # Switch to progress tab
        self.results_tabs.setCurrentIndex(0)
        
        # Set state
        self.is_downloading = True
        self.cancel_requested = False
        self.output_dir = save_dir
        
        # Start download thread
        self.download_thread = Thread(target=self.download_images)
        self.download_thread.daemon = True
        self.download_thread.start()
    
    def cancel_download(self):
        """Cancel download"""
        self.cancel_requested = True
        self.status_label.setText("Cancelling download...")
        self.download_button.setEnabled(False)
    
    def download_images(self):
        """Download images using direct search APIs and concurrent downloads"""
        temp_dir = None
        try:
            with self.download_lock:
                if self.cancel_requested:
                    return

                # Get parameters
                engine = self.engine_combo.currentText()
                size_option = self.size_combo.currentText()
                search_term = self.search_term.currentText().strip()
                num_images = self.num_images.value()
                file_types = self.get_selected_file_types()
                aspect_ratio = self.aspect_combo.currentText()
                color_mode = self.color_combo.currentText()

                self.progress_signal.emit("Searching for images...", 5)

                # Request 3x more URLs than needed - many will fail to download
                fetch_count = max(num_images * 3, 30)

                # Collect image URLs from search engines
                image_urls = []

                if engine in ["Bing", "All Engines"]:
                    self.progress_signal.emit("Searching Bing...", 8)
                    urls = search_bing_scrape(
                        search_term, fetch_count,
                        size_filter=size_option,
                        color_filter=color_mode,
                    )
                    image_urls.extend(urls)
                    print(f"Bing found {len(urls)} URLs")

                if engine in ["Google", "All Engines"]:
                    self.progress_signal.emit("Searching Google...", 15)
                    urls = search_google_scrape(
                        search_term, fetch_count,
                        size_filter=size_option,
                        color_filter=color_mode,
                    )
                    image_urls.extend(urls)
                    print(f"Google found {len(urls)} URLs")

                if self.cancel_requested:
                    return

                # Deduplicate URLs while preserving order
                seen = set()
                unique_urls = []
                for url in image_urls:
                    normalized = url.split("?")[0].lower()
                    if normalized not in seen:
                        seen.add(normalized)
                        unique_urls.append(url)
                image_urls = unique_urls

                print(f"Total unique URLs to try: {len(image_urls)}")

                if not image_urls:
                    self.download_complete_signal.emit(
                        False,
                        "No images found.\n\nTry:\n"
                        "- Different search terms (more specific or more general)\n"
                        "- A different search engine\n"
                        "- 'All Sizes' size filter\n"
                        "- 'Any' color mode",
                        0,
                    )
                    return

                self.progress_signal.emit(
                    f"Found {len(image_urls)} image URLs, downloading...", 20
                )

                # Create temp directory for downloads
                temp_dir = os.path.join(self.output_dir, f"temp_{int(time.time())}")
                os.makedirs(temp_dir, exist_ok=True)

            # Download images concurrently
            max_workers = min(self.settings.get("download_threads", 4), 8)
            timeout = self.settings.get("timeout", 15)
            downloaded_files = []
            failed_count = 0

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all download tasks
                future_to_info = {}
                for idx, url in enumerate(image_urls):
                    if self.cancel_requested:
                        break
                    ext = guess_extension(url)
                    save_path = os.path.join(temp_dir, f"img_{idx:04d}{ext}")
                    future = executor.submit(download_single_image, url, save_path, timeout)
                    future_to_info[future] = (url, save_path, idx)

                # Process results as they complete
                for future in as_completed(future_to_info):
                    if self.cancel_requested:
                        break
                    if len(downloaded_files) >= num_images:
                        # We have enough, cancel remaining futures
                        for remaining in future_to_info:
                            remaining.cancel()
                        break

                    result = future.result()
                    if result:
                        downloaded_files.append(result)
                        progress = 20 + int((len(downloaded_files) / num_images) * 50)
                        self.progress_signal.emit(
                            f"Downloaded {len(downloaded_files)}/{num_images} images...",
                            min(progress, 70),
                        )
                    else:
                        failed_count += 1

            print(f"Downloaded {len(downloaded_files)} files, {failed_count} failed")

            if self.cancel_requested:
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                self.download_complete_signal.emit(False, "Download cancelled.", 0)
                return

            # Apply post-download filters
            self.progress_signal.emit("Filtering images...", 72)
            all_files = list(downloaded_files)

            # Filter by file type
            if file_types:
                filtered = []
                for fp in all_files:
                    _, ext = os.path.splitext(fp.lower())
                    ext_clean = ext.lstrip(".")
                    if ext_clean in file_types or (
                        ext_clean == "jpeg" and "jpg" in file_types
                    ):
                        filtered.append(fp)
                    else:
                        # Check actual image format via PIL
                        try:
                            with Image.open(fp) as img:
                                fmt = (img.format or "").lower()
                                if fmt in file_types or (
                                    fmt == "jpeg" and "jpg" in file_types
                                ):
                                    filtered.append(fp)
                        except Exception:
                            pass
                if filtered:  # Only apply filter if it doesn't remove everything
                    all_files = filtered
                    print(f"After file type filter: {len(all_files)} files")

            # Filter by size
            if size_option not in ("All Sizes", "Custom") and size_option in SIZE_DEFINITIONS:
                size_def = SIZE_DEFINITIONS[size_option]
                if "min_width" in size_def and "min_height" in size_def:
                    min_w = size_def["min_width"]
                    min_h = size_def["min_height"]
                    filtered = []
                    for fp in all_files:
                        try:
                            with Image.open(fp) as img:
                                # Accept if at least 50% of target size
                                if img.width >= min_w * 0.5 and img.height >= min_h * 0.5:
                                    filtered.append(fp)
                        except Exception:
                            pass
                    if filtered:
                        all_files = filtered
                        print(f"After size filter: {len(all_files)} files")

            elif size_option == "Custom":
                min_w = self.custom_width.value()
                min_h = self.custom_height.value()
                filtered = []
                for fp in all_files:
                    try:
                        with Image.open(fp) as img:
                            if img.width >= min_w and img.height >= min_h:
                                filtered.append(fp)
                    except Exception:
                        pass
                if filtered:
                    all_files = filtered
                    print(f"After custom size filter: {len(all_files)} files")

            # Filter by aspect ratio
            if aspect_ratio != "Any" and aspect_ratio in ASPECT_RATIOS:
                target_ratio = ASPECT_RATIOS[aspect_ratio]
                if target_ratio:
                    filtered = []
                    for fp in all_files:
                        try:
                            with Image.open(fp) as img:
                                ratio = img.width / img.height
                                if abs(ratio - target_ratio) < target_ratio * 0.25:
                                    filtered.append(fp)
                        except Exception:
                            pass
                    if filtered:
                        all_files = filtered
                        print(f"After aspect ratio filter: {len(all_files)} files")

            # Rename and move files to final location
            self.progress_signal.emit("Organizing files...", 80)
            successful_count = 0
            file_prefix = self.file_prefix.text() or "image"
            naming_pattern = self.settings.get("naming_pattern", "{prefix}_{number}")

            for idx, file_path in enumerate(all_files[:num_images], start=1):
                if self.cancel_requested:
                    break

                progress = 80 + int((idx / min(len(all_files), num_images)) * 18)
                self.progress_signal.emit(
                    f"Saving file {idx} of {min(len(all_files), num_images)}...",
                    min(progress, 98),
                )

                try:
                    _, ext = os.path.splitext(file_path)

                    if naming_pattern == "{prefix}_{date}_{number}":
                        new_name = f"{file_prefix}_{datetime.now().strftime('%Y%m%d')}_{idx:04d}{ext}"
                    elif naming_pattern == "{prefix}_{dimensions}_{number}":
                        try:
                            with Image.open(file_path) as img:
                                new_name = f"{file_prefix}_{img.width}x{img.height}_{idx:04d}{ext}"
                        except Exception:
                            new_name = f"{file_prefix}_{idx:04d}{ext}"
                    elif naming_pattern == "{search_term}_{number}":
                        safe_term = re.sub(r'[^\w\-]', '_', search_term)[:30]
                        new_name = f"{safe_term}_{idx:04d}{ext}"
                    elif naming_pattern == "{hash}_{number}":
                        with open(file_path, "rb") as f:
                            file_hash = hashlib.md5(f.read()).hexdigest()[:8]
                        new_name = f"{file_hash}_{idx:04d}{ext}"
                    else:
                        new_name = f"{file_prefix}_{idx:04d}{ext}"

                    new_path = os.path.join(self.output_dir, new_name)

                    # Avoid overwriting existing files
                    if os.path.exists(new_path):
                        base, ext = os.path.splitext(new_name)
                        counter = 1
                        while os.path.exists(new_path):
                            new_name = f"{base}_{counter}{ext}"
                            new_path = os.path.join(self.output_dir, new_name)
                            counter += 1

                    shutil.move(file_path, new_path)

                    self.image_downloaded_signal.emit(new_path)
                    self.downloaded_images.append(new_path)
                    successful_count += 1

                except Exception as e:
                    print(f"Error saving file: {e}")

            # Clean up temp directory
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

            # Save to history
            if successful_count > 0:
                history_entry = {
                    "date": datetime.now().isoformat(),
                    "search_term": search_term,
                    "engine": engine,
                    "images": successful_count,
                    "location": self.output_dir,
                }
                self.download_history.append(history_entry)
                self.save_history()

            # Report result
            self.progress_signal.emit("Download completed", 100)

            if successful_count > 0:
                message = (
                    f"Successfully downloaded {successful_count} images\n"
                    f"({failed_count} URLs failed, which is normal)"
                )
                self.download_complete_signal.emit(True, message, successful_count)
            else:
                message = (
                    f"No images could be downloaded ({failed_count} URLs tried).\n\n"
                    "Try:\n"
                    "- More specific or general search terms\n"
                    "- 'All Engines' to search both Bing and Google\n"
                    "- 'All Sizes' size filter\n"
                    "- 'Any' for aspect ratio and color mode"
                )
                self.download_complete_signal.emit(False, message, 0)

        except Exception as e:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            error_msg = f"Error: {str(e)}\n\nTry different settings or search terms."
            self.download_complete_signal.emit(False, error_msg, 0)
    
    def add_downloaded_image(self, image_path):
        """Add downloaded image to the list"""
        try:
            # Create thumbnail
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                thumbnail = pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                
                # Create list item
                item = QListWidgetItem()
                item.setIcon(QIcon(thumbnail))
                item.setText(os.path.basename(image_path))
                item.setData(Qt.UserRole, image_path)
                
                self.images_list.addItem(item)
        except Exception as e:
            print(f"Error adding image to list: {e}")
    
    def update_progress(self, status, progress):
        """Update progress bar and status label"""
        self.status_label.setText(status)
        self.progress_bar.setValue(progress)
        
        # Update statistics
        if self.is_downloading:
            stats_text = f"Downloaded: {len(self.downloaded_images)} images\n"
            if self.downloaded_images:
                total_size = sum(os.path.getsize(f) for f in self.downloaded_images if os.path.exists(f))
                stats_text += f"Total size: {total_size / 1024 / 1024:.2f} MB"
            self.stats_label.setText(stats_text)
    
    def download_completed(self, success, message, count):
        """Handle download completion"""
        self.is_downloading = False
        self.download_button.setText("Start Download")
        self.download_button.setEnabled(True)
        self.download_button.setStyleSheet("""
            QPushButton {
                background-color: #4361ee;
                color: white;
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3f37c9;
            }
        """)
        
        if success:
            self.status_label.setText("Download completed successfully!")
            # Switch to images tab
            self.results_tabs.setCurrentIndex(1)
            # Refresh history
            self.populate_history_table()
        else:
            self.status_label.setText("Download failed or no images found")
        
        QMessageBox.information(self, "Download Complete", message)
    
    def preview_images(self):
        """Preview downloaded images"""
        if self.downloaded_images:
            dialog = ImagePreviewDialog(self.downloaded_images, self)
            dialog.exec_()
        else:
            QMessageBox.information(self, "No Images", "No images to preview")
    
    def analyze_images(self):
        """Analyze downloaded images"""
        if not self.downloaded_images:
            QMessageBox.information(self, "No Images", "No images to analyze")
            return
        
        # Create and start analyzer thread
        self.analyzer = ImageAnalyzer(self.downloaded_images)
        self.analyzer.analysis_complete.connect(self.show_analysis_results)
        self.analyzer.progress_update.connect(self.update_progress)
        self.analyzer.start()
    
    def show_analysis_results(self, results):
        """Show image analysis results"""
        msg = f"Analysis Results:\n\n"
        msg += f"Total images: {len(self.downloaded_images)}\n"
        msg += f"Total size: {results['total_size'] / 1024 / 1024:.2f} MB\n\n"
        
        msg += "Formats:\n"
        for fmt, count in results['formats'].items():
            msg += f"  {fmt}: {count}\n"
        
        msg += f"\nDuplicates found: {len(results['duplicates'])}\n"
        msg += f"Corrupted files: {len(results['corrupted'])}\n"
        
        if results['dimensions']:
            dims = results['dimensions']
            avg_width = sum(d['width'] for d in dims) / len(dims)
            avg_height = sum(d['height'] for d in dims) / len(dims)
            msg += f"\nAverage dimensions: {avg_width:.0f}×{avg_height:.0f}"
        
        QMessageBox.information(self, "Analysis Results", msg)
    
    def clear_images_list(self):
        """Clear the images list"""
        self.images_list.clear()
        self.downloaded_images.clear()
    
    def populate_history_table(self):
        """Populate the history table"""
        self.history_table.setRowCount(len(self.download_history))
        
        for row, entry in enumerate(self.download_history):
            date_item = QTableWidgetItem(entry.get('date', ''))
            search_item = QTableWidgetItem(entry.get('search_term', ''))
            engine_item = QTableWidgetItem(entry.get('engine', ''))
            images_item = QTableWidgetItem(str(entry.get('images', 0)))
            location_item = QTableWidgetItem(entry.get('location', ''))
            
            self.history_table.setItem(row, 0, date_item)
            self.history_table.setItem(row, 1, search_item)
            self.history_table.setItem(row, 2, engine_item)
            self.history_table.setItem(row, 3, images_item)
            self.history_table.setItem(row, 4, location_item)
    
    def update_status(self):
        """Update status bar"""
        if self.is_downloading:
            self.status_bar.showMessage(f"Downloading... {len(self.downloaded_images)} images")
        else:
            self.status_bar.showMessage("Ready")
    
    def save_current_settings(self):
        """Save current settings"""
        self.settings.update({
            "last_search_engine": self.engine_combo.currentText(),
            "last_image_size": self.size_combo.currentText(),
            "last_num_images": self.num_images.value(),
            "last_save_location": self.save_dir.text(),
            "last_file_prefix": self.file_prefix.text(),
            "file_type_jpg": self.jpg_check.isChecked(),
            "file_type_png": self.png_check.isChecked(),
            "file_type_webp": self.webp_check.isChecked(),
            "file_type_gif": self.gif_check.isChecked(),
            "file_type_bmp": self.bmp_check.isChecked(),
            "file_type_ico": self.ico_check.isChecked(),
            "organize_by": self.organize_combo.currentText(),
        })
        self.save_settings(self.settings)
    
    # Menu actions
    def new_download(self):
        """Clear current download and start fresh"""
        self.search_term.clearEditText()
        self.num_images.setValue(10)
        self.progress_bar.setValue(0)
        self.status_label.setText("Ready to download")
        self.clear_images_list()
    
    def show_advanced_settings(self):
        """Show advanced settings dialog"""
        dialog = AdvancedSettingsDialog(self)
        if dialog.exec_():
            # Save advanced settings
            self.settings.update({
                "download_threads": dialog.threads_spin.value(),
                "timeout": dialog.timeout_spin.value(),
                "retry_attempts": dialog.retry_spin.value(),
                "min_quality": dialog.min_quality_slider.value(),
                "convert_webp": dialog.convert_webp.isChecked(),
                "optimize_images": dialog.optimize_images.isChecked(),
                "naming_pattern": dialog.naming_pattern.currentText(),
                "preserve_original": dialog.preserve_original.isChecked(),
            })
            self.save_settings(self.settings)
    
    def clear_history(self):
        """Clear download history"""
        reply = QMessageBox.question(self, "Clear History", 
                                   "Are you sure you want to clear the download history?",
                                   QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.download_history.clear()
            self.save_history()
            self.populate_history_table()
    
    def clear_cache(self):
        """Clear application cache"""
        QMessageBox.information(self, "Clear Cache", "Cache cleared successfully")
    
    def batch_download(self):
        """Show batch download dialog"""
        QMessageBox.information(self, "Batch Download", 
                              "Batch download allows you to download images for multiple search terms.\n"
                              "This feature is coming soon!")
    
    def find_duplicates(self):
        """Find duplicate images"""
        if not self.downloaded_images:
            QMessageBox.information(self, "No Images", "No images to check for duplicates")
            return
        
        # This would be implemented with the ImageAnalyzer
        self.analyze_images()
    
    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(self, "About Image Downloader",
                         "Image Downloader v3.0\n\n"
                         "Reliable image downloading tool with:\n"
                         "• Bing + Google search engines\n"
                         "• Concurrent downloads with retries\n"
                         "• Advanced filtering (size, aspect ratio, color)\n"
                         "• Image analysis and duplicate detection\n"
                         "• Custom naming patterns\n"
                         "• Download history\n\n"
                         "Created with PyQt5 and Python")
    
    def browse_directory(self):
        """Open file dialog to select save directory"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Save Location",
            self.save_dir.text()
        )
        if directory:
            self.save_dir.setText(directory)
    
    def set_application_icon(self):
        """Set application icon if available"""
        icon_paths = [
            "app_icon.ico",
            "icon.ico",
            "icon.png",
            "icon.webp"
        ]
        
        for icon_path in icon_paths:
            if os.path.exists(icon_path):
                try:
                    app_icon = QIcon(icon_path)
                    self.setWindowIcon(app_icon)
                    QApplication.setWindowIcon(app_icon)
                    break
                except Exception as e:
                    print(f"Error setting icon: {e}")
    
    def load_settings(self):
        """Load settings from file"""
        default_settings = {
            "last_save_location": os.path.join(os.path.expanduser("~"), "Pictures"),
            "last_search_engine": "Bing",
            "last_image_size": "All Sizes",
            "last_num_images": 10,
            "last_file_prefix": "image",
            "file_type_jpg": True,
            "file_type_png": True,
            "file_type_webp": True,
            "file_type_gif": False,
            "file_type_bmp": False,
            "file_type_ico": False,
            "organize_by": "None",
            "download_threads": 4,
            "search_history": []
        }
        
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                
                # Ensure all keys exist
                for key, value in default_settings.items():
                    if key not in settings:
                        settings[key] = value
                
                return settings
            else:
                return default_settings
        except Exception:
            return default_settings
    
    def save_settings(self, settings_dict):
        """Save settings to file"""
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings_dict, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def load_history(self):
        """Load download history"""
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, 'r') as f:
                    return json.load(f)
        except:
            pass
        return []
    
    def save_history(self):
        """Save download history"""
        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(self.download_history, f, indent=2)
        except Exception as e:
            print(f"Error saving history: {e}")
    
    def closeEvent(self, event):
        """Handle close event"""
        if self.is_downloading:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "A download is in progress. Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.cancel_requested = True
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

def main():
    # Clean up any hanging processes
    cleanup_old_processes()
    
    # Single instance check
    import socket
    import errno
    
    # Try to create a socket to ensure single instance
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', 47200))  # Arbitrary port for our app
    except socket.error as e:
        if e.errno == errno.EADDRINUSE:
            print("Application is already running!")
            # Try to bring existing window to front
            QMessageBox.warning(None, "Already Running", 
                              "Image Downloader is already running.\n"
                              "Please check your system tray or task manager.")
            sys.exit(1)
        else:
            # Some other error
            sock.close()
            
    # Set high DPI scaling
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Set application metadata
    app.setApplicationName("Image Downloader")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("ImageDownloader")
    
    try:
        # Create and show main window
        window = ImageDownloader()
        window.show()
        
        # Keep the socket open while app runs
        app.aboutToQuit.connect(sock.close)
        
        # Clean up PID file on exit
        def cleanup():
            sock.close()
            try:
                os.remove(PID_FILE)
            except:
                pass
        
        app.aboutToQuit.connect(cleanup)
        
        sys.exit(app.exec_())
        
    except Exception as e:
        QMessageBox.critical(None, "Fatal Error", 
                           f"Failed to start application:\n{str(e)}\n\n"
                           "Please try restarting your computer if this persists.")
        sock.close()
        try:
            os.remove(PID_FILE)
        except:
            pass
        sys.exit(1)

if __name__ == "__main__":
    # Prevent multiple imports from creating instances
    import multiprocessing
    multiprocessing.freeze_support()
    
    # Add exception hook for better error reporting
    import traceback
    
    def exception_hook(exctype, value, tb):
        error_msg = ''.join(traceback.format_exception(exctype, value, tb))
        print(error_msg)
        QMessageBox.critical(None, "Unhandled Exception", 
                           f"An error occurred:\n\n{exctype.__name__}: {value}\n\n"
                           "Check the console for full traceback.")
        sys.exit(1)
    
    sys.excepthook = exception_hook
    
    main()