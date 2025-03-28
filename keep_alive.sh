#!/bin/bash

# Скрипт для поддержания активности GitHub Codespace
# Запускает небольшую активность каждые 20 минут для предотвращения
# автоматической остановки неактивного Codespace

echo "Запуск скрипта поддержания активности для GitHub Codespace"
echo "ВНИМАНИЕ: Оставьте это окно терминала открытым"
echo "Скрипт будет выполнять легкие действия каждые 20 минут"
echo "Нажмите Ctrl+C для остановки"
echo ""

counter=0

while true; do
    # Увеличиваем счетчик
    counter=$((counter + 1))
    
    # Текущее время
    current_time=$(date "+%Y-%m-%d %H:%M:%S")
    
    # Выполняем легкие действия для поддержания активности
    echo "[$current_time] Поддержание активности #$counter"
    
    # Проверка статуса автоматизации
    ps_output=$(ps -ef | grep python | grep "main.py" | grep -v grep)
    if [ -z "$ps_output" ]; then
        echo "[$current_time] ВНИМАНИЕ: Процесс автоматизации не запущен!"
        echo "[$current_time] Запустите процесс командой: ./restart_codespace.sh"
    else
        pid=$(echo $ps_output | awk '{print $2}')
        echo "[$current_time] Процесс автоматизации активен (PID: $pid)"
    fi
    
    # Проверка использования ресурсов
    echo "[$current_time] Использование памяти:"
    free -m | grep "Mem:" | awk '{print "  Всего: " $2 " MB, Использовано: " $3 " MB, Свободно: " $4 " MB"}'
    
    echo "[$current_time] Загрузка CPU:"
    top -bn1 | grep "Cpu(s)" | awk '{print "  " $0}'
    
    echo "[$current_time] Следующая проверка через 20 минут..."
    echo ""
    
    # Ожидание 20 минут (1200 секунд)
    sleep 1200
done
