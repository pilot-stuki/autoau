import os
import sys
import time
import signal
import logging
import threading
import subprocess
import platform
import atexit
import tempfile
import shutil
import random
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    WebDriverException, 
    SessionNotCreatedException,
    TimeoutException
)

from resource_manager import get_resource_manager

# Получение логгера
logger = logging.getLogger(__name__)

# Синглтон и блокировка для потокобезопасности
_browser_service_instance = None
_instance_lock = threading.Lock()


class BrowserNotFoundException(Exception):
    """Исключение, вызываемое при невозможности найти или запустить браузер"""
    pass


class BrowserVersionMismatchException(Exception):
    """Исключение, вызываемое при несоответствии версий Chrome и ChromeDriver"""
    pass


class BrowserService:
    """
    Сервис для управления браузерами и WebDriver с оптимизацией ресурсов
    """
    
    def __init__(self):
        """Инициализация сервиса управления браузерами"""
        self.resource_mgr = get_resource_manager()
        self.system = platform.system()
        
        # Настройка параметров для разных систем
        if self.system == 'Windows':
            self.chrome_path = self._detect_chrome_path_windows()
            self.driver_path = self._get_driver_path_windows()
        elif self.system == 'Darwin':  # macOS
            self.chrome_path = self._detect_chrome_path_macos()
            self.driver_path = self._get_driver_path_macos()
        else:  # Linux и другие UNIX-подобные
            self.chrome_path = self._detect_chrome_path_linux()
            self.driver_path = self._get_driver_path_linux()
            
        # Блокировка для синхронизации доступа к драйверам
        self.driver_lock = threading.Lock()
        
        # Список активных драйверов для отслеживания и очистки
        self.active_drivers = []
        
        # Скрываем ли окна браузера
        self.headless_mode = True
        
        # Параметр для экономии ресурсов на Codespace
        self.optimize_for_low_resources = self.resource_mgr.should_optimize_for_low_resources()
        
        logger.info(f"Инициализирован BrowserService: система={self.system}, "
                    f"chrome_path={self.chrome_path}, driver_path={self.driver_path}, "
                    f"headless={self.headless_mode}, optimize={self.optimize_for_low_resources}")
        
        # Регистрация очистки ресурсов при завершении
        atexit.register(self.cleanup_all_drivers)

    def _detect_chrome_path_windows(self):
        """Определяет путь к Chrome на Windows"""
        possible_paths = [
            os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), r'Google\Chrome\Application\chrome.exe'),
            os.path.join(os.environ.get('PROGRAMFILES', ''), r'Google\Chrome\Application\chrome.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\Application\chrome.exe')
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
                
        # Если Chrome не найден в стандартных местах, пробуем найти через реестр
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe')
            chrome_path, _ = winreg.QueryValueEx(key, '')
            return chrome_path
        except:
            pass
            
        return None

    def _detect_chrome_path_macos(self):
        """Определяет путь к Chrome на macOS"""
        possible_paths = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            os.path.expanduser('~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
                
        return None

    def _detect_chrome_path_linux(self):
        """Определяет путь к Chrome на Linux"""
        try:
            # Пытаемся найти Chrome в системных путях
            chrome_path = subprocess.check_output(['which', 'google-chrome'], 
                                                 stderr=subprocess.STDOUT).decode().strip()
            if os.path.exists(chrome_path):
                return chrome_path
        except subprocess.CalledProcessError:
            pass
            
        possible_paths = [
            '/usr/bin/google-chrome',
            '/usr/bin/chromium-browser',
            '/usr/bin/chromium',
            '/snap/bin/chromium',
            '/snap/bin/google-chrome',
            '/opt/google/chrome/google-chrome',
            '/opt/autoau/bin/google-chrome'
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
                
        return None

    def _get_driver_path_windows(self):
        """Возвращает путь к Chrome Driver на Windows"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        driver_path = os.path.join(base_dir, 'drivers', 'chromedriver.exe')
        
        # Проверяем, существует ли драйвер
        if not os.path.exists(driver_path):
            driver_dir = os.path.dirname(driver_path)
            os.makedirs(driver_dir, exist_ok=True)
            logger.warning(f"Chrome Driver не найден по пути {driver_path}. "
                          f"Требуется установить драйвер.")
            
        return driver_path

    def _get_driver_path_macos(self):
        """Возвращает путь к Chrome Driver на macOS"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        driver_path = os.path.join(base_dir, 'drivers', 'chromedriver')
        
        # Проверяем, существует ли драйвер
        if not os.path.exists(driver_path):
            driver_dir = os.path.dirname(driver_path)
            os.makedirs(driver_dir, exist_ok=True)
            logger.warning(f"Chrome Driver не найден по пути {driver_path}. "
                          f"Требуется установить драйвер.")
            
        return driver_path

    def _get_driver_path_linux(self):
        """Возвращает путь к Chrome Driver на Linux"""
        # Сначала проверяем наличие драйвера в системных путях
        try:
            driver_path = subprocess.check_output(['which', 'chromedriver'], 
                                                stderr=subprocess.STDOUT).decode().strip()
            if os.path.exists(driver_path):
                return driver_path
        except subprocess.CalledProcessError:
            pass
        
        # Если не нашли в системе, проверяем в папке проекта
        base_dir = os.path.dirname(os.path.abspath(__file__))
        driver_path = os.path.join(base_dir, 'drivers', 'chromedriver')
        
        # Проверяем, существует ли драйвер
        if not os.path.exists(driver_path):
            driver_dir = os.path.dirname(driver_path)
            os.makedirs(driver_dir, exist_ok=True)
            logger.warning(f"Chrome Driver не найден по пути {driver_path}. "
                          f"Требуется установить драйвер.")
            
        return driver_path

    def install_chromedriver(self):
        """
        Устанавливает Chrome Driver, соответствующий версии Chrome
        """
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from webdriver_manager.core.os_manager import ChromeType
            
            # Установка драйвера с использованием webdriver-manager, который автоматически подберет
            # совместимую версию драйвера для установленной версии Chrome
            driver_path = ChromeDriverManager().install()
            
            # Копируем драйвер в папку проекта для постоянного доступа
            base_dir = os.path.dirname(os.path.abspath(__file__))
            driver_dir = os.path.join(base_dir, 'drivers')
            os.makedirs(driver_dir, exist_ok=True)
            
            if self.system == 'Windows':
                target_path = os.path.join(driver_dir, 'chromedriver.exe')
            else:
                target_path = os.path.join(driver_dir, 'chromedriver')
                
            shutil.copy2(driver_path, target_path)
            
            # Устанавливаем права на выполнение для UNIX-подобных систем
            if self.system != 'Windows':
                os.chmod(target_path, 0o755)
                
            self.driver_path = target_path
            logger.info(f"Chrome Driver успешно установлен в {target_path}")
            
            return target_path
        except ImportError:
            logger.error("Не установлен пакет webdriver-manager. Установите его командой: pip install webdriver-manager")
            raise
        except Exception as e:
            logger.error(f"Ошибка при установке Chrome Driver: {e}")
            raise

    def _get_chrome_options(self, headless=None, incognito=True):
        """
        Создает оптимизированные опции для Chrome
        
        Args:
            headless: Запускать ли браузер в безголовом режиме
            incognito: Запускать ли в режиме инкогнито
            
        Returns:
            ChromeOptions: Настроенные опции Chrome
        """
        from selenium.webdriver.chrome.options import Options
        options = Options()
        
        # Режим headless
        if headless is None:
            # Если значение не указано, используем глобальную настройку
            headless = self.headless_mode
            
        if headless:
            options.add_argument('--headless=new')
            logger.debug("Включен безголовый режим Chrome")
        
        # Устанавливаем путь к бинарному файлу Chrome
        chrome_binary = os.environ.get('CHROME_PATH', '/opt/google/chrome/google-chrome')
        if os.path.exists(chrome_binary):
            options.binary_location = chrome_binary
            logger.debug(f"Установлен путь к Chrome: {chrome_binary}")
        elif self.chrome_path and os.path.exists(self.chrome_path):
            options.binary_location = self.chrome_path
            logger.debug(f"Установлен путь к Chrome: {self.chrome_path}")
            
        # Режим инкогнито
        if incognito:
            options.add_argument('--incognito')
            
        # Общие оптимизации
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-translate')
        options.add_argument('--start-maximized')
        options.add_argument('--disable-background-networking')
        
        # Критически важные параметры для запуска в серверной среде
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        
        # Параметры для стабильного запуска в headless режиме
        options.add_argument('--window-size=1280,1024')
        
        # Отключаем логирование
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        options.add_argument('--log-level=3')  # Только критические ошибки
        
        # Маскируем автоматизацию
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--disable-blink-features=AutomationControlled')
        
        # Force compatibility with ChromeDriver 123
        options.add_argument('--chrome-version=123')
        
        # User agent
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36')
        
        # Оптимизации для систем с ограниченными ресурсами
        if self.optimize_for_low_resources:
            options.add_argument('--disable-extensions')
            options.add_argument('--js-flags="--max-old-space-size=128"')
            options.add_argument('--mute-audio')
            options.add_argument('--blink-settings=imagesEnabled=false')
            
        return options
        
    def create_driver(self, headless=None, incognito=True, implicit_wait=10):
        """
        Создает новый экземпляр WebDriver с оптимизированными настройками
        
        Args:
            headless: Запускать ли браузер в безголовом режиме
            incognito: Запускать ли в режиме инкогнито
            implicit_wait: Время ожидания элементов по умолчанию
            
        Returns:
            webdriver.Chrome: Экземпляр драйвера Chrome
        """
        with self.driver_lock:  # блокировка для синхронизации
            # Проверяем нагрузку на систему перед созданием нового драйвера
            if self.resource_mgr.memory_usage_critical():
                # При критическом использовании памяти сначала очищаем ресурсы
                logger.warning("Критическое использование памяти перед созданием драйвера. Запуск очистки.")
                self.cleanup_unused_drivers()
                self.resource_mgr.force_garbage_collection()
                
            # Для работы в GitHub Codespace применяем дополнительные оптимизации
            is_codespace = self.resource_mgr.is_running_in_github_codespace()
            is_low_resources = self.resource_mgr.should_optimize_for_low_resources()
                
            # В GitHub Codespace или при ограниченных ресурсах всегда используем headless
            if is_codespace or is_low_resources:
                headless = True
                
            max_retries = 3
            retry_count = 0
            last_exception = None
            
            # Создаем временную директорию для данных пользователя Chrome
            user_data_dir = None
            
            while retry_count < max_retries:
                try:
                    options = self._get_chrome_options(headless, incognito)
                    
                    # *** КРИТИЧЕСКИЕ ИЗМЕНЕНИЯ ДЛЯ РЕШЕНИЯ ПРОБЛЕМЫ С DEVTOOLSACTIVEPORT ***
                    
                    # 1. Создаем уникальную временную директорию для профиля Chrome
                    try:
                        user_data_dir = tempfile.mkdtemp(prefix="chrome_user_data_")
                        logger.debug(f"Создана временная директория для Chrome: {user_data_dir}")
                        options.add_argument(f"--user-data-dir={user_data_dir}")
                    except Exception as e:
                        logger.warning(f"Не удалось создать временную директорию: {e}")
                    
                    # 2. Используем случайный порт для отладки, чтобы избежать конфликтов
                    random_port = random.randint(9222, 19222)
                    options.add_argument(f"--remote-debugging-port={random_port}")
                    
                    # 3. Принудительная установка важных опций
                    if "--disable-dev-shm-usage" not in str(options.arguments):
                        options.add_argument("--disable-dev-shm-usage")
                    
                    if "--no-sandbox" not in str(options.arguments):
                        options.add_argument("--no-sandbox")
                    
                    # 4. Устанавливаем пути к логам Chrome для диагностики
                    log_path = None
                    try:
                        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
                        os.makedirs(log_dir, exist_ok=True)
                        log_path = os.path.join(log_dir, f"chrome_debug_{int(time.time())}.log")
                        options.add_argument(f"--log-file={log_path}")
                        options.add_argument("--enable-logging")
                        options.add_argument("--v=1")
                    except Exception as e:
                        logger.warning(f"Не удалось настроить логирование Chrome: {e}")
                    
                    # 5. Увеличиваем время ожидания на подключение
                    try:
                        from selenium.webdriver.remote.remote_connection import RemoteConnection
                        # Check if set_timeout exists as a class method
                        if hasattr(RemoteConnection, 'set_timeout') and callable(getattr(RemoteConnection, 'set_timeout')):
                            RemoteConnection.set_timeout(60)
                        # For newer Selenium versions
                        elif hasattr(RemoteConnection, 'get_connection_manager'):
                            conn_mgr = RemoteConnection.get_connection_manager()
                            if conn_mgr and hasattr(conn_mgr, 'set_timeout'):
                                conn_mgr.set_timeout(60)
                        logger.debug("Установлен таймаут соединения 60 секунд")
                    except Exception as e:
                        logger.warning(f"Не удалось установить таймаут соединения: {e}")
                    
                    # Дополнительные оптимизации для GitHub Codespace или для систем с ограниченными ресурсами
                    if is_codespace or is_low_resources:
                        # Принудительно включаем оптимизации для низких ресурсов
                        logger.info("Применяются дополнительные оптимизации для среды с ограниченными ресурсами")
                        options.add_argument('--disable-extensions')
                        options.add_argument('--mute-audio')
                        options.add_argument('--window-size=1280,720')
                        options.add_argument('--disable-features=VizDisplayCompositor')
                        options.add_argument('--blink-settings=imagesEnabled=false')
                        
                        # Ограничение потребления памяти
                        options.add_argument('--js-flags="--max-old-space-size=128"')
                    
                    # Добавляем настройки для повышения стабильности сетевых соединений
                    options.add_argument('--dns-prefetch-disable')
                    
                    # 6. Устанавливаем переменные окружения для Chrome
                    os.environ["DISPLAY"] = os.environ.get("DISPLAY", ":0")
                    
                    # Создаем сервис с указанием драйвера
                    service = Service(executable_path=self.driver_path)
                    
                    # Запускаем драйвер с настроенными опциями
                    driver = webdriver.Chrome(service=service, options=options)
                    driver.set_page_load_timeout(60)  # увеличиваем таймаут загрузки страницы
                    driver.implicitly_wait(implicit_wait)  # время ожидания элементов
                    
                    # Устанавливаем маленький размер окна для экономии ресурсов
                    if self.optimize_for_low_resources and not headless:
                        driver.set_window_size(800, 600)
                    
                    # Отслеживаем созданный драйвер для последующей очистки
                    self.active_drivers.append(driver)
                    
                    # Сохраняем директорию для дальнейшей очистки
                    if user_data_dir:
                        setattr(driver, "_user_data_dir", user_data_dir)
                    
                    # Инжектируем JavaScript для маскировки автоматизации
                    self._hide_automation_flags(driver)
                    
                    logger.info(f"Создан новый экземпляр Chrome Driver (всего активных: {len(self.active_drivers)})")
                    return driver
                
                except (WebDriverException, SessionNotCreatedException) as e:
                    retry_count += 1
                    last_exception = e
                    error_message = str(e).lower()
                    
                    # Очищаем временную директорию после неудачи
                    if user_data_dir and os.path.exists(user_data_dir):
                        try:
                            shutil.rmtree(user_data_dir)
                            logger.debug(f"Удалена временная директория: {user_data_dir}")
                        except Exception as cleanup_error:
                            logger.warning(f"Не удалось удалить временную директорию: {cleanup_error}")
                    
                    # Логируем ошибку подробно
                    logger.error(f"Ошибка при создании драйвера (попытка {retry_count}/{max_retries}): {e}")
                    
                    # Обработка различных типов ошибок
                    if "browser version" in error_message:
                        logger.error(f"Несоответствие версий Chrome и ChromeDriver: {e}")
                        # Пробуем автоматически установить подходящий драйвер
                        try:
                            self.install_chromedriver()
                        except Exception as install_error:
                            logger.error(f"Ошибка при автоматической установке ChromeDriver: {install_error}")
                    
                    elif "executable needs to be in path" in error_message:
                        logger.error(f"Chrome Driver не найден на указанном пути: {self.driver_path}")
                        try:
                            # Пробуем автоматически установить драйвер
                            self.install_chromedriver()
                        except Exception as install_error:
                            logger.error(f"Ошибка при автоматической установке ChromeDriver: {install_error}")
                    
                    elif "chrome failed to start" in error_message or "devtoolsactiveport file doesn't exist" in error_message:
                        logger.error(f"Chrome не удалось запустить: {e}")
                        # Пробуем очистить процессы Chrome перед следующей попыткой
                        self.kill_chrome_processes()
                        # Проверяем переменную DISPLAY
                        logger.info(f"Переменная DISPLAY={os.environ.get('DISPLAY', 'не установлена')}")
                        # Проверяем доступ к /tmp
                        try:
                            test_tmp = os.path.join('/tmp', f'test_chrome_{time.time()}')
                            with open(test_tmp, 'w') as f:
                                f.write('test')
                            os.remove(test_tmp)
                            logger.info("Проверка доступа к /tmp: ОК")
                        except Exception as tmp_error:
                            logger.error(f"Проблема с доступом к /tmp: {tmp_error}")
                        # Увеличиваем паузу перед следующей попыткой
                        time.sleep(2 * (retry_count + 1))
                    
                    elif "retrieval incomplete" in error_message or "network error" in error_message:
                        logger.error(f"Сетевая ошибка при создании драйвера: {e}")
                        # Пауза перед следующей попыткой
                        pause_time = 5 * (retry_count + 1)  # 5, 10, 15 секунд
                        logger.info(f"Ожидание {pause_time} секунд перед следующей попыткой")
                        time.sleep(pause_time)
                    
                    else:
                        logger.error(f"Неизвестная ошибка при создании драйвера: {e}")
                        # Небольшая пауза перед повторной попыткой
                        time.sleep(2)
                        
                    # Очищаем ресурсы перед повторной попыткой
                    self.cleanup_unused_drivers()
                    
                    # Если достигли максимального числа попыток, пробуем использовать undetected_chromedriver
                    if retry_count >= max_retries:
                        logger.warning(f"Не удалось создать Chrome Driver после {max_retries} попыток.")
                        logger.info("Пробую создать undetected_chromedriver как запасной вариант")
                        try:
                            return self.create_undetected_driver(headless=headless, incognito=incognito)
                        except Exception as uc_error:
                            logger.error(f"Не удалось создать даже undetected_chromedriver: {uc_error}")
                            # Если и это не сработало, выбрасываем исходное исключение
                            if "browser version" in error_message:
                                raise BrowserVersionMismatchException(f"Невозможно создать драйвер: {last_exception}. Установите подходящую версию ChromeDriver.")
                            elif "executable needs to be in path" in error_message:
                                raise BrowserNotFoundException(f"Chrome Driver не найден. Установите Chrome Driver вручную или используйте скрипт install_chromedriver.sh")
                            elif "chrome failed to start" in error_message:
                                raise BrowserNotFoundException(f"Chrome не удалось запустить. Проверьте, что Chrome установлен в системе.")
                            else:
                                raise last_exception
                
                except Exception as e:
                    logger.error(f"Неожиданная ошибка при создании драйвера Chrome: {e}")
                    # В случае ошибки пробуем удалить все активные драйверы
                    self.cleanup_all_drivers()
                    
                    # Очищаем временную директорию
                    if user_data_dir and os.path.exists(user_data_dir):
                        try:
                            shutil.rmtree(user_data_dir)
                        except Exception:
                            pass
                            
                    raise

    def _hide_automation_flags(self, driver):
        """
        Скрывает флаги автоматизации в браузере для избежания блокировок
        
        Args:
            driver: Экземпляр драйвера для обработки
        """
        try:
            driver.execute_script("""
                // Скрываем флаги автоматизации
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Скрываем свойства Selenium и ChromeDriver
                if (window.navigator.plugins) {
                    Object.defineProperty(navigator, 'plugins', {
                        get: function() { return [1, 2, 3, 4, 5]; }
                    });
                }
                
                // Подделываем технические отпечатки
                if (window.navigator.languages) {
                    Object.defineProperty(navigator, 'languages', {
                        get: function() { return ['ru-RU', 'ru', 'en-US', 'en']; }
                    });
                }
                
                // Удаляем флаги CDPSession
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
            """)
        except Exception as e:
            logger.debug(f"Ошибка при скрытии флагов автоматизации: {e}")

    def close_driver(self, driver):
        """
        Безопасно закрывает драйвер и освобождает ресурсы
        
        Args:
            driver: Экземпляр драйвера для закрытия
        """
        if driver is None:
            return
            
        # Очищаем временную директорию, если она была создана
        user_data_dir = getattr(driver, "_user_data_dir", None)
            
        try:
            # Пытаемся корректно закрыть драйвер
            driver.quit()
            logger.debug("Драйвер успешно закрыт")
        except Exception as e:
            logger.warning(f"Ошибка при закрытии драйвера: {e}")
            
        # Удаляем драйвер из списка активных
        if driver in self.active_drivers:
            self.active_drivers.remove(driver)
            
        # Удаляем временную директорию после закрытия драйвера
        if user_data_dir and os.path.exists(user_data_dir):
            try:
                shutil.rmtree(user_data_dir)
                logger.debug(f"Удалена временная директория: {user_data_dir}")
            except Exception as e:
                logger.warning(f"Не удалось удалить временную директорию {user_data_dir}: {e}")

    def cleanup_unused_drivers(self):
        """
        Закрывает неиспользуемые или зависшие драйверы
        
        Returns:
            int: Количество очищенных драйверов
        """
        with self.driver_lock:
            initial_count = len(self.active_drivers)
            
            if initial_count == 0:
                return 0
                
            # Создаем копию списка для безопасной итерации
            drivers_to_check = self.active_drivers.copy()
            
            for driver in drivers_to_check:
                try:
                    # Проверяем, отвечает ли драйвер
                    driver.current_url  # простой доступ к свойству для проверки
                except Exception:
                    # Драйвер не отвечает или уже закрыт
                    self.close_driver(driver)
                    
            cleaned_count = initial_count - len(self.active_drivers)
            
            if cleaned_count > 0:
                logger.info(f"Очищено неиспользуемых драйверов: {cleaned_count}")
                
            return cleaned_count

    def cleanup_all_drivers(self):
        """
        Закрывает все активные драйверы
        
        Returns:
            int: Количество закрытых драйверов
        """
        with self.driver_lock:
            count = len(self.active_drivers)
            
            if count == 0:
                return 0
                
            logger.info(f"Закрытие всех активных драйверов ({count})")
            
            # Создаем копию списка для безопасной итерации
            drivers_to_close = self.active_drivers.copy()
            
            for driver in drivers_to_close:
                self.close_driver(driver)
                
            # Дополнительная очистка процессов Chrome, если остались
            self.kill_chrome_processes()
            
            # Очистка памяти
            self.resource_mgr.force_garbage_collection()
            
            return count

    def kill_chrome_processes(self):
        """
        Принудительно завершает процессы Chrome и ChromeDriver
        
        Returns:
            int: Общее количество завершенных процессов
        """
        logger.info("Принудительное завершение процессов Chrome и ChromeDriver")
        count = 0
        
        # Завершаем процессы ChromeDriver
        driver_count = self.resource_mgr.kill_process_by_name('chromedriver')
        count += driver_count
        
        # Завершаем процессы Chrome
        chrome_count = self.resource_mgr.kill_process_by_name('chrome')
        count += chrome_count
        
        if count > 0:
            logger.info(f"Завершено процессов: ChromeDriver={driver_count}, Chrome={chrome_count}")
            
        return count

    def create_driver_with_fallback(self, headless=None, incognito=True, implicit_wait=10):
        """
        Создает обычный ChromeDriver сначала, с запасным вариантом undetected_chromedriver при необходимости
        
        Args:
            headless: Запускать ли браузер в безголовом режиме
            incognito: Запускать ли в режиме инкогнито
            implicit_wait: Время ожидания элементов по умолчанию
            
        Returns:
            tuple: (driver, is_undetected) - экземпляр драйвера и флаг использования undetected_chromedriver
        """
        # Проверяем сетевое подключение перед попыткой создания драйвера
        network_ok = self.check_network_connectivity()
        if not network_ok:
            logger.warning("Сетевое подключение отсутствует или нестабильно, это может вызвать проблемы при создании драйвера")
        
        # Очищаем неиспользуемые драйверы для избежания конфликтов
        self.cleanup_unused_drivers()
        
        try:
            # Сначала пробуем обычный ChromeDriver - он быстрее и надежнее
            logger.info("Создаю обычный ChromeDriver")
            driver = self.create_driver(headless=headless, incognito=incognito, implicit_wait=implicit_wait)
            return driver, False  # False означает, что не используется undetected_chromedriver
        except Exception as e:
            logger.warning(f"Не удалось создать обычный ChromeDriver: {e}")
            
            # Определяем, нужно ли пробовать undetected_chromedriver (например, обнаружение анти-бот защиты)
            error_str = str(e).lower()
            should_try_undetected = any(text in error_str for text in [
                "automation", "bot", "captcha", "challenge", "cloudflare", 
                "security", "blocked", "detected", "unusual activity"
            ])
            
            if should_try_undetected:
                try:
                    logger.info("Попытка создать undetected_chromedriver в качестве запасного варианта")
                    driver = self.create_undetected_driver(headless=headless, incognito=incognito)
                    return driver, True  # True означает использование undetected_chromedriver
                except Exception as uc_e:
                    logger.error(f"Также не удалось создать undetected_chromedriver: {uc_e}")
                    # Очищаем ресурсы перед повторной попыткой выбросить исключение
                    self.cleanup_all_drivers()
                    raise uc_e
            else:
                # Если ошибка не связана с обнаружением автоматизации, просто выбрасываем её
                # Очищаем ресурсы перед выбросом исключения
                self.cleanup_all_drivers()
                raise e

    def set_headless_mode(self, headless=True):
        """
        Устанавливает режим отображения окон браузера
        
        Args:
            headless: True для скрытия окон браузера, False для отображения
        """
        self.headless_mode = headless
        logger.info(f"Browser headless mode set to: {headless}")

    def check_network_connectivity(self, url="https://www.google.com", timeout=5):
        """
        Проверяет доступность сети перед попыткой создания драйвера
        
        Args:
            url: URL для проверки соединения
            timeout: Таймаут в секундах
            
        Returns:
            bool: True если соединение работает, False в противном случае
        """
        import socket
        import urllib.request
        
        try:
            # Сначала пробуем быстрое разрешение DNS
            socket.gethostbyname("www.google.com")
            
            # Затем пробуем быстрый HTTP запрос
            urllib.request.urlopen(url, timeout=timeout)
            logger.debug("Сетевое подключение работает нормально")
            return True
        except Exception as e:
            logger.warning(f"Проверка сетевого подключения не удалась: {e}")
            return False

    def create_undetected_driver(self, headless=None, incognito=True):
        """
        Создает новый экземпляр WebDriver используя undetected_chromedriver для обхода обнаружения автоматизации
        
        Args:
            headless: Запускать ли браузер в безголовом режиме
            incognito: Запускать ли в режиме инкогнито
            
        Returns:
            uc_webdriver.Chrome: Экземпляр undetected_chromedriver Chrome
        """
        with self.driver_lock:  # блокировка для синхронизации
            # Убедимся, что undetected_chromedriver установлен
            try:
                import undetected_chromedriver as uc_webdriver
            except ImportError:
                logger.error("Установка undetected_chromedriver...")
                try:
                    import pip
                    pip.main(['install', 'undetected-chromedriver'])
                    import undetected_chromedriver as uc_webdriver
                except Exception as e:
                    logger.error(f"Не удалось установить undetected_chromedriver: {e}")
                    # Возвращаемся к обычному драйверу Chrome при ошибке установки
                    logger.warning("Использую обычный ChromeDriver вместо undetected_chromedriver")
                    return self.create_driver(headless=headless, incognito=incognito)
            
            try:
                # Проверяем нагрузку на систему перед созданием нового драйвера
                if self.resource_mgr.memory_usage_critical():
                    # При критическом использовании памяти сначала очищаем ресурсы
                    logger.warning("Критическое использование памяти перед созданием драйвера. Запуск очистки.")
                    self.cleanup_unused_drivers()
                    self.resource_mgr.force_garbage_collection()
                
                # Настройка параметров драйвера
                options = uc_webdriver.ChromeOptions()
                
                # Применяем настройки headless и incognito
                if headless is None:
                    headless = self.headless_mode
                
                if headless:
                    options.add_argument('--headless')
                
                if incognito:
                    options.add_argument('--incognito')
                
                # Создаем временную директорию для профиля
                user_data_dir = None
                try:
                    user_data_dir = tempfile.mkdtemp(prefix="uc_chrome_user_data_")
                    logger.debug(f"Создана временная директория для undetected_chromedriver: {user_data_dir}")
                    options.add_argument(f"--user-data-dir={user_data_dir}")
                except Exception as e:
                    logger.warning(f"Не удалось создать временную директорию для undetected_chromedriver: {e}")
                
                # Дополнительные настройки для оптимизации
                options.add_argument('--start-maximized')
                options.add_argument('--disable-extensions')
                options.add_argument('--disable-gpu')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--no-sandbox')
                
                # Используем случайный порт для отладки
                random_port = random.randint(9222, 19222)
                options.add_argument(f"--remote-debugging-port={random_port}")
                
                # Увеличенные таймауты для сетевых операций
                options.add_argument('--dns-prefetch-disable')
                
                # Добавляем настройки для стабильности соединения
                options.add_argument('--disable-features=NetworkService')
                options.add_argument('--disable-features=VizDisplayCompositor')
                
                # Устанавливаем переменную DISPLAY
                os.environ["DISPLAY"] = os.environ.get("DISPLAY", ":0")
                
                # Устанавливаем путь к бинарному файлу Chrome
                chrome_binary = os.environ.get('CHROME_PATH')
                if chrome_binary and os.path.exists(chrome_binary):
                    options.binary_location = chrome_binary
                
                max_retries = 3
                retry_count = 0
                last_error = None
                
                while retry_count < max_retries:
                    try:
                        # Создаем драйвер с обработкой временных сетевых ошибок
                        driver = uc_webdriver.Chrome(
                            options=options,
                            use_subprocess=True,
                            version_main=123
                        )
                        
                        # Сохраняем директорию для дальнейшей очистки
                        if user_data_dir:
                            setattr(driver, "_user_data_dir", user_data_dir)
                        
                        # Отслеживаем созданный драйвер для последующей очистки
                        self.active_drivers.append(driver)
                        
                        logger.info(f"Создан новый экземпляр undetected Chrome Driver (всего активных: {len(self.active_drivers)})")
                        return driver
                    except Exception as e:
                        retry_count += 1
                        last_error = e
                        logger.warning(f"Ошибка при создании undetected Chrome Driver (попытка {retry_count}/{max_retries}): {e}")
                        
                        # Очищаем временную директорию после неудачи
                        if user_data_dir and os.path.exists(user_data_dir):
                            try:
                                shutil.rmtree(user_data_dir)
                                logger.debug(f"Удалена временная директория: {user_data_dir}")
                            except Exception as cleanup_error:
                                logger.warning(f"Не удалось удалить временную директорию: {cleanup_error}")
                        
                        # Очистка перед повторной попыткой
                        self.kill_chrome_processes()
                        time.sleep(2)  # Пауза перед повторной попыткой
                        
                        # Если последняя попытка не удалась, пробуем обычный ChromeDriver
                        if retry_count >= max_retries:
                            logger.warning(f"Не удалось создать undetected Chrome Driver после {max_retries} попыток. Использую обычный ChromeDriver.")
                            return self.create_driver(headless=headless, incognito=incognito)
                
                raise last_error  # Этот код не должен выполниться из-за возврата выше
                
            except Exception as e:
                logger.error(f"Ошибка при создании undetected Chrome Driver: {e}")
                # Пробуем создать обычный ChromeDriver как запасной вариант
                logger.warning("Пробую создать обычный ChromeDriver как запасной вариант")
                try:
                    return self.create_driver(headless=headless, incognito=incognito)
                except Exception as e2:
                    logger.error(f"Также не удалось создать обычный ChromeDriver: {e2}")
                    raise e


def get_browser_service():
    """
    Возвращает глобальный экземпляр сервиса браузера (синглтон)
    """
    global _browser_service_instance
    
    if _browser_service_instance is None:
        with _instance_lock:  # блокировка для потокобезопасности
            if _browser_service_instance is None:  # двойная проверка для избежания состояния гонки
                _browser_service_instance = BrowserService()
                
    return _browser_service_instance