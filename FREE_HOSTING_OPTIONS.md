# Альтернативные бесплатные варианты размещения AutoAU

GitHub Codespaces имеет ограничения для длительной работы сервисов. Ниже приведены альтернативные бесплатные платформы для развертывания вашего проекта.

## 1. Railway

Railway предлагает бесплатный тарифный план с лимитом часов работы.

### Настройка Railway:

1. Зарегистрируйтесь на [Railway](https://railway.app/)

2. Установите Railway CLI:
   ```bash
   npm i -g @railway/cli
   ```

3. Авторизуйтесь:
   ```bash
   railway login
   ```

4. Инициализируйте проект:
   ```bash
   railway init
   ```

5. Разверните приложение:
   ```bash
   railway up
   ```

6. Не забудьте настроить переменные окружения в панели управления Railway, если требуется.

## 2. Fly.io

Fly.io предлагает бесплатный тарифный план для небольших приложений.

### Настройка Fly.io:

1. Зарегистрируйтесь на [Fly.io](https://fly.io/)

2. Установите Fly CLI:
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

3. Авторизуйтесь:
   ```bash
   fly auth login
   ```

4. Инициализируйте приложение:
   ```bash
   fly launch
   ```

5. Разверните приложение:
   ```bash
   fly deploy
   ```

## 3. Oracle Cloud Free Tier

Oracle Cloud предлагает по-настоящему бесплатный уровень с двумя виртуальными машинами ARM, которые можно использовать неограниченно долго.

### Настройка Oracle Cloud:

1. Зарегистрируйтесь на [Oracle Cloud](https://www.oracle.com/cloud/free/)

2. Создайте виртуальную машину на базе ARM (Oracle Linux)

3. Установите необходимое ПО:
   ```bash
   sudo yum update -y
   sudo yum install -y python3 python3-pip git
   ```

4. Клонируйте ваш репозиторий:
   ```bash
   git clone https://github.com/your-username/autoau.git
   cd autoau
   ```

5. Установите зависимости:
   ```bash
   pip3 install -r requirements.txt
   ```

6. Установите Chrome и ChromeDriver:
   ```bash
   chmod +x install_chromedriver.sh
   ./install_chromedriver.sh
   ```

7. Настройте автозапуск через systemd:
   ```bash
   sudo nano /etc/systemd/system/autoau.service
   ```

   ```
   [Unit]
   Description=AutoAU Service
   After=network.target

   [Service]
   Type=simple
   User=opc
   WorkingDirectory=/home/opc/autoau
   ExecStart=/usr/bin/python3 /home/opc/autoau/main.py
   Restart=always
   RestartSec=5
   Environment=DISPLAY=:99

   [Install]
   WantedBy=multi-user.target
   ```

8. Настройте Xvfb:
   ```bash
   sudo nano /etc/systemd/system/xvfb.service
   ```

   ```
   [Unit]
   Description=X Virtual Frame Buffer
   After=network.target

   [Service]
   ExecStart=/usr/bin/Xvfb :99 -screen 0 1280x1024x24
   Restart=always
   RestartSec=2

   [Install]
   WantedBy=multi-user.target
   ```

9. Включите и запустите сервисы:
   ```bash
   sudo systemctl enable xvfb.service
   sudo systemctl start xvfb.service
   sudo systemctl enable autoau.service
   sudo systemctl start autoau.service
   ```

10. Проверьте статус:
    ```bash
    sudo systemctl status autoau.service
    ```

## 4. Render

Render предлагает бесплатный тарифный план для веб-сервисов.

### Настройка Render:

1. Зарегистрируйтесь на [Render](https://render.com/)

2. Создайте новый Web Service и подключите ваш GitHub репозиторий

3. Настройте команду для сборки:
   ```
   pip install -r requirements.txt
   chmod +x install_chromedriver.sh
   ./install_chromedriver.sh
   ```

4. Настройте команду для запуска:
   ```
   python main.py
   ```

5. Выберите бесплатный тарифный план

## Важные замечания

1. **Использование ресурсов**: Большинство бесплатных планов имеют ограничения на вычислительные ресурсы и время работы. Настройте ваш проект (в `config.yaml`) для максимальной экономии ресурсов.

2. **Headless режим**: Для всех указанных платформ рекомендуется использовать Chrome в режиме headless (без GUI), что уже должно быть реализовано в вашем проекте.

3. **Постоянное хранилище**: Некоторые платформы могут очищать файловую систему при перезапуске. Если вам нужно сохранять данные между запусками, рассмотрите возможность использования внешнего хранилища.

4. **Ограничения по времени**: Некоторые бесплатные планы могут иметь ограничения на общее время работы в месяц. Учтите это при настройке частоты проверок.
