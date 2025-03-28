FROM python:3.10-slim

# Установка необходимых пакетов
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    gnupg \
    curl \
    xvfb \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Установка Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Настройка директории проекта
WORKDIR /app
COPY . /app/

# Установка зависимостей Python
RUN pip install --no-cache-dir -r requirements.txt

# Запуск скрипта для установки Chrome Driver
RUN chmod +x install_chromedriver.sh && ./install_chromedriver.sh

# Копирование конфигурации supervisor
COPY supervisord.conf /etc/supervisor/conf.d/autoau.conf

# Создание директории для логов supervisor
RUN mkdir -p /var/log/supervisor

# Запуск supervisor как сервис
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/autoau.conf"]