@echo off
echo ===== Image Downloader Builder =====
echo.

echo Step 1: Checking Python installation...
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Python is not installed or not in PATH.
    echo Please install Python 3.7+ and add it to PATH.
    pause
    exit /b 1
)
echo Python is installed.
echo.

echo Step 2: Upgrading pip...
python -m pip install --upgrade pip
if %ERRORLEVEL% neq 0 (
    echo Warning: Could not upgrade pip, continuing with current version...
)
echo.

echo Step 3: Installing required packages...
python -m pip install --upgrade --user PyQt5 Pillow pyinstaller requests
if %ERRORLEVEL% neq 0 (
    echo User installation failed, trying system-wide installation...
    python -m pip install --upgrade PyQt5 Pillow pyinstaller requests
    if %ERRORLEVEL% neq 0 (
        echo Error installing packages.
        echo Please try installing manually using:
        echo python -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)
echo Packages installed successfully.
echo.

echo Step 4: Converting icon if needed...
python -c "from PIL import Image; import os; icon_webp = 'icon.webp'; icon_ico = 'app_icon.ico'; exec(\"try:\\n    if os.path.exists(icon_webp) and not os.path.exists(icon_ico):\\n        print(f'Converting {icon_webp} to {icon_ico}...')\\n        img = Image.open(icon_webp)\\n        img.save(icon_ico)\\n        print('Icon converted successfully.')\\n    else:\\n        print('Using existing icon or icon not found.')\\nexcept Exception as e:\\n    print(f'Icon conversion error: {e}')\")"
echo.

echo Step 5: Stopping any running instances...
taskkill /F /IM ImageDownloader.exe 2>nul
echo.

echo Step 6: Building executable...
set PYTHON_FILE=image_downloader.py

if not exist "%PYTHON_FILE%" (
    echo Error: %PYTHON_FILE% not found in current directory.
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
        python -m PyInstaller --clean --name "ImageDownloader" --onefile --windowed --icon=app_icon.ico --hidden-import=PyQt5.sip --hidden-import=pkg_resources.py2_warn "%PYTHON_FILE%"
    ) else (
        python -m PyInstaller --clean --name "ImageDownloader" --onefile --windowed --hidden-import=PyQt5.sip --hidden-import=pkg_resources.py2_warn "%PYTHON_FILE%"
    )
    
    if %ERRORLEVEL% neq 0 (
        echo Second build attempt failed. Trying with minimal options...
        python -m PyInstaller --name "ImageDownloader" --onefile "%PYTHON_FILE%"
        
        if %ERRORLEVEL% neq 0 (
            echo All build attempts failed.
            echo Please check the error messages above and try building manually.
            pause
            exit /b 1
        )
    )
)

echo.
echo Step 7: Creating shortcut...
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
echo To run the application, either:
echo 1. Double-click the shortcut on your desktop
echo 2. Navigate to the 'dist' folder and run ImageDownloader.exe
echo 3. Or run: python image_downloader.py
echo.
echo Press any key to exit...
pause > nul
