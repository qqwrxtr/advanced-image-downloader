# Advanced Image Downloader

A fast, no-fuss desktop app for **bulk-downloading images** from the web. Type a search term, pick how many images you want, and it scrapes **Bing** and **Google Images**, downloads them concurrently, filters out junk, and saves them to a folder of your choice.

Built with **Python + PyQt5**, and packaged into a single Windows `.exe` with PyInstaller.

> **Heads-up:** This tool scrapes public image search results. Downloaded images may be copyrighted. Use it responsibly and respect the rights of content owners and the terms of service of the sites involved. Intended for personal use.

---

## Features

- 🔎 **Multiple engines** — search Bing, Google, or both at once ("All Engines")
- ⚡ **Concurrent downloads** — multi-threaded fetching with automatic retries
- 🎚️ **Advanced filtering** — filter by size, aspect ratio, and color
- 🧹 **Duplicate detection** — image analysis to skip near-identical results
- 🏷️ **Custom naming patterns** — control how downloaded files are named
- 🖼️ **Preview window** — review what you downloaded
- 🕓 **Download history** — remembers past searches and settings
- 💾 **Persistent settings** — stored in your home directory (`~/.image_downloader.json`)

## Requirements

- Python 3.8+
- Windows (primary target; the Python script itself is cross-platform, but the build tooling targets Windows)

Python dependencies (see [`requirements.txt`](requirements.txt)):

```
PyQt5>=5.15.0
Pillow>=8.0.0
requests>=2.25.0
pyinstaller>=4.0
```

> The app will also attempt to auto-install missing packages on first run.

---

## Run from source

```bash
# 1. (optional) create a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 2. install dependencies
pip install -r requirements.txt

# 3. run
python image_downloader.py
```

---

## Build a standalone Windows executable

The easiest way is the included build script:

```bat
build.bat
```

This will:
1. Install/upgrade the required packages
2. Build a single-file, windowed executable with the custom icon
3. Output `dist\ImageDownloader.exe`
4. Create a desktop shortcut

Prefer to run PyInstaller directly?

```bash
python -m PyInstaller --clean --name "ImageDownloader" --onefile --windowed --icon=app_icon.ico image_downloader.py
```

---

## How to use

1. Launch the app (`python image_downloader.py` or the built `.exe`).
2. Enter a **search term**.
3. Choose the **number of images** and, optionally, size/color filters.
4. Pick a **save directory**.
5. Select a **search engine** (Bing, Google, or All Engines).
6. Click **Download** and watch the progress bar.

---

## Project structure

| File | Purpose |
|------|---------|
| `image_downloader.py` | Main application (PyQt5 GUI + scraping + download logic) |
| `requirements.txt` | Python dependencies |
| `build.bat` / `build_new.bat` | Windows build scripts (PyInstaller) |
| `*.spec` | PyInstaller build specifications |
| `app_icon.ico` | Application icon |
| `icon_code_update.py` | Helper for icon handling |
| `test_dependencies.py` | Dependency sanity check |
