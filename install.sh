#!/bin/bash
# unified_autoau_installer.sh - Comprehensive installation script for AutoAU service
# This script combines the functionality of chrome_installation.sh, install_autoau.sh,
# and install_chromedriver.sh into a single unified installer.
#
# The script:
# 1. Sets up a dedicated service user
# 2. Installs Python 3.10 using pyenv
# 3. Creates a virtual environment
# 4. Installs Chrome 123 from a local RPM
# 5. Installs compatible ChromeDriver
# 6. Copies application files
# 7. Configures and starts the service

# Exit on any error
set -e

# Configuration variables
APP_DIR="/opt/autoau"                    # Application installation directory
SERVICE_NAME="autoau"                    # Service name
SERVICE_USER="autoau"                    # User to run the service
PYTHON_VERSION="3.10.13"                 # Python version to install
PYENV_ROOT="$APP_DIR/.pyenv"             # pyenv installation directory
PYTHON_PATH="$PYENV_ROOT/versions/$PYTHON_VERSION/bin/python"  # Path to newer Python
VENV_DIR="$APP_DIR/venv"                 # Virtual environment directory
LOG_DIR="$APP_DIR/logs"                  # Log directory
SESSION_DIR="$APP_DIR/sessions"          # Session directory
PROJECT_SOURCE="/home/opc/autoau"        # Source folder - CHANGE THIS if needed
TEMP_DIR=$(mktemp -d)                    # Temporary directory for downloads

# Color definitions for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to log messages
log_message() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Clean up temporary files on exit
cleanup() {
    log_message "Cleaning up temporary files..."
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run this script as root"
    exit 1
fi

# Display initial information
log_message "======= AutoAU Unified Installer ======="
log_message "Installation directory: $APP_DIR"
log_message "Service user: $SERVICE_USER"
log_message "Python version: $PYTHON_VERSION"
log_message "Source directory: $PROJECT_SOURCE"

#####################################################
# UTILITY FUNCTIONS FOR CHROME SETUP AND VERIFICATION
#####################################################

# Function to create an enhanced Chrome wrapper script
create_chrome_wrapper_script() {
    log_message "Creating enhanced Chrome wrapper script for headless environments..."
    
    # Create the wrapper script in the application bin directory
    cat > "$APP_DIR/bin/google-chrome" << 'EOF'
#!/bin/bash
# Enhanced Chrome wrapper script for headless environments

# Path to the real Chrome binary (will be auto-detected if not found)
CHROME_BIN=""

# Log function
log() {
    LOG_DIR="/opt/autoau/logs"
    mkdir -p "$LOG_DIR"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Chrome Wrapper] $1" >> "$LOG_DIR/chrome-wrapper.log"
}

log "Starting Chrome wrapper with args: $@"

# Add headless mode flags automatically if not explicitly provided
ARGS=("$@")
NEEDS_HEADLESS=true
NEEDS_DISABLE_GPU=true
NEEDS_NO_SANDBOX=true
NEEDS_DISABLE_DEV_SHM=true

for arg in "${ARGS[@]}"; do
    if [[ "$arg" == "--headless" ]]; then
        NEEDS_HEADLESS=false
    fi
    if [[ "$arg" == "--disable-gpu" ]]; then
        NEEDS_DISABLE_GPU=false
    fi
    if [[ "$arg" == "--no-sandbox" ]]; then
        NEEDS_NO_SANDBOX=false
    fi
    if [[ "$arg" == "--disable-dev-shm-usage" ]]; then
        NEEDS_DISABLE_DEV_SHM=false
    fi
done

# For version checks, always add these flags
if [[ "$*" == *"--version"* ]]; then
    NEEDS_HEADLESS=true
    NEEDS_DISABLE_GPU=true
    NEEDS_NO_SANDBOX=true
    NEEDS_DISABLE_DEV_SHM=true
fi

# Add the necessary flags for headless environments
NEW_ARGS=("${ARGS[@]}")
if [[ "$NEEDS_HEADLESS" == true ]]; then
    NEW_ARGS+=("--headless")
fi
if [[ "$NEEDS_DISABLE_GPU" == true ]]; then
    NEW_ARGS+=("--disable-gpu")
fi
if [[ "$NEEDS_NO_SANDBOX" == true ]]; then
    NEW_ARGS+=("--no-sandbox")
fi
if [[ "$NEEDS_DISABLE_DEV_SHM" == true ]]; then
    NEW_ARGS+=("--disable-dev-shm-usage")
fi

# Check for binary in current directory first
if [ -f "$APP_DIR/bin/chrome" ]; then
    CHROME_BIN="$APP_DIR/bin/chrome"
elif [ -f "/opt/google/chrome/chrome" ]; then
    CHROME_BIN="/opt/google/chrome/chrome"
elif [ -f "/usr/bin/google-chrome-stable" ]; then
    CHROME_BIN="/usr/bin/google-chrome-stable"
else
    # Perform a more extensive search but exclude our wrapper
    CHROME_BIN=$(find /bin /usr/bin /opt -name "chrome" -o -name "google-chrome" -type f -executable 2>/dev/null | grep -v "wrapper" | grep -v "$APP_DIR/bin/google-chrome" | head -1)
fi

if [ -z "$CHROME_BIN" ]; then
    log "ERROR: Chrome binary not found!"
    echo "Chrome binary not found. Please install Chrome properly." >&2
    exit 1
fi

log "Using Chrome binary: $CHROME_BIN with arguments: ${NEW_ARGS[*]}"

# Set display variable if not set
if [ -z "$DISPLAY" ]; then
    export DISPLAY=:0
fi

# Execute Chrome with the modified arguments
exec "$CHROME_BIN" "${NEW_ARGS[@]}"
EOF

    # Make executable and fix ownership
    chmod +x "$APP_DIR/bin/google-chrome"
    chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/bin/google-chrome"
    
    # Create symlink in standard location for system compatibility
    ln -sf "$APP_DIR/bin/google-chrome" /usr/bin/google-chrome 2>/dev/null || true
    
    # Create the same wrapper in the standard Chrome location
    cat > "/opt/google/chrome/google-chrome" << 'EOF'
#!/bin/bash
# Redirector to application's Chrome wrapper
exec /opt/autoau/bin/google-chrome "$@"
EOF
    
    chmod +x "/opt/google/chrome/google-chrome"
    
    log_message "Enhanced Chrome wrapper script created successfully"
}

