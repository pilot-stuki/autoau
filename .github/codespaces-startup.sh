#!/bin/bash
# Скрипт для автоматического запуска сервиса в GitHub Codespaces

# Установка переменных окружения
export PYTHONUNBUFFERED=1
export DISPLAY=:99

# Запуск Xvfb для эмуляции дисплея (для Selenium)
Xvfb :99 -screen 0 1280x1024x24 > /dev/null 2>&1 &

# Проверка наличия chromedriver
if [ ! -f "/app/drivers/chromedriver" ]; then
    echo "Установка chromedriver..."
    cd /app
    ./install_chromedriver.sh
fi

# Запуск сервиса через supervisor
if [ -f "/usr/bin/supervisord" ]; then
    echo "Запуск сервиса через supervisor..."
    /usr/bin/supervisord -c /etc/supervisor/conf.d/autoau.conf
else
    # Альтернативный способ запуска, если supervisor недоступен
    echo "Запуск сервиса напрямую..."
    cd /app
    nohup python main.py > /tmp/autoau.log 2>&1 &
fi

echo "Сервис запущен! Логи доступны в /tmp/autoau.log"
