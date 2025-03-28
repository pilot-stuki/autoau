# Запуск AutoAU сервиса в GitHub Codespaces

## Шаг 1: Создание репозитория GitHub

1. Создайте новый репозиторий на GitHub
2. Загрузите туда все файлы проекта
3. Убедитесь, что файлы `.devcontainer/devcontainer.json`, `Dockerfile` и `.github/codespaces-startup.sh` находятся в репозитории

## Шаг 2: Создание Codespace

1. На странице вашего репозитория нажмите кнопку "Code"
2. Выберите вкладку "Codespaces"
3. Нажмите "Create codespace on main"

## Шаг 3: Первоначальная настройка

1. После запуска Codespace выполните следующие команды:
   ```bash
   chmod +x update_permissions.sh
   ./update_permissions.sh
   ```

2. Проверьте работу сервиса в тестовом режиме:
   ```bash
   python main.py --test-mode
   ```

## Шаг 4: Запуск сервиса

1. Для запуска сервиса выполните:
   ```bash
   bash .github/codespaces-startup.sh
   ```

2. Проверка статуса:
   ```bash
   ps -ef | grep python
   ```

3. Просмотр логов:
   ```bash
   tail -f /tmp/autoau.log
   ```

## Поддержание работы сервиса

GitHub Codespaces имеет ограничение времени бездействия - они останавливаются после 30 минут неактивности. Чтобы этого избежать:

1. Установите GitHub CLI (https://cli.github.com/)

2. Настройте скрипт для периодического подключения к Codespace:
   ```bash
   # На вашем локальном компьютере
   while true; do
     gh codespace ssh -c [имя-вашего-codespace] -- "echo 'keepalive'"
     sleep 25m
   done
   ```

3. Также можно использовать автоматизированные сервисы для отправки регулярных запросов к вашему Codespace, например, с помощью GitHub Actions или внешних сервисов мониторинга.

## Экономия ресурсов

Для оптимального использования ресурсов:

1. В файле `config.yaml` установите параметр `optimize_for_low_resources: true`

2. Используйте минимальное необходимое количество аккаунтов

3. Настройте более длительные интервалы между проверками в файле `main.py` (функция `calculate_next_run_interval`)