# Function to safely verify Chrome installation in headless environments
verify_chrome_installation() {
    log_message "Verifying Chrome installation safely in headless environment..."
    
    # First check if the binary exists
    if [ -f "/opt/google/chrome/chrome" ]; then
        log_message "✓ Chrome binary exists at /opt/google/chrome/chrome"
    elif [ -f "/opt/google/chrome/google-chrome" ]; then
        log_message "✓ Chrome binary exists at /opt/google/chrome/google-chrome"
    elif [ -f "$APP_DIR/bin/chrome" ]; then
        log_message "✓ Chrome binary exists at $APP_DIR/bin/chrome"
    else
        log_error "✗ Chrome binary not found in expected locations"
        return 1
    fi
    
    # Try to get version using our wrapper script
    if [ -f "$APP_DIR/bin/google-chrome" ]; then
        CHROME_VERSION_WRAPPER=$("$APP_DIR/bin/google-chrome" --version 2>/dev/null)
        if [ -n "$CHROME_VERSION_WRAPPER" ]; then
            log_message "✓ Chrome version via wrapper: $CHROME_VERSION_WRAPPER"
            return 0
        fi
    fi
    
    # Try to get version with headless flags
    CHROME_VERSION_HEADLESS=$(DISPLAY=:0 /opt/google/chrome/chrome --headless --disable-gpu --no-sandbox --version 2>/dev/null)
    if [ -n "$CHROME_VERSION_HEADLESS" ]; then
        log_message "✓ Chrome version (headless mode): $CHROME_VERSION_HEADLESS"
        return 0
    fi
    
    # Check if RPM reports Chrome as installed
    if rpm -q google-chrome-stable &>/dev/null; then
        CHROME_RPM_VERSION=$(rpm -q --queryformat '%{VERSION}' google-chrome-stable)
        log_message "✓ Chrome installed via RPM with version: $CHROME_RPM_VERSION"
        return 0
    fi
    
    # If all version checks failed, check file properties as a last resort
    if [ -f "/opt/google/chrome/chrome" ]; then
        CHROME_FILE_INFO=$(file /opt/google/chrome/chrome)
        log_message "Chrome binary file info: $CHROME_FILE_INFO"
        
        # Check if it's an executable
        if [[ "$CHROME_FILE_INFO" == *"executable"* ]]; then
            log_message "✓ Chrome binary is executable"
            
            # Check dependencies
            log_message "Checking Chrome dependencies..."
            MISSING_DEPS=$(ldd /opt/google/chrome/chrome 2>/dev/null | grep "not found")
            if [ -n "$MISSING_DEPS" ]; then
                log_warning "Chrome has missing dependencies:"
                echo "$MISSING_DEPS"
                log_message "Installing common Chrome dependencies..."
                yum install -y pango.x86_64 libXcomposite.x86_64 libXcursor.x86_64 libXdamage.x86_64 \
                    libXext.x86_64 libXi.x86_64 libXtst.x86_64 cups-libs.x86_64 libXScrnSaver.x86_64 \
                    libXrandr.x86_64 GConf2.x86_64 alsa-lib.x86_64 atk.x86_64 gtk3.x86_64 \
                    xorg-x11-fonts-100dpi xorg-x11-fonts-75dpi xorg-x11-utils \
                    xorg-x11-fonts-cyrillic xorg-x11-fonts-Type1 xorg-x11-fonts-misc
            else
                log_message "✓ Chrome dependencies look good"
            fi
        else
            log_warning "✗ Chrome binary exists but may not be executable"
        fi
    fi
    
    log_warning "⚠ Could not verify Chrome version through execution."
    log_message "This is common in headless environments and may be OK for automated operation."
    return 0
}

#####################################################
# 1. PREPARE SYSTEM AND INSTALL DEPENDENCIES
#####################################################

# Install required development packages for building Python and other dependencies
log_message "Installing system dependencies..."
yum install -y gcc gcc-c++ make git openssl-devel bzip2-devel libffi-devel zlib-devel \
  readline-devel sqlite-devel wget unzip xz-devel ncurses-devel gdbm-devel

# Create service user if it doesn't exist
if ! id "$SERVICE_USER" &> /dev/null; then
    log_message "Creating service user: $SERVICE_USER"
    useradd -r -m -d "$APP_DIR" -s /bin/bash "$SERVICE_USER"
else
    log_message "Service user $SERVICE_USER already exists"
fi

# Create application directory if it doesn't exist
if [ ! -d "$APP_DIR" ]; then
    log_message "Creating application directory: $APP_DIR"
    mkdir -p "$APP_DIR"
    chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
fi

