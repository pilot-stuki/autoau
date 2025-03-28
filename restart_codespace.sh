#!/bin/bash

# Скрипт для перезапуска сервиса в GitHub Codespaces

# Настройка переменных окружения
export DISPLAY=:99

# Проверка и запуск Xvfb, если он не запущен
if ! pgrep -x "Xvfb" > /dev/null; then
    echo "Запуск Xvfb..."
    Xvfb :99 -screen 0 1280x1024x24 > /dev/null 2>&1 &
    sleep 2
fi

# Останавливаем текущий процесс, если он запущен
PID=$(ps -ef | grep python | grep "main.py" | grep -v grep | awk '{print $2}')
if [ ! -z "$PID" ]; then
    echo "Останавливаем текущий процесс (PID: $PID)..."
    kill $PID
    sleep 2
    # Если процесс все еще работает, завершаем его принудительно
    if ps -p $PID > /dev/null; then
        echo "Процесс все еще работает, завершаем принудительно..."
        kill -9 $PID
    fi
fi

# Очищаем процессы Chrome и ChromeDriver
echo "Очищаем процессы Chrome и ChromeDriver..."
pkill -f "chromedriver" || true
pkill -f "chrome" || true

# Проверка наличия драйвера Chrome
if [ ! -f "drivers/chromedriver" ]; then
    echo "ChromeDriver не найден, запуск установки..."
    ./install_chromedriver.sh
fi

# Создаем директорию для логов
mkdir -p logs

# Оптимизируем для ограниченных ресурсов в Codespaces
export CODESPACE_OPTIMIZATION=true

# Запускаем приложение с оптимизацией для Codespaces
echo "Запускаем приложение в Codespaces..."
nohup python main.py > logs/codespace_autoau.log 2>&1 &

# Выводим PID нового процесса
NEW_PID=$!
echo "Приложение запущено с PID: $NEW_PID"
echo "Логи доступны в файле: logs/codespace_autoau.log"

# Подсказка по мониторингу
echo ""
echo "Для мониторинга логов в реальном времени используйте:"
echo "tail -f logs/codespace_autoau.log"
echo ""
echo "Для проверки состояния процесса используйте:"
echo "ps -ef | grep main.py"
