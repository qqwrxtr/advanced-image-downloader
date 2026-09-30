@echo off
echo ===== Image Downloader Builder =====
echo.

echo Step 1: Installing required packages...
python -m pip install --upgrade pip
python -m pip install --upgrade PyQt5  Pillow pyinstaller requests
if %ERRORLEVEL% neq 0 (
    echo Error installing packages.
    echo Please make sure Python is installed correctly.
    pause
    exit /b 1
)
echo Packages installed successfully.
echo.

echo Step 2: Converting icon if needed...
python -c "from PIL import Image; import os; icon_webp = 'icon.webp'; icon_ico = 'app_icon.ico'; try: if os.path.exists(icon_webp) and not os.path.exists(icon_ico): print(f'Converting {icon_webp} to {icon_ico}...'); img = Image.open(icon_webp); img.save(icon_ico); print('Icon converted successfully.'); else: print('Using existing icon or icon not found.'); except Exception as e: print(f'Icon conversion error: {e}');"
echo.

echo Step 3: Cleaning previous build files...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "*.spec" del /f /q *.spec
echo Build directory cleaned.
echo.

echo Step 4: Building executable...
echo This may take a few minutes...

:: Kill any running instances
taskkill /F /IM ImageDownloader.exe 2>nul
taskkill /F /IM ImageDownloader.exe 2>nul
ping -n 2 127.0.0.1 > nul

:: Check which Python file exists
set PYTHON_FILE=
if exist "image_downloader.py" (
    set PYTHON_FILE=image_downloader.py
    echo Found: image_downloader.py
) else if exist "final_image_downloader.py" (
    set PYTHON_FILE=final_image_downloader.py
    echo Found: final_image_downloader.py
) else if exist "advanced_image_downloader.py" (
    set PYTHON_FILE=advanced_image_downloader.py
    echo Found: advanced_image_downloader.py
) else (
    echo Error: No Python file found!
    echo Please make sure you have one of these files:
    echo - fixed_image_downloader.py
    echo - final_image_downloader.py
    echo - advanced_image_downloader.py
    pause
    exit /b 1
)

:: Check if icon exists and use it
if exist "app_icon.ico" (
    echo Using custom icon: app_icon.ico
    python -m PyInstaller --clean --name "ImageDownloader" --onefile --windowed --icon=app_icon.ico "%PYTHON_FILE%"
) else (
    echo Custom icon not found, building without icon...
    python -m PyInstaller --clean --name "ImageDownloader" --onefile --windowed "%PYTHON_FILE%"
)

if %ERRORLEVEL% neq 0 (
    echo First build attempt failed. Trying again with more options...
    
    if exist "app_icon.ico" (
        python -m PyInstaller --clean --name "ImageDownloader" --onefile --windowed --icon=app_icon.ico --hidden-import=PyQt5.sip --hidden-import=.builtin "%PYTHON_FILE%"
    ) else (
        python -m PyInstaller --clean --name "ImageDownloader" --onefile --windowed --hidden-import=PyQt5.sip --hidden-import=.builtin "%PYTHON_FILE%"
    )
    
    if %ERRORLEVEL% neq 0 (
        echo Second build attempt failed. Trying with minimal options...
        python -m PyInstaller --name "ImageDownloader" --onefile "%PYTHON_FILE%"
        
        if %ERRORLEVEL% neq 0 (
            echo All build attempts failed.
            pause
            exit /b 1
        )
    )
)

echo.
echo Step 5: Creating shortcut...
echo Set oWS = WScript.CreateObject("WScript.Shell") > CreateShortcut.vbs
echo sLinkFile = "%USERPROFILE%\Desktop\Image Downloader.lnk" >> CreateShortcut.vbs
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> CreateShortcut.vbs
echo oLink.TargetPath = "%CD%\dist\ImageDownloader.exe" >> CreateShortcut.vbs
echo oLink.Description = "Image Downloader" >> CreateShortcut.vbs
echo oLink.Save >> CreateShortcut.vbs
cscript /nologo CreateShortcut.vbs
del CreateShortcut.vbs

echo.
echo ===== Build Completed Successfully! =====
echo.
echo Your ImageDownloader.exe is in the 'dist' folder.
echo A shortcut has been created on your desktop.
echo.
echo Press any key to exit...
pause > nul