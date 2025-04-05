#!/bin/bash
# install_autoau.sh - Installation script for AutoAU service
# This script sets up the AutoAU application with a Python virtual environment
# using a newer Python version (3.9) alongside the system Python 3.6

# Exit on any error
set -e

# Configuration variables
APP_DIR="/opt/autoau"                    # Application installation directory
SERVICE_NAME="autoau"                    # Service name
SERVICE_USER="autoau"                    # User to run the service
PYTHON_VERSION="3.10.13"                 # Python version to install (using a more stable version)
PYENV_ROOT="$APP_DIR/.pyenv"             # pyenv installation directory
PYTHON_PATH="$PYENV_ROOT/versions/$PYTHON_VERSION/bin/python"  # Path to newer Python
VENV_DIR="$APP_DIR/venv"                 # Virtual environment directory
LOG_DIR="$APP_DIR/logs"                  # Log directory
SESSION_DIR="$APP_DIR/sessions"          # Session directory
PROJECT_SOURCE="/home/opc/autoau"        # Source folder - CHANGE THIS if needed

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

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run this script as root"
    exit 1
fi

# Install required development packages for building Python
log_message "Installing Python build dependencies..."
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

# Install pyenv for the service user
log_message "Installing pyenv to manage Python versions..."
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
    
    # Create a script in the service user's home directory
    PYENV_SCRIPT="$APP_DIR/install_python.sh"
    
    # Create a script to run as the service user
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
log_message "Creating Python virtual environment with Python $PYTHON_VERSION..."
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

# Create directories for logs, sessions, and drivers
log_message "Creating log, session, and driver directories..."
mkdir -p "$LOG_DIR" "$SESSION_DIR" "$APP_DIR/drivers"
chown -R "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR" "$SESSION_DIR" "$APP_DIR/drivers"

# Check if ChromeDriver is already installed
if [ -f "/home/opc/autoau/drivers/chromedriver" ]; then
    log_message "Found manually installed ChromeDriver, setting it up..."
    # Copy the manually installed ChromeDriver to the application directory
    cp "/home/opc/autoau/drivers/chromedriver" "$APP_DIR/drivers/"
    chmod +x "$APP_DIR/drivers/chromedriver"
    chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/drivers/chromedriver"
else
    log_warning "ChromeDriver not found at /home/opc/autoau/drivers/chromedriver"
    log_message "You may need to manually install ChromeDriver"
fi

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

# Install dependencies in virtual environment
log_message "Installing Python dependencies..."
su -c "$VENV_DIR/bin/pip install -r $APP_DIR/requirements.txt" "$SERVICE_USER"

# Install the latest compatible versions of SSL-related packages
log_message "Installing SSL-related packages..."
su -c "$VENV_DIR/bin/pip install pyOpenSSL cryptography" "$SERVICE_USER"

# Create an enhanced version of the restart script
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

# Verify that the service is running
if systemctl is-active --quiet "$SERVICE_NAME.service"; then
    log_message "AutoAU service is now running"
else
    log_error "Failed to start AutoAU service. Check logs with: journalctl -u $SERVICE_NAME.service"
    exit 1
fi

# Install Chrome if it's not already installed
if ! command -v google-chrome &> /dev/null; then
    log_message "Installing Chrome browser..."
    
    # Add Chrome repository
    cat > /etc/yum.repos.d/google-chrome.repo << EOF
[google-chrome]
name=google-chrome
baseurl=http://dl.google.com/linux/chrome/rpm/stable/x86_64
enabled=1
gpgcheck=1
gpgkey=https://dl.google.com/linux/linux_signing_key.pub
EOF

    # Install Chrome
    yum install -y google-chrome-stable
    
    if command -v google-chrome &> /dev/null; then
        log_message "Chrome installed successfully"
    else
        log_warning "Chrome installation may have failed. You may need to install it manually."
    fi
else
    log_message "Chrome is already installed"
fi

log_message "Installation completed successfully!"
log_message "Service name: $SERVICE_NAME"
log_message "To check status: systemctl status $SERVICE_NAME"
log_message "To view logs: tail -f $LOG_DIR/autoau_output.log"
log_message "To manually control: $APP_DIR/service_control.sh {start|stop|restart|status}"
