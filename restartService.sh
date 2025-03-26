#!/bin/bash

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

# Создаем директорию для логов
mkdir -p logs

# Запускаем приложение
echo "Запускаем приложение..."
nohup python3 main.py > logs/autoau_output.log 2>&1 &

# Выводим PID нового процесса
NEW_PID=$!
echo "Приложение запущено с PID: $NEW_PID"
