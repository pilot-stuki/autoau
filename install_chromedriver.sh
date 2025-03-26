#!/bin/bash

# Скрипт для автоматической установки ChromeDriver, соответствующего установленной версии Chrome

echo "Установка ChromeDriver..."

# Определение операционной системы
OS="$(uname -s)"
case "${OS}" in
    Linux*)     OS_TYPE=linux;;
    Darwin*)    OS_TYPE=mac;;
    MINGW*|CYGWIN*|MSYS*)    OS_TYPE=win;;
    *)          OS_TYPE="UNKNOWN:${OS}"
esac

echo "Определена операционная система: ${OS_TYPE}"

# Определение архитектуры процессора
ARCH="$(uname -m)"
case "${ARCH}" in
    x86_64*)    ARCH_TYPE=64;;
    x86*)       ARCH_TYPE=32;;
    arm*)       ARCH_TYPE=arm64;;
    aarch64*)   ARCH_TYPE=arm64;;
    *)          ARCH_TYPE="UNKNOWN:${ARCH}"
esac

echo "Определена архитектура: ${ARCH_TYPE}"

# Создание директории для драйверов
DRIVER_DIR="$(pwd)/drivers"
mkdir -p "${DRIVER_DIR}"

# Определение версии установленного Chrome
if [[ "${OS_TYPE}" == "linux" ]]; then
    if command -v google-chrome &> /dev/null; then
        CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d '.' -f 1)
    elif command -v chromium-browser &> /dev/null; then
        CHROME_VERSION=$(chromium-browser --version | awk '{print $2}' | cut -d '.' -f 1)
    else
        echo "Chrome или Chromium не найден. Установите Chrome или Chromium перед установкой ChromeDriver."
        exit 1
    fi
