#!/bin/bash
# manual_chrome_fix.sh - Directly creates the Chrome directory structure

# Exit on any error
set -e

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

log_message "Starting manual Chrome directory fix..."

# Try to find where Chrome is actually installed
log_message "Searching for Chrome installation..."

# Method 1: Search using the RPM database
CHROME_FILES=$(rpm -ql google-chrome-stable 2>/dev/null)
if [ -n "$CHROME_FILES" ]; then
    log_message "Found Chrome files through RPM database"
    
    # Try to find the main Chrome binary
    CHROME_BIN=$(echo "$CHROME_FILES" | grep -E "/google-chrome$" | head -1)
    if [ -n "$CHROME_BIN" ]; then
        log_message "Found Chrome binary at: $CHROME_BIN"
        CHROME_DIR=$(dirname "$CHROME_BIN")
        log_message "Chrome installation directory: $CHROME_DIR"
    fi
fi

# Method 2: Search in common locations
if [ -z "$CHROME_BIN" ]; then
    for DIR in /usr/bin /usr/local/bin /opt /usr/share; do
        FOUND_BIN=$(find $DIR -name "google-chrome" -type f 2>/dev/null | head -1)
        if [ -n "$FOUND_BIN" ]; then
            CHROME_BIN=$FOUND_BIN
            CHROME_DIR=$(dirname "$CHROME_BIN")
            log_message "Found Chrome binary at: $CHROME_BIN"
            log_message "Chrome installation directory: $CHROME_DIR"
            break
        fi
    done
fi

# Method 3: Use which (but this may fail if not in PATH)
if [ -z "$CHROME_BIN" ]; then
    CHROME_BIN=$(which google-chrome 2>/dev/null || echo "")
    if [ -n "$CHROME_BIN" ]; then
        if [ -L "$CHROME_BIN" ]; then
            # Follow symlink to find real binary
            REAL_BIN=$(readlink -f "$CHROME_BIN")
            CHROME_BIN=$REAL_BIN
        fi
        CHROME_DIR=$(dirname "$CHROME_BIN")
        log_message "Found Chrome binary at: $CHROME_BIN"
        log_message "Chrome installation directory: $CHROME_DIR"
    fi
fi

# If we've found Chrome, create the expected directory structure
if [ -n "$CHROME_BIN" ]; then
    log_message "Creating /opt/google/chrome directory structure..."
    
    # Create directory
    mkdir -p /opt/google/chrome
    
    if [ -d "$CHROME_DIR" ] && [ "$CHROME_DIR" != "/opt/google/chrome" ]; then
        # Copy all Chrome files to the new directory
        log_message "Copying Chrome files from $CHROME_DIR to /opt/google/chrome"
        cp -r "$CHROME_DIR"/* /opt/google/chrome/
    else
        # If we only found the binary but not the full directory, create a minimal structure
        log_message "Creating minimal Chrome structure in /opt/google/chrome"
        cp "$CHROME_BIN" /opt/google/chrome/google-chrome
    fi
    
    # Ensure the binary is executable
    chmod +x /opt/google/chrome/google-chrome
    
    # Create a symlink to ensure Chrome is in PATH
    ln -sf /opt/google/chrome/google-chrome /usr/bin/google-chrome
    
    log_message "Testing Chrome installation..."
    if [ -f "/opt/google/chrome/google-chrome" ]; then
        /opt/google/chrome/google-chrome --version && log_message "Chrome test successful!" || log_error "Chrome test failed"
    else
        log_error "Chrome binary not found at /opt/google/chrome/google-chrome"
    fi
else
    # If we can't find Chrome, create a minimal structure from the RPM
    log_message "Chrome binary not found. Creating minimal structure from RPM..."
    
    # Find the Chrome 123 RPM
    CHROME_RPM=$(find /home/opc -name "google-chrome-stable-123*.rpm" 2>/dev/null | head -1)
    
    if [ -n "$CHROME_RPM" ]; then
        log_message "Found Chrome RPM: $CHROME_RPM"
        
        # Create a temp directory for extraction
        TEMP_DIR=$(mktemp -d)
        
        # Extract the RPM contents
        log_message "Extracting RPM contents..."
        cd $TEMP_DIR
        rpm2cpio "$CHROME_RPM" | cpio -idmv
        
        # Find the Chrome binary in the extracted files
        EXTRACTED_BIN=$(find $TEMP_DIR -name "google-chrome" -type f | head -1)
        
        if [ -n "$EXTRACTED_BIN" ]; then
            EXTRACTED_DIR=$(dirname "$EXTRACTED_BIN")
            log_message "Found Chrome binary in extracted RPM at: $EXTRACTED_BIN"
            
            # Create the target directory
            mkdir -p /opt/google/chrome
            
            # Copy the files
            log_message "Copying Chrome files to /opt/google/chrome"
            cp -r "$EXTRACTED_DIR"/* /opt/google/chrome/
            
            # Ensure the binary is executable
            chmod +x /opt/google/chrome/google-chrome
            
            # Create a symlink to ensure Chrome is in PATH
            ln -sf /opt/google/chrome/google-chrome /usr/bin/google-chrome
        else
            log_error "Chrome binary not found in extracted RPM"
        fi
        
        # Cleanup
        rm -rf $TEMP_DIR
    else
        log_error "Chrome RPM not found"
    fi
fi

# Update browser_service.py to specify Chrome binary path
log_message "Updating browser_service.py to specify Chrome binary path..."
BROWSER_SERVICE_FILE="/opt/autoau/browser_service.py"

if [ -f "$BROWSER_SERVICE_FILE" ]; then
    # Backup the file first
    cp "$BROWSER_SERVICE_FILE" "${BROWSER_SERVICE_FILE}.bak"
    
    # Add Chrome binary path to options
    if ! grep -q "options.binary_location" "$BROWSER_SERVICE_FILE"; then
        sed -i '/options.add_argument.*--disable-blink-features=AutomationControlled/a \        # Explicitly set Chrome binary path\n        options.binary_location = "/opt/google/chrome/google-chrome"' "$BROWSER_SERVICE_FILE"
        log_message "Added Chrome binary location to browser_service.py"
    else
        log_message "Chrome binary location already set in browser_service.py"
    fi
    
    # Make sure Chrome path is available to the service user
    chown autoau:autoau "$BROWSER_SERVICE_FILE"
    
    log_message "browser_service.py updated successfully"
else
    log_warning "browser_service.py not found at $BROWSER_SERVICE_FILE"
    
    # Try to find the correct path
    FOUND_SERVICE=$(find /opt/autoau -name "browser_service.py" 2>/dev/null)
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
        
        # Make sure Chrome path is available to the service user
        chown autoau:autoau "$FOUND_SERVICE"
        
        log_message "browser_service.py updated successfully"
    else
        log_error "Could not find browser_service.py"
    fi
fi

# Restart the AutoAU service
log_message "Restarting AutoAU service..."
systemctl restart autoau

# Verify that the service is running
if systemctl is-active --quiet autoau; then
    log_message "✓ AutoAU service restarted successfully"
else
    log_error "✗ Failed to restart AutoAU service"
    log_message "Check logs with: journalctl -u autoau"
fi

log_message "Fix completed!"