# Create directories for logs, sessions, and drivers
log_message "Creating necessary directories..."
mkdir -p "$LOG_DIR" "$SESSION_DIR" "$APP_DIR/drivers"
chown -R "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR" "$SESSION_DIR" "$APP_DIR/drivers"

#####################################################
# 2. INSTALL PYTHON USING PYENV
#####################################################

# Install pyenv for the service user
log_message "Setting up Python environment with pyenv..."
if [ ! -d "$PYENV_ROOT" ]; then
    log_message "Cloning pyenv repository..."
    su -c "git clone https://github.com/pyenv/pyenv.git $PYENV_ROOT" "$SERVICE_USER"
    
    # Set up environment for pyenv
    echo "export PYENV_ROOT=\"$PYENV_ROOT\"" >> "$APP_DIR/.bashrc"
    echo "export PATH=\"\$PYENV_ROOT/bin:\$PATH\"" >> "$APP_DIR/.bashrc"
    echo "eval \"\$(pyenv init --path)\"" >> "$APP_DIR/.bashrc"
    echo "eval \"\$(pyenv init -)\"" >> "$APP_DIR/.bashrc"
    
    chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/.bashrc"
else
    log_message "pyenv is already installed"
fi

# Install Python using pyenv
log_message "Installing Python $PYTHON_VERSION..."
if [ ! -d "$PYENV_ROOT/versions/$PYTHON_VERSION" ]; then
    # Make sure pyenv directories have correct permissions
    chown -R "$SERVICE_USER:$SERVICE_USER" "$PYENV_ROOT"
    
    # Create the versions directory with the right permissions
    mkdir -p "$PYENV_ROOT/versions"
    chown -R "$SERVICE_USER:$SERVICE_USER" "$PYENV_ROOT/versions"
    
    # Create a script to run as the service user
    PYENV_SCRIPT="$APP_DIR/install_python.sh"
    
    cat > "$PYENV_SCRIPT" << EOF
#!/bin/bash
export PYENV_ROOT="$PYENV_ROOT"
export PATH="$PYENV_ROOT/bin:\$PATH"
eval "\$($PYENV_ROOT/bin/pyenv init --path)"
eval "\$($PYENV_ROOT/bin/pyenv init -)"
cd "$APP_DIR"
echo "Starting Python $PYTHON_VERSION installation..."
$PYENV_ROOT/bin/pyenv install $PYTHON_VERSION
echo "Python installation completed with status \$?"
EOF
    
    # Make it executable and set proper ownership
    chmod +x "$PYENV_SCRIPT"
    chown "$SERVICE_USER:$SERVICE_USER" "$PYENV_SCRIPT"
    
    # Run the script as the service user
    log_message "Running Python installation as $SERVICE_USER..."
    su -l "$SERVICE_USER" -c "$PYENV_SCRIPT"
    
    # Clean up
    rm -f "$PYENV_SCRIPT"
    
    if [ ! -f "$PYTHON_PATH" ]; then
        log_error "Failed to install Python $PYTHON_VERSION. Check the log at /tmp/python-build.*.log"
        
        # Try to find the most recent Python build log
        RECENT_LOG=$(ls -t /tmp/python-build.*.log 2>/dev/null | head -1)
        if [ -n "$RECENT_LOG" ]; then
            log_message "Last 20 lines of build log ($RECENT_LOG):"
            tail -20 "$RECENT_LOG"
            
            # Check for common issues in the log
            if grep -q "No module named '_ctypes'" "$RECENT_LOG"; then
                log_message "Missing libffi-devel. Installing it now..."
                yum install -y libffi-devel
                log_message "Please run the script again."
            elif grep -q "The necessary bits to build these optional modules were not found" "$RECENT_LOG"; then
                log_message "Some optional modules couldn't be built. This may be OK for basic functionality."
                log_message "To install all development libraries, run: yum install -y bzip2-devel libffi-devel ncurses-devel gdbm-devel xz-devel tk-devel uuid-devel readline-devel"
            fi
        fi
        
        exit 1
    fi
    
    log_message "Python $PYTHON_VERSION installed successfully"
else
    log_message "Python $PYTHON_VERSION is already installed"
fi

# Create virtual environment with the new Python version
log_message "Creating Python virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    # First install virtualenv with the new Python
    su -c "$PYTHON_PATH -m pip install --upgrade pip setuptools wheel virtualenv" "$SERVICE_USER"
    
    # Then create the virtual environment
    su -c "$PYTHON_PATH -m virtualenv $VENV_DIR" "$SERVICE_USER"
    
    if [ ! -f "$VENV_DIR/bin/python" ]; then
        log_error "Failed to create virtual environment"
        exit 1
    fi
    
    log_message "Virtual environment created successfully"
else
    log_warning "Virtual environment already exists at $VENV_DIR"
fi

#####################################################
# 3. INSTALL CHROME
#####################################################

log_message "Setting up Chrome version 123 for Oracle Private Cloud environment..."

# Create application bin directory if it doesn't exist
mkdir -p "$APP_DIR/bin"
chmod 755 "$APP_DIR/bin"
chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/bin"

# Find Chrome 123 RPM in /home/opc directory
CHROME_RPM_PATH=$(find /home/opc -name "google-chrome-stable-123*.rpm" 2>/dev/null | head -1)