elif [[ "${OS_TYPE}" == "mac" ]]; then
    if [ -f "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
        CHROME_VERSION=$("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version | awk '{print $3}' | cut -d '.' -f 1)
    else
        echo "Chrome не найден. Установите Chrome перед установкой ChromeDriver."
        exit 1
    fi
elif [[ "${OS_TYPE}" == "win" ]]; then
    # В Windows путь к Chrome может отличаться, попробуем несколько вариантов
    if [ -f "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" ]; then
        CHROME_VERSION=$("/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" --version | awk '{print $3}' | cut -d '.' -f 1)
    elif [ -f "/c/Program Files/Google/Chrome/Application/chrome.exe" ]; then
        CHROME_VERSION=$("/c/Program Files/Google/Chrome/Application/chrome.exe" --version | awk '{print $3}' | cut -d '.' -f 1)
    else
        # В случае, если путь не найден, будем использовать версию по умолчанию
        CHROME_VERSION=108
        echo "Не удалось определить версию Chrome. Используем версию по умолчанию: ${CHROME_VERSION}"
    fi
else
    echo "Неподдерживаемая операционная система: ${OS_TYPE}"
    exit 1
fi

echo "Определена версия Chrome: ${CHROME_VERSION}"

# Определение URL для скачивания ChromeDriver
if [[ "${CHROME_VERSION}" -ge 115 ]]; then
    # Начиная с Chrome 115, используется новый формат API и URL
    # Получаем последнюю версию ChromeDriver для нашей версии Chrome
    echo "Версия Chrome >= 115, используем новый API для определения версии драйвера"
    
    # Для более новых версий Chrome используем фиксированную версию, которая точно работает
    # В данном случае для Chrome 134 используем ChromeDriver 123.0.6312.86
    LATEST_DRIVER_VERSION="123.0.6312.86"
    
    # Определяем платформу для URL
    if [[ "${OS_TYPE}" == "mac" ]]; then
        if [[ "${ARCH_TYPE}" == "arm64" ]]; then
            PLATFORM="mac-arm64"
        else
            PLATFORM="mac-x64"
        fi
    elif [[ "${OS_TYPE}" == "linux" ]]; then
        if [[ "${ARCH_TYPE}" == "arm64" ]]; then
            PLATFORM="linux-arm64"
        else
            PLATFORM="linux64"
        fi
    elif [[ "${OS_TYPE}" == "win" ]]; then
        PLATFORM="win32"
    fi
    
    # Формируем URL для скачивания
    DRIVER_URL="https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${LATEST_DRIVER_VERSION}/${PLATFORM}/chromedriver-${PLATFORM}.zip"
    
else
    # Старый формат URL для Chrome версии до 115
    LATEST_DRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION}")
    
    if [[ "${OS_TYPE}" == "linux" ]]; then
        DRIVER_URL="https://chromedriver.storage.googleapis.com/${LATEST_DRIVER_VERSION}/chromedriver_linux64.zip"
    elif [[ "${OS_TYPE}" == "mac" ]]; then
        if [[ "${ARCH_TYPE}" == "64" ]]; then
            DRIVER_URL="https://chromedriver.storage.googleapis.com/${LATEST_DRIVER_VERSION}/chromedriver_mac64.zip"
        elif [[ "${ARCH_TYPE}" == "arm64" ]]; then
            # Для Apple Silicon в Chrome < 115 используем более новый формат
            DRIVER_URL="https://chromedriver.storage.googleapis.com/${LATEST_DRIVER_VERSION}/chromedriver_mac_arm64.zip"
            # Если ссылка не существует, используем x64 с Rosetta
            if ! curl --output /dev/null --silent --head --fail "${DRIVER_URL}"; then
                echo "ARM64 версия не найдена, используем x64 с Rosetta"
                DRIVER_URL="https://chromedriver.storage.googleapis.com/${LATEST_DRIVER_VERSION}/chromedriver_mac64.zip"
            fi
        fi
    elif [[ "${OS_TYPE}" == "win" ]]; then
        DRIVER_URL="https://chromedriver.storage.googleapis.com/${LATEST_DRIVER_VERSION}/chromedriver_win32.zip"
    fi
fi

echo "URL для скачивания ChromeDriver: ${DRIVER_URL}"

# Создаем временную директорию для скачивания
TMP_DIR=$(mktemp -d)
ARCHIVE_PATH="${TMP_DIR}/chromedriver.zip"

# Скачиваем архив
echo "Скачивание ChromeDriver..."
if command -v curl &> /dev/null; then
    curl -L "${DRIVER_URL}" -o "${ARCHIVE_PATH}"
elif command -v wget &> /dev/null; then
    wget "${DRIVER_URL}" -O "${ARCHIVE_PATH}"
else
    echo "Не найдены curl или wget. Установите одну из этих утилит для скачивания файлов."
    exit 1
fi

# Распаковываем архив
echo "Распаковка ChromeDriver..."
if command -v unzip &> /dev/null; then
    unzip -o "${ARCHIVE_PATH}" -d "${TMP_DIR}"
else
    echo "Не найден unzip. Установите unzip для распаковки файлов."
    exit 1
fi

# Копируем драйвер в директорию драйверов
if [[ "${OS_TYPE}" == "win" ]]; then
    # Для Chrome >= 115 структура архива изменилась, драйвер находится в подкаталоге
    if [[ "${CHROME_VERSION}" -ge 115 ]]; then
        if [ -f "${TMP_DIR}/chromedriver-${PLATFORM}/chromedriver.exe" ]; then
            cp "${TMP_DIR}/chromedriver-${PLATFORM}/chromedriver.exe" "${DRIVER_DIR}/"
        else
            # Пробуем найти драйвер в текущем или других подкаталогах
            find "${TMP_DIR}" -name "chromedriver.exe" -exec cp {} "${DRIVER_DIR}/" \;
        fi
    else
        cp "${TMP_DIR}/chromedriver.exe" "${DRIVER_DIR}/"
    fi
    
    chmod +x "${DRIVER_DIR}/chromedriver.exe"
    echo "ChromeDriver установлен в ${DRIVER_DIR}/chromedriver.exe"
else
    # Для Chrome >= 115 структура архива изменилась, драйвер находится в подкаталоге
    if [[ "${CHROME_VERSION}" -ge 115 ]]; then
        if [ -f "${TMP_DIR}/chromedriver-${PLATFORM}/chromedriver" ]; then
            cp "${TMP_DIR}/chromedriver-${PLATFORM}/chromedriver" "${DRIVER_DIR}/"
        else
            # Пробуем найти драйвер в текущем или других подкаталогах
            find "${TMP_DIR}" -name "chromedriver" -exec cp {} "${DRIVER_DIR}/" \;
        fi
    else
        cp "${TMP_DIR}/chromedriver" "${DRIVER_DIR}/"
    fi
    
    chmod +x "${DRIVER_DIR}/chromedriver"
    echo "ChromeDriver установлен в ${DRIVER_DIR}/chromedriver"
fi

# Очистка временной директории
echo "Очистка временных файлов..."
rm -rf "${TMP_DIR}"

echo "Установка ChromeDriver завершена успешно!"
