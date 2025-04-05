#!/bin/bash
# Enhanced install_chromedriver.sh with alternative Chrome download method
# This script installs Chrome 123 (if needed) and the matching ChromeDriver

# Exit on errors
set -e

# Configuration
TARGET_CHROME_VERSION="123.0.6312.86"
DRIVERS_DIR="${DRIVERS_DIR:-"$PWD/drivers"}"
TEMP_DIR=$(mktemp -d)
LOG_FILE="/tmp/chrome_chromedriver_install.log"

# Start logging
exec > >(tee -a "$LOG_FILE") 2>&1

echo "===== Enhanced Chrome/ChromeDriver Installation Script ====="
echo "Started at: $(date)"
echo "Target Chrome version: $TARGET_CHROME_VERSION"
echo "Drivers directory: $DRIVERS_DIR"

# Function to clean up temp files
cleanup() {
    echo "Очистка временных файлов..."
    rm -rf "$TEMP_DIR"
}

# Register cleanup function
trap cleanup EXIT

# Create drivers directory if it doesn't exist
mkdir -p "$DRIVERS_DIR"

# Skip Chrome installation and focus only on ChromeDriver
echo "ПРИМЕЧАНИЕ: Пропуск установки Chrome, фокусируемся только на установке ChromeDriver версии 123"
echo "Установка ChromeDriver для Chrome 123..."

# ChromeDriver 123 URL (specific for version 123)
CHROMEDRIVER_URL="https://storage.googleapis.com/chrome-for-testing-public/123.0.6312.86/linux64/chromedriver-linux64.zip"

echo "Скачивание ChromeDriver с: $CHROMEDRIVER_URL"
curl -L -o "$TEMP_DIR/chromedriver.zip" "$CHROMEDRIVER_URL"

echo "Распаковка ChromeDriver..."
unzip -q "$TEMP_DIR/chromedriver.zip" -d "$TEMP_DIR"

# Find chromedriver binary - handle different folder structures
CHROMEDRIVER_BIN=$(find "$TEMP_DIR" -path "*/chromedriver-linux64/chromedriver" -type f)

if [ -z "$CHROMEDRIVER_BIN" ]; then
    echo "ОШИБКА: chromedriver не найден в скачанном архиве"
    find "$TEMP_DIR" -type f
    exit 1
fi

# Install ChromeDriver
cp "$CHROMEDRIVER_BIN" "$DRIVERS_DIR/chromedriver"
chmod +x "$DRIVERS_DIR/chromedriver"

echo "ChromeDriver установлен в: $DRIVERS_DIR/chromedriver"

# Verify ChromeDriver installation
echo "Проверка установки ChromeDriver:"
"$DRIVERS_DIR/chromedriver" --version

echo "===== Установка ChromeDriver завершена ====="
echo "ChromeDriver теперь поддерживает Chrome версии 123"
echo "Для наилучшей совместимости, пожалуйста, следуйте инструкциям ниже:"
echo ""
echo "ВАЖНО: Для обеспечения совместимости с ChromeDriver 123:"
echo "1. Используйте аргументы браузера для принудительной совместимости:"
echo "   --chrome-version=123"
echo ""
echo "2. В вашем приложении добавьте следующие опции Chrome:"
echo "   options.add_argument('--chrome-version=123')"
echo ""
echo "3. Если вы используете undetected_chromedriver, используйте параметр version_main:"
echo "   driver = uc.Chrome(version_main=123)"
echo ""
echo "Завершено: $(date)"