if [ -f "$CHROME_RPM_PATH" ]; then
    log_message "Found Chrome 123 RPM at $CHROME_RPM_PATH"
    
    # First check if Chrome is already installed via RPM
    if rpm -q google-chrome-stable &> /dev/null; then
        CURRENT_VERSION=$(rpm -q --queryformat '%{VERSION}' google-chrome-stable | grep -o "^[0-9]*")
        log_message "Current Chrome version from RPM database: $CURRENT_VERSION"
        
        # Regardless of version, remove existing Chrome installation to ensure clean state
        log_message "Removing existing Chrome installation..."
        yum remove -y google-chrome-stable
        
        # Also remove any existing Chrome directories that might cause conflicts
        log_message "Cleaning up any existing Chrome directories..."
        rm -rf /opt/google/chrome
        rm -f "$APP_DIR/bin/chrome" "$APP_DIR/bin/google-chrome"
    fi
    
    # Create standard Chrome directory with proper permissions
    log_message "Creating standard Chrome installation directory..."
    mkdir -p /opt/google/chrome
    chmod 755 /opt/google/chrome
    
    # Install Chrome 123 from RPM
    log_message "Installing Chrome 123 from RPM..."
    yum install -y "$CHROME_RPM_PATH"
    
    # Verify Chrome binary location after installation
    CHROME_BIN=$(which google-chrome 2>/dev/null || echo "")
    if [ -z "$CHROME_BIN" ]; then
        # Look for chrome binary in standard locations
        for loc in "/opt/google/chrome/chrome" "/opt/google/chrome/google-chrome" "/usr/bin/google-chrome" "/usr/bin/chrome"; do
            if [ -f "$loc" ]; then
                CHROME_BIN="$loc"
                log_message "Found Chrome binary at: $CHROME_BIN"
                break
            fi
        done
    else
        log_message "Found Chrome in PATH at: $CHROME_BIN"
    fi
    
    # If Chrome binary found but not in expected location, handle this case
    if [ -n "$CHROME_BIN" ]; then
        # Get the real binary, not just a symlink
        REAL_CHROME_BIN=$(readlink -f "$CHROME_BIN")
        log_message "Real Chrome binary is at: $REAL_CHROME_BIN"
        
        # Copy the real Chrome binary to the application's bin directory
        log_message "Copying Chrome binary to application bin directory..."
        cp "$REAL_CHROME_BIN" "$APP_DIR/bin/chrome"
        chmod +x "$APP_DIR/bin/chrome"
        
        # Create symlink for google-chrome in the app's bin directory
        ln -sf "$APP_DIR/bin/chrome" "$APP_DIR/bin/google-chrome"
        
        # Also create the expected directory structure with the real binary
        log_message "Ensuring proper Chrome structure in /opt/google/chrome"
        if [ ! -f "/opt/google/chrome/chrome" ]; then
            cp "$REAL_CHROME_BIN" /opt/google/chrome/chrome
            chmod +x /opt/google/chrome/chrome
        fi
        
        if [ ! -f "/opt/google/chrome/google-chrome" ]; then
            ln -sf /opt/google/chrome/chrome /opt/google/chrome/google-chrome
        fi
    else
        # Chrome binary not found, extract from RPM directly
        log_message "Chrome binary not found in expected location. Extracting from RPM..."
        
        # Create a temp directory for extraction
        TEMP_CHROME_DIR="$TEMP_DIR/chrome_extract"
        mkdir -p "$TEMP_CHROME_DIR"
        
        # Extract the RPM contents
        cd "$TEMP_CHROME_DIR"
        rpm2cpio "$CHROME_RPM_PATH" | cpio -idmv &>/dev/null
        
        # Find the real Chrome binary in extracted files (avoid SELinux directories)
        EXTRACTED_BIN=$(find "$TEMP_CHROME_DIR" -path "*/opt/google/chrome/chrome" -type f 2>/dev/null | grep -v "selinux" | head -1)
        
        if [ -n "$EXTRACTED_BIN" ]; then
            log_message "Found Chrome binary in RPM at: $EXTRACTED_BIN"
            
            # Get the directory containing chrome binary
            CHROME_FILES_DIR=$(dirname "$EXTRACTED_BIN")
            
            # Copy all required files to the standard Chrome directory
            log_message "Copying Chrome files to /opt/google/chrome"
            cp -r "$CHROME_FILES_DIR"/* /opt/google/chrome/
            
            # Copy Chrome binary to application bin directory
            log_message "Copying Chrome binary to application bin directory"
            cp "$EXTRACTED_BIN" "$APP_DIR/bin/chrome"
            
            # Make binaries executable
            chmod +x /opt/google/chrome/chrome
            chmod +x /opt/google/chrome/google-chrome 2>/dev/null || true
            chmod +x "$APP_DIR/bin/chrome"
            
            # Create symlinks
            ln -sf /opt/google/chrome/chrome /opt/google/chrome/google-chrome 2>/dev/null || true
            ln -sf "$APP_DIR/bin/chrome" "$APP_DIR/bin/google-chrome"
        else
            log_error "Chrome binary not found in extracted RPM using standard path. Trying alternative search..."
            # Try to find chrome executable anywhere in the extracted files, avoiding SELinux directories
            EXTRACTED_BIN=$(find "$TEMP_CHROME_DIR" -name "chrome" -type f -executable 2>/dev/null | grep -v "selinux" | head -1)
            
            if [ -n "$EXTRACTED_BIN" ]; then
                log_message "Found Chrome binary at: $EXTRACTED_BIN"
                cp "$EXTRACTED_BIN" "$APP_DIR/bin/chrome"
                chmod +x "$APP_DIR/bin/chrome"
                ln -sf "$APP_DIR/bin/chrome" "$APP_DIR/bin/google-chrome"
                
                # Also update standard location
                cp "$EXTRACTED_BIN" /opt/google/chrome/chrome
                chmod +x /opt/google/chrome/chrome
                ln -sf /opt/google/chrome/chrome /opt/google/chrome/google-chrome
            else
                log_error "Chrome binary not found in extracted RPM. Creating wrapper script as fallback..."
                # Create wrapper scripts as fallback
                create_chrome_wrapper_script
            fi
        fi
    fi
    
    # Create symlinks in standard locations for compatibility
    log_message "Creating system-wide symlinks for compatibility"
    ln -sf "$APP_DIR/bin/google-chrome" /usr/bin/google-chrome 2>/dev/null || true
    
    # Lock Chrome version to prevent updates
    log_message "Locking Chrome version to prevent updates..."
    if yum list available yum-versionlock &>/dev/null; then
        yum install -y yum-versionlock
        yum versionlock add google-chrome-stable 2>/dev/null || log_message "Chrome already locked or versionlock failed"
    else
        log_message "yum-versionlock package not available, using alternative method to prevent updates"
        # Alternative method: disable the repo
        yum-config-manager --disable google-chrome 2>/dev/null || log_warning "Could not disable google-chrome repo"
    fi
    
    log_message "Preventing Chrome auto-updates via configuration..."
    mkdir -p /etc/default
    echo "repo_add_once=false" > /etc/default/google-chrome
    echo "repo_reenable_on_distupgrade=false" >> /etc/default/google-chrome
    
    # Install dependencies needed for Chrome in headless environments
    log_message "Installing dependencies required for Chrome in headless environments..."
    yum install -y pango.x86_64 libXcomposite.x86_64 libXcursor.x86_64 libXdamage.x86_64 \
        libXext.x86_64 libXi.x86_64 libXtst.x86_64 cups-libs.x86_64 libXScrnSaver.x86_64 \
        libXrandr.x86_64 GConf2.x86_64 alsa-lib.x86_64 atk.x86_64 gtk3.x86_64 \
        xorg-x11-fonts-100dpi xorg-x11-fonts-75dpi xorg-x11-utils \
        xorg-x11-fonts-cyrillic xorg-x11-fonts-Type1 xorg-x11-fonts-misc
    
    # Install xvfb if available (for virtual display)
    if yum list available xorg-x11-server-Xvfb &>/dev/null; then
        log_message "Installing Xvfb for virtual display support..."
        yum install -y xorg-x11-server-Xvfb
    fi
    
    # Create enhanced Chrome wrapper script for headless environments
    create_chrome_wrapper_script
    
    # Test Chrome installation with headless flags
    verify_chrome_installation
else
    log_error "Chrome 123 RPM not found in /home/opc directory"
    log_error "Please download Chrome 123 RPM manually and place it in /home/opc"
    log_error "You can find it at: https://dl.google.com/linux/chrome/rpm/stable/x86_64/google-chrome-stable-123.0.6312.58-1.x86_64.rpm"
    log_error "Warning: Using a different Chrome version may cause the application to malfunction"
    
    # Ask if user wants to attempt installation of latest Chrome
    read -p "Would you like to try installing the latest Chrome version instead? (y/n): " INSTALL_LATEST
    if [[ $INSTALL_LATEST == "y" || $INSTALL_LATEST == "Y" ]]; then
        log_message "Attempting to install latest Chrome version..."
        
        # Add Google Chrome repository
        cat > /etc/yum.repos.d/google-chrome.repo << EOF
[google-chrome]
name=google-chrome
baseurl=http://dl.google.com/linux/chrome/rpm/stable/x86_64
enabled=1
gpgcheck=1
gpgkey=https://dl.google.com/linux/linux_signing_key.pub
EOF
        
        # Install latest Chrome
        yum install -y google-chrome-stable
        
        # Find installed Chrome and copy to application bin
        CHROME_BIN=$(which google-chrome 2>/dev/null || echo "")
        if [ -n "$CHROME_BIN" ]; then
            REAL_CHROME_BIN=$(readlink -f "$CHROME_BIN")
            cp "$REAL_CHROME_BIN" "$APP_DIR/bin/chrome"
            chmod +x "$APP_DIR/bin/chrome"
            ln -sf "$APP_DIR/bin/chrome" "$APP_DIR/bin/google-chrome"
            chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/bin"
            
            # Create enhanced Chrome wrapper for headless environments
            create_chrome_wrapper_script
            verify_chrome_installation
        fi
        
        log_warning "Installed latest Chrome version. Application may not work correctly!"
    else
        log_error "Skipping Chrome installation. Please manually install Chrome 123."
    fi
fi

log_message "Chrome setup completed for Oracle Private Cloud environment"

# Call these functions after Chrome installation logic is complete
update_browser_service_for_headless
update_service_file_for_headless

#####################################################
# 4. INSTALL CHROMEDRIVER
#####################################################

log_message "Installing ChromeDriver for Chrome 123..."

# Check for existing ChromeDriver in project directory
if [ -f "/home/opc/autoau/drivers/chromedriver" ]; then
    log_message "Found manually installed ChromeDriver, setting it up..."
    # Copy the manually installed ChromeDriver to the application directory
    cp "/home/opc/autoau/drivers/chromedriver" "$APP_DIR/drivers/"
    chmod +x "$APP_DIR/drivers/chromedriver"
    chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/drivers/chromedriver"
else
    log_message "Downloading ChromeDriver 123..."
    CHROMEDRIVER_URL="https://storage.googleapis.com/chrome-for-testing-public/123.0.6312.86/linux64/chromedriver-linux64.zip"
    CHROMEDRIVER_ZIP="$TEMP_DIR/chromedriver.zip"
    
    curl -L -o "$CHROMEDRIVER_ZIP" "$CHROMEDRIVER_URL"
    if [ -f "$CHROMEDRIVER_ZIP" ] && [ -s "$CHROMEDRIVER_ZIP" ]; then
        log_message "Extracting ChromeDriver..."
        unzip -q "$CHROMEDRIVER_ZIP" -d "$TEMP_DIR"
        
        # Find chromedriver binary
        CHROMEDRIVER_BIN=$(find "$TEMP_DIR" -path "*/chromedriver-linux64/chromedriver" -type f)
        
        if [ -n "$CHROMEDRIVER_BIN" ]; then
            cp "$CHROMEDRIVER_BIN" "$APP_DIR/drivers/chromedriver"
            chmod +x "$APP_DIR/drivers/chromedriver"
            chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/drivers/chromedriver"
            log_message "ChromeDriver 123 installed successfully"
        else
            log_error "ChromeDriver binary not found in extracted files"
            log_error "You may need to manually install ChromeDriver"
        fi
    else
        log_error "Failed to download ChromeDriver 123"
        log_error "You may need to manually install ChromeDriver"
    fi
fi

# Verify ChromeDriver installation
if [ -f "$APP_DIR/drivers/chromedriver" ]; then
    log_message "Verifying ChromeDriver installation..."
    CHROMEDRIVER_VERSION=$("$APP_DIR/drivers/chromedriver" --version)
    log_message "ChromeDriver installed: $CHROMEDRIVER_VERSION"
else
    log_error "ChromeDriver not found at $APP_DIR/drivers/chromedriver"
    log_error "You may need to manually install ChromeDriver"
fi

#####################################################
# 5. COPY APPLICATION FILES
#####################################################

# Copy application files to installation directory
log_message "Copying application files..."
if [ -d "$PROJECT_SOURCE" ]; then
    # Create a list of files to copy (excluding system directories)
    find "$PROJECT_SOURCE" -type f -not -path "*/\.*" -not -path "*/venv/*" -not -path "*/\__pycache__/*" | \
    while read file; do
        # Get the relative path
        rel_path=${file#$PROJECT_SOURCE/}
        # Create the directory if it doesn't exist
        mkdir -p "$APP_DIR/$(dirname "$rel_path")"
        # Copy the file
        cp "$file" "$APP_DIR/$rel_path"
    done
    
    # Copy directories but exclude problematic ones
    find "$PROJECT_SOURCE" -type d -not -path "*/\.*" -not -path "*/venv/*" -not -path "*/\__pycache__/*" -not -path "*/drivers/*" | \
    while read dir; do
        # Skip the source directory itself
        if [ "$dir" != "$PROJECT_SOURCE" ]; then
            # Get the relative path
            rel_path=${dir#$PROJECT_SOURCE/}
            # Create the directory
            mkdir -p "$APP_DIR/$rel_path"
        fi
    done
    
    chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
    log_message "Application files copied successfully"
else
    log_error "Source directory $PROJECT_SOURCE does not exist!"
    exit 1
fi

#####################################################
# 6. UPDATE CONFIGURATION FILES
#####################################################

# Update browser_service.py to use Chrome 123 correctly
log_message "Updating browser_service.py with Chrome compatibility settings..."
if [ -f "$APP_DIR/browser_service.py" ]; then
    # Backup the file first
    cp "$APP_DIR/browser_service.py" "$APP_DIR/browser_service.py.bak"
    
    # Add Chrome binary path to options
    if ! grep -q "options.binary_location" "$APP_DIR/browser_service.py"; then
        sed -i '/options.add_argument.*--disable-blink-features=AutomationControlled/a \        # Explicitly set Chrome binary path\n        options.binary_location = "/opt/google/chrome/google-chrome"' "$APP_DIR/browser_service.py"
        log_message "Added Chrome binary location to browser_service.py"
    else
        log_message "Chrome binary location already set in browser_service.py"
    fi
    
    # Add Chrome version compatibility setting to options
    if ! grep -q "options.add_argument('--chrome-version=123')" "$APP_DIR/browser_service.py"; then
        sed -i '/options.add_argument.*--disable-blink-features=AutomationControlled/a \        # Force compatibility with ChromeDriver 123\n        options.add_argument("--chrome-version=123")' "$APP_DIR/browser_service.py"
        log_message "Added Chrome version compatibility setting to browser_service.py"
    else
        log_message "Chrome version compatibility setting already exists in browser_service.py"
    fi
    
    # Add version_main parameter to undetected_chromedriver if it exists
    if grep -q "uc_webdriver.Chrome" "$APP_DIR/browser_service.py" && ! grep -q "version_main=123" "$APP_DIR/browser_service.py"; then
        sed -i '/driver = uc_webdriver.Chrome(/a \                            version_main=123,' "$APP_DIR/browser_service.py"
        log_message "Added version_main parameter to undetected_chromedriver in browser_service.py"
    fi
    
    chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/browser_service.py"
    log_message "browser_service.py updated with Chrome 123 compatibility settings"
else
    log_warning "browser_service.py not found, skipping compatibility settings"
    
    # Try to find the correct path
    FOUND_SERVICE=$(find "$APP_DIR" -name "browser_service.py" 2>/dev/null)
    if [ -n "$FOUND_SERVICE" ]; then
        log_message "Found browser_service.py at: $FOUND_SERVICE"
        
        # Backup the file first
        cp "$FOUND_SERVICE" "${FOUND_SERVICE}.bak"
        
        # Add Chrome binary path to options
        if ! grep -q "options.binary_location" "$FOUND_SERVICE"; then
            sed -i '/options.add_argument.*--disable-blink-features=AutomationControlled/a \        # Explicitly set Chrome binary path\n        options.binary_location = "/opt/google/chrome/google-chrome"' "$FOUND_SERVICE"
            log_message "Added Chrome binary location to browser_service.py"
        else
            log_message "Chrome binary location already set in browser_service.py"
        fi
        
        # Add Chrome version compatibility setting
        if ! grep -q "options.add_argument('--chrome-version=123')" "$FOUND_SERVICE"; then
            sed -i '/options.add_argument.*--disable-blink-features=AutomationControlled/a \        # Force compatibility with ChromeDriver 123\n        options.add_argument("--chrome-version=123")' "$FOUND_SERVICE"
            log_message "Added Chrome version compatibility setting to browser_service.py"
        fi
        
        # Add version_main parameter to undetected_chromedriver if it exists
        if grep -q "uc_webdriver.Chrome" "$FOUND_SERVICE" && ! grep -q "version_main=123" "$FOUND_SERVICE"; then
            sed -i '/driver = uc_webdriver.Chrome(/a \                            version_main=123,' "$FOUND_SERVICE"
            log_message "Added version_main parameter to undetected_chromedriver"
        fi
        
        chown "$SERVICE_USER:$SERVICE_USER" "$FOUND_SERVICE"
        log_message "browser_service.py updated successfully"
    else
        log_warning "Could not find browser_service.py in the application directory"
    fi
fi

#####################################################
# 7. INSTALL PYTHON DEPENDENCIES
#####################################################

# Install dependencies in virtual environment
log_message "Installing Python dependencies..."
if [ -f "$APP_DIR/requirements.txt" ]; then
    su -c "$VENV_DIR/bin/pip install -r $APP_DIR/requirements.txt" "$SERVICE_USER"
else
    log_warning "requirements.txt not found at $APP_DIR/requirements.txt"
    # Try to find it
    REQUIREMENTS_FILE=$(find "$APP_DIR" -name "requirements.txt" 2>/dev/null | head -1)
    if [ -n "$REQUIREMENTS_FILE" ]; then
        log_message "Found requirements.txt at: $REQUIREMENTS_FILE"
        su -c "$VENV_DIR/bin/pip install -r $REQUIREMENTS_FILE" "$SERVICE_USER"
    else
        log_warning "Could not find requirements.txt, installing common packages..."
        su -c "$VENV_DIR/bin/pip install selenium webdriver-manager undetected-chromedriver pyOpenSSL cryptography" "$SERVICE_USER"
    fi
fi

# Install the latest compatible versions of SSL-related packages
log_message "Installing SSL-related packages..."
su -c "$VENV_DIR/bin/pip install pyOpenSSL cryptography" "$SERVICE_USER"

#####################################################
# 8. CREATE SERVICE CONTROL SCRIPT
#####################################################

# Create an enhanced version of the restart script
log_message "Creating service control script..."
cat > "$APP_DIR/service_control.sh" << 'EOF'
#!/bin/bash
# service_control.sh - Enhanced control script for AutoAU service

# Environment
APP_DIR="$(dirname "$(readlink -f "$0")")"
VENV_DIR="$APP_DIR/venv"
LOG_DIR="$APP_DIR/logs"
PYTHON="$VENV_DIR/bin/python"

# Load pyenv environment if needed
if [ -f "$APP_DIR/.bashrc" ]; then
    source "$APP_DIR/.bashrc"
fi

# Log file
CONTROL_LOG="$LOG_DIR/service_control.log"

# Make sure log directory exists
mkdir -p "$LOG_DIR"

# Add drivers directory to PATH
export PATH="$APP_DIR/drivers:$PATH"

# Set environment variables for ChromeDriver compatibility
export SELENIUM_EXCLUDE_DV_CHECK=true
export WDM_LOG_LEVEL=0

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$CONTROL_LOG"
}

stop_app() {
    log "Stopping AutoAU application..."
    
    # Find and stop main Python process
    PID=$(ps -ef | grep "$VENV_DIR/bin/python" | grep "main.py" | grep -v grep | awk '{print $2}')
    if [ ! -z "$PID" ]; then
        log "Found process with PID: $PID, sending SIGTERM..."
        kill $PID
        
        # Wait for process to terminate
        for i in {1..10}; do
            if ! ps -p $PID > /dev/null; then
                log "Process terminated successfully"
                break
            fi
            sleep 1
        done
        
        # Force kill if still running
        if ps -p $PID > /dev/null; then
            log "Process still running, sending SIGKILL..."
            kill -9 $PID
        fi
    else
        log "No running AutoAU process found"
    fi
    
    # Clean up browser processes
    log "Cleaning up Chrome and ChromeDriver processes..."
    pkill -f "chromedriver" 2>/dev/null || true
    pkill -f "chrome" 2>/dev/null || true
}

start_app() {
    log "Starting AutoAU application..."
    
    # Check if Python executable exists
    if [ ! -f "$PYTHON" ]; then
        log "ERROR: Python executable not found at $PYTHON"
        exit 1
    fi
    
    # Check if main.py exists
    if [ ! -f "$APP_DIR/main.py" ]; then
        log "ERROR: main.py not found at $APP_DIR/main.py"
        exit 1
    fi
    
    # Verify ChromeDriver exists and is compatible
    if [ -f "$APP_DIR/drivers/chromedriver" ]; then
        CHROMEDRIVER_VERSION=$("$APP_DIR/drivers/chromedriver" --version | grep -oP "ChromeDriver \K[0-9]+")
        log "Found ChromeDriver version: $CHROMEDRIVER_VERSION"
    else
        log "WARNING: ChromeDriver not found at $APP_DIR/drivers/chromedriver"
    fi
    
    # Verify Chrome exists in expected location
    if [ -d "/opt/google/chrome" ] || [ -f "/opt/google/chrome" ]; then
        log "Verified Chrome in /opt/google/chrome"
    else
        log "WARNING: Chrome not found in /opt/google/chrome"
    fi
    
    # Move to application directory
    cd "$APP_DIR"
    
    # Rotate log file if too large (over 10MB)
    if [ -f "$LOG_DIR/autoau_output.log" ] && [ $(stat -c%s "$LOG_DIR/autoau_output.log") -gt 10485760 ]; then
        log "Rotating log file..."
        mv "$LOG_DIR/autoau_output.log" "$LOG_DIR/autoau_output.log.$(date '+%Y%m%d%H%M%S')"
        
        # Keep only the 5 most recent log files
        ls -t "$LOG_DIR"/autoau_output.log.* | tail -n +6 | xargs -r rm
    fi
    
    # Start the application with the virtual environment Python
    log "Launching application using $PYTHON"
    nohup "$PYTHON" main.py > "$LOG_DIR/autoau_output.log" 2>&1 &
    
    # Check if process started successfully
    NEW_PID=$!
    sleep 2
    if ps -p $NEW_PID > /dev/null; then
        log "Application started successfully with PID: $NEW_PID"
    else
        log "ERROR: Failed to start application"
        exit 1
    fi
}

status_app() {
    PID=$(ps -ef | grep "$VENV_DIR/bin/python" | grep "main.py" | grep -v grep | awk '{print $2}')
    if [ ! -z "$PID" ]; then
        log "AutoAU is running with PID: $PID"
        echo "AutoAU is running with PID: $PID"
        return 0
    else
        log "AutoAU is not running"
        echo "AutoAU is not running"
        return 1
    fi
}

restart_app() {
    log "Restarting AutoAU application..."
    stop_app
    sleep 2
    start_app
}

# Parse command-line arguments
case "$1" in
    start)
        start_app
        ;;
    stop)
        stop_app
        ;;
    restart)
        restart_app
        ;;
    status)
        status_app
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac

exit 0
EOF

# Make the service control script executable
chmod +x "$APP_DIR/service_control.sh"
chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/service_control.sh"

#####################################################
# 9. CREATE SYSTEMD SERVICE
#####################################################

# Create systemd service file
log_message "Creating systemd service..."
cat > "/etc/systemd/system/$SERVICE_NAME.service" << EOF
[Unit]
Description=AutoAU Service
After=network.target

[Service]
Type=forking
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/drivers:$PATH"
Environment="SELENIUM_EXCLUDE_DV_CHECK=true"
Environment="WDM_LOG_LEVEL=0"
ExecStart=$APP_DIR/service_control.sh start
ExecStop=$APP_DIR/service_control.sh stop
ExecReload=$APP_DIR/service_control.sh restart
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd, enable and start the service
log_message "Enabling and starting the service..."
systemctl daemon-reload
systemctl enable "$SERVICE_NAME.service"
systemctl start "$SERVICE_NAME.service"

#####################################################
# 10. FINAL VALIDATION
#####################################################

# Verify that the service is running
if systemctl is-active --quiet "$SERVICE_NAME.service"; then
    log_message "AutoAU service is now running"
else
    log_warning "AutoAU service did not start automatically. Checking logs..."
    journalctl -u "$SERVICE_NAME.service" -n 20
fi

# Perform final validation
log_message "Performing final validation..."

# Verify Python installation
if [ -f "$PYTHON_PATH" ]; then
    PYTHON_VERSION_INSTALLED=$("$PYTHON_PATH" --version)
    log_message "✓ Python installed: $PYTHON_VERSION_INSTALLED"
else
    log_error "✗ Python not found at $PYTHON_PATH"
fi

# Verify virtual environment
if [ -f "$VENV_DIR/bin/python" ]; then
    VENV_PYTHON_VERSION=$("$VENV_DIR/bin/python" --version)
    log_message "✓ Virtual environment Python: $VENV_PYTHON_VERSION"
else
    log_error "✗ Virtual environment Python not found"
fi

# Verify Chrome installation
verify_chrome_installation

# Verify ChromeDriver installation
if [ -f "$APP_DIR/drivers/chromedriver" ]; then
    CHROMEDRIVER_VERSION=$("$APP_DIR/drivers/chromedriver" --version)
    log_message "✓ ChromeDriver installed: $CHROMEDRIVER_VERSION"
else
    log_error "✗ ChromeDriver not found at $APP_DIR/drivers/chromedriver"
fi

# Verify service status
if systemctl is-active --quiet "$SERVICE_NAME.service"; then
    log_message "✓ AutoAU service is running"
else
    log_warning "✗ AutoAU service is not running"
    log_message "Try starting manually: systemctl start $SERVICE_NAME"
fi

log_message "Installation completed!"
log_message "Service name: $SERVICE_NAME"
log_message "To check status: systemctl status $SERVICE_NAME"
log_message "To view logs: tail -f $LOG_DIR/autoau_output.log"
log_message "To manually control: $APP_DIR/service_control.sh {start|stop|restart|status}"
