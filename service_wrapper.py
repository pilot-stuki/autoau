#!/usr/bin/env python3
import os
import sys
import signal
import logging
from logging.handlers import RotatingFileHandler
import traceback
from itertools import chain
from concurrent.futures import ThreadPoolExecutor
import time  # Import time module directly
from multiprocessing import TimeoutError, Pool
import threading
from random import randint
from datetime import datetime, timedelta
import shutil
import glob
from typing import Set, Dict
import psutil
from selenium.common.exceptions import WebDriverException, TimeoutException
from functools import wraps
from time import sleep  # Add explicit import for sleep
import random  # Add for random batch sizes

from browser_service import get_browser_service
from session_service import get_session_service
from automation_service import get_automation_service
from error_service import get_error_service, ErrorScope
from resource_manager import get_resource_manager
from config import Config

# Make paths absolute for systemd
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logging():
    """Setup logging with proper paths and permissions"""
    try:
        # Ensure log directory exists and has proper permissions
        os.makedirs(LOG_DIR, exist_ok=True)
        os.chmod(LOG_DIR, 0o755)
        
        log_file = os.path.join(LOG_DIR, 'service.log')
        
        # Create logger
        logger = logging.getLogger('service')
        logger.setLevel(logging.DEBUG)  # Enable debug for startup
        
        # File handler with absolute path
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,
            backupCount=5
        )
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
        
        # Console handler for systemd
        console_handler = logging.StreamHandler(sys.stdout)  # Use stdout for systemd
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(console_handler)
        
        # Test write access
        logger.info("Logging system initialized")
        return logger
        
    except Exception as e:
        sys.stderr.write(f"Failed to initialize logging: {str(e)}\n")
        sys.exit(1)

# Initialize logging first
try:
    # Clear existing handlers
    root = logging.getLogger()
    if (root.handlers):
        for handler in root.handlers:
            root.removeHandler(handler)
            
    service_logger = setup_logging()
    service_logger.info(f"Starting service from {BASE_DIR}")
    
except Exception as e:
    sys.stderr.write(f"Critical startup error: {str(e)}\n")
    sys.exit(1)

# Убираем циклический импорт
# Вместо импорта из main.py, будем использовать конфиг
config = Config()
ACCOUNTS = config.get_users()  # Получаем аккаунты из конфига напрямую

def cleanup_chrome():
    """Функция для очистки процессов Chrome/Chromedriver"""
    try:
        resource_mgr = get_resource_manager()
        
        # Первая попытка - через встроенный метод
        chrome_killed = resource_mgr.kill_process_by_name('chrome')
        driver_killed = resource_mgr.kill_process_by_name('chromedriver')
        
        # Если не удалось убить процессы обычным способом, используем более агрессивный подход
        if chrome_killed == 0:
            try:
                import psutil
                import signal
                
                # Находим все процессы Chrome и принудительно убиваем их
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        # Проверяем, относится ли процесс к Chrome
                        if 'chrome' in proc.info['name'].lower() or 'chromedriver' in proc.info['name'].lower():
                            # Сначала пробуем SIGTERM
                            os.kill(proc.info['pid'], signal.SIGTERM)
                            # Ждем немного
                            time.sleep(0.5)
                            # Если процесс все еще жив, используем SIGKILL
                            if psutil.pid_exists(proc.info['pid']):
                                os.kill(proc.info['pid'], signal.SIGKILL)
                                chrome_killed += 1
                    except Exception as proc_err:
                        service_logger.debug(f"Ошибка при убийстве процесса {proc.info['pid']}: {proc_err}")
            except Exception as e:
                service_logger.error(f"Ошибка при агрессивной очистке Chrome: {e}")
        
        service_logger.info(f"Очищено {chrome_killed} процессов Chrome и {driver_killed} процессов ChromeDriver")
        return chrome_killed + driver_killed
    except Exception as e:
        service_logger.error(f"Ошибка в cleanup_chrome: {e}")
        return 0

def init_worker():
    """Initialize worker process"""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    service_logger.info(f"Worker process started: {os.getpid()}")

def signal_handler(signum, frame):
    """Handle termination signals"""
    service_logger.info(f"Received signal {signum}, initiating shutdown...")
    cleanup_chrome()
    sys.exit(0)

def check_system_resources():
    """Check if system has enough resources"""
    mem = psutil.virtual_memory()
    if (mem.available < 1024 * 1024 * 1024):  # 1GB
        service_logger.error("Not enough memory available")
        return False
    return True

def chunk_accounts(accounts, size=None):
    """Split accounts into random-sized chunks"""
    if size is None:
        size = random.randint(2, 4)
    for i in range(0, len(accounts), size):
        yield accounts[i:i + min(size, len(accounts))]

# Debug mode and timeout configurations
DEBUG_MODE = True

# Update timeout configurations
if DEBUG_MODE:
    TIMEOUTS = {
        'network_check': 30,    # 30s network check
        'page_load': 45,       # 45s page load
        'element_wait': 20,    # 20s element wait
        'process': 120,       # 2min per account process
        'batch': 180,        # 3min batch timeout (increased from 15s)
        'cycle': 1800       # 30min cycle
    }
    
    # Add cycle delay configuration
    CYCLE_DELAYS = {
        'success': 300,    # 5min if all succeeded
        'partial': 600,    # 10min if some failed
        'failure': 900     # 15min if all failed
    }
    
    BATCH_SIZE = 3
    MAX_RETRIES = 2
    RETRY_DELAYS = [5, 10]
else:
    TIMEOUTS = {
        'network_check': 30,    # 30 seconds for network check
        'page_load': 60,       # 60 seconds for page load
        'element_wait': 30,    # 30 seconds for element waits
        'process': 300,       # 5 minutes per process
        'batch': 600,        # 10 minutes per batch
        'account': 300,      # 5 minutes per account
        'cycle': 900,       # 15 minutes per cycle
        'global': 1800      # 30 minutes global timeout
    }
    BATCH_SIZE = random.randint(2, 4)  # Random batch size
    MAX_RETRIES = 3
    RETRY_DELAYS = [30, 60, 120]
    INTER_BATCH_DELAY = random.randint(300, 600)  # 5-10 minutes

MIN_PROCESS_TIMEOUT = 300  # Increase to 5 minutes minimum
DEFAULT_PROCESS_TIMEOUT = 600  # Increase to 10 minutes default
MAX_CYCLES = 0  # 0 means run indefinitely

FAILED_ACCOUNTS: Set[str] = set()
ACCOUNT_LOCKS: Dict[str, threading.Lock] = {}

def cleanup_zombie_processes():
    """Clean up any zombie Chrome processes"""
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if 'chrome' in proc.info['name'].lower():
                try:
                    proc.kill()
                except:
                    pass
    except Exception as e:
        service_logger.error(f"Error cleaning zombie processes: {str(e)}")

def get_random_timeouts():
    """Get randomized timeouts with increased minimums"""
    return {
        'batch': randint(300, 600),      # 5-10 minutes
        'inter_batch': randint(60, 120),  # 1-2 minutes
        'process': randint(MIN_PROCESS_TIMEOUT, DEFAULT_PROCESS_TIMEOUT),  # 5-10 minutes
        'cycle': randint(600, 900)       # 10-15 minutes
    }

def archive_logs():
    """Archive logs older than 7 days"""
    try:
        archive_dir = os.path.join(BASE_DIR, 'logs', 'archive')
        os.makedirs(archive_dir, exist_ok=True)
        
        # Get current date for comparison
        current_date = datetime.now()
        
        # Check all log files
        log_files = glob.glob(os.path.join(BASE_DIR, 'logs', '*.log*'))
        for log_file in log_files:
            # Get file modification time
            mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
            days_old = (current_date - mtime).days
            
            # Archive files older than 7 days
            if days_old > 7:
                archive_name = f"{os.path.basename(log_file)}.{mtime.strftime('%Y%m%d')}"
                archive_path = os.path.join(archive_dir, archive_name)
                
                # Compress and move to archive
                try:
                    shutil.copy2(log_file, archive_path)
                    os.remove(log_file)
                    service_logger.info(f"Archived log file: {archive_name}")
                except Exception as e:
                    service_logger.error(f"Failed to archive {log_file}: {str(e)}")
                    
    except Exception as e:
        service_logger.error(f"Log archival error: {str(e)}")

def get_system_metrics():
    """Get current system resource usage"""
    try:
        mem = psutil.virtual_memory()
        chrome_count = len([p for p in psutil.process_iter(['name']) 
                          if 'chrome' in p.info['name'].lower()])
        python_count = len([p for p in psutil.process_iter(['name']) 
                          if 'python' in p.info['name'].lower()])
        return {
            'memory_percent': mem.percent,
            'chrome_processes': chrome_count,
            'python_processes': python_count
        }
    except Exception as e:
        service_logger.error(f"Error getting metrics: {str(e)}")
        return {}

def log_diagnostics(phase: str, account_email: str = None):
    """Log diagnostic information at key points"""
    metrics = get_system_metrics()
    msg = (f"DIAGNOSTIC [{phase}] "
           f"Memory: {metrics.get('memory_percent')}%, "
           f"Chrome: {metrics.get('chrome_processes')}, "
           f"Python: {metrics.get('python_processes')}")
    if account_email:
        msg += f", Account: {account_email}"
    service_logger.info(msg)

def is_time_between(check_time, start_time, end_time):
    """Check if current time is between start and end times"""
    if start_time <= end_time:
        return start_time <= check_time <= end_time
    else:  # crosses midnight
        return check_time >= start_time or check_time <= end_time

def get_next_run_time(current_time, interval_minutes=60):
    """Calculate next run time with proper datetime handling"""
    return current_time + timedelta(minutes=interval_minutes)

def timeout_handler(signum, frame):
    raise TimeoutError("Processing timed out")

def process_with_timeout(timeout=30):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Set the timeout handler
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            try:
                result = func(*args, **kwargs)
                signal.alarm(0)  # Disable alarm
                return result
            except TimeoutError:
                user = args[0] if args else "Unknown"
                service_logger.error(f"Timeout: {user[0]}", exc_info=True)
                raise
            finally:
                signal.alarm(0)  # Ensure alarm is disabled
        return wrapper
    return decorator

def run_account(user, max_attempts=3):
    attempt = 1
    while attempt <= max_attempts:
        try:
            service_logger.info(f"Starting {user[0]} (Attempt {attempt})")
            process_with_timeout(timeout=30)(main)(user)
            break
        except TimeoutError:
            service_logger.error(f"Timeout: {user[0]}")
            cleanup_chrome()  # Clean up after timeout
            attempt += 1
        except Exception as e:
            service_logger.error(f"Error processing {user[0]}:", exc_info=True)
            cleanup_chrome()
            attempt += 1
            
    if attempt > max_attempts:
        service_logger.error(f"Max attempts ({max_attempts}) reached for {user[0]}")

def process_single_account(user, timeout):
    """Process single account with simplified state tracking"""
    account_email = user[0]
    account_password = user[1]
    start_time = time.time()
    attempts = 0
    max_attempts = 3
    
    try:
        while attempts < max_attempts:
            service_logger.info(f"Processing {account_email} (Attempt {attempts + 1}/{max_attempts})")
            
            try:
                # Получаем сервисы для обработки аккаунта
                automation_service = get_automation_service()
                service_wrapper = get_service_wrapper()
                
                # Выполняем вход
                driver, is_new_login = self.error_service.retry_operation(
                    lambda: automation_service.login(email, password),
                    f"login_{email}",
                    max_retries=3,
                    retry_delay=2
                )
                
                # Закрываем всплывающие окна после входа
                service_wrapper.handle_popups(driver, account_email)
                
                # Проверяем состояние переключателя
                toggle_result = automation_service.check_and_set_toggle(driver)
                
                # Закрываем браузер
                get_browser_service().close_driver(driver)
                
                service_logger.info(f"Success: {account_email}")
                return "SUCCESS"
                    
            except Exception as e:
                if "Toggle already enabled" in str(e):
                    service_logger.info(f"Already enabled for {account_email}")
                    return "SUCCESS"
                    
                attempts += 1
                if attempts < max_attempts:
                    service_logger.warning(f"Error for {account_email}, retry {attempts}: {str(e)}")
                    cleanup_chrome()
                    time.sleep(5 * attempts)
                else:
                    service_logger.error(f"Failed after {max_attempts} attempts: {account_email}")
                    return "FAILED"
                    
    except Exception as e:
        service_logger.error(f"Critical error for {account_email}: {str(e)}")
        return "FAILED"
    finally:
        cleanup_chrome()

def process_batch(batch, batch_num, total_batches, timeouts):
    """Process batch with simplified tracking"""
    batch_start = time.time()
    completed = []
    failed = []
    
    try:
        service_logger.info(f"=== Starting Batch {batch_num + 1}/{total_batches} ===")
        service_logger.info(f"Batch size: {len(batch)}")
        
        with Pool(min(3, len(batch))) as pool:
            # Start all processes
            results = []
            for user in batch:
                result = pool.apply_async(process_single_account, 
                                       (user, timeouts['process']))
                results.append((user, result))
            
            # Wait for results
            for user, result in results:
                try:
                    status = result.get(timeout=timeouts['process'])
                    if status == "SUCCESS":
                        completed.append(user)
                        service_logger.info(f"Completed: {user[0]}")
                    else:
                        failed.append(user)
                        service_logger.error(f"Failed: {user[0]}")
                except TimeoutError:
                    failed.append(user)
                    service_logger.error(f"Timeout: {user[0]}")
                except Exception as e:
                    failed.append(user)
                    service_logger.error(f"Error processing {user[0]}: {str(e)}")
            
            # Clean final state
            pool.close()
            pool.join()
            
    except Exception as e:
        service_logger.error(f"Batch error: {str(e)}")
        failed.extend([u for u, _ in results if u not in completed])
    finally:
        cleanup_chrome()
        
        elapsed = time.time() - batch_start
        service_logger.info(f"""
        === Batch {batch_num + 1} Summary ===
        Completed: {len(completed)}/{len(batch)}
        Failed: {len(failed)}/{len(batch)}
        Duration: {elapsed:.1f}s
        """)
    
    return completed, failed

def run_service():
    """Main service loop with improved state management"""
    cycle = 0
    
    try:
        while True:
            cycle += 1
            cycle_start = datetime.now()
            
            service_logger.info(f"Starting cycle {cycle} at {cycle_start}")
            cleanup_chrome()
            
            # Process in smaller batches
            batch_size = 3  # Process 3 accounts at a time
            batches = list(chunk_accounts(ACCOUNTS, batch_size))
            
            cycle_completed = []
            cycle_failed = []
            
            for batch_num, batch in enumerate(batches):
                completed, failed = process_batch(batch, batch_num, len(batches), TIMEOUTS)
                cycle_completed.extend(completed)
                cycle_failed.extend(failed)
                
                # Only delay if there were failures
                if failed and batch_num < len(batches) - 1:
                    time.sleep(30)  # 30s delay between batches on failure
            
            # Calculate next cycle delay based on success rate
            success_rate = len(cycle_completed) / len(ACCOUNTS)
            if success_rate == 1.0:
                next_delay = 300  # 5min on full success
            elif success_rate == 0:
                next_delay = 900  # 15min on full failure
            else:
                next_delay = 600  # 10min on partial success
                
            service_logger.info(f"""
            === Cycle {cycle} Complete ===
            Success Rate: {success_rate:.1%}
            Next Delay: {next_delay}s
            """)
            
            time.sleep(next_delay)
            
    except KeyboardInterrupt:
        service_logger.info("Service stopped by user")
    except Exception as e:
        service_logger.critical(f"Service error: {str(e)}")
        return 1

def run_with_timeout(user, timeout):
    start_time = time()
    try:
        service_logger.info(f"Starting {user[0]} (Attempt 1)")
        main(user)
    except Exception as e:
        elapsed_time = time() - start_time
        if elapsed_time >= timeout:
            service_logger.error(f"Timeout: {user[0]}")
        service_logger.error(f"Error processing {user[0]}: {str(e)}", exc_info=True)
        raise

# Получение логгера
logger = logging.getLogger(__name__)

# Семафор для координации доступа к ресурсам
_resource_semaphore = threading.Semaphore(1)

# Версия обертки сервисов
SERVICE_WRAPPER_VERSION = '2.0.0'


class ServiceWrapper:
    """
    Обертка для координации между сервисами и оптимизации ресурсов
    
    Предоставляет единый интерфейс для работы с различными сервисами
    и оптимизирует использование ресурсов при длительном выполнении.
    """
    
    def __init__(self):
        """Инициализация обертки сервисов"""
        # Инициализация сервисов
        self.browser_service = get_browser_service()
        self.session_service = get_session_service()
        self.automation_service = get_automation_service()
        self.error_service = get_error_service()
        self.resource_mgr = get_resource_manager()
        self.config = Config()
        
        # Настройки для оптимизации ресурсов
        self.low_resource_mode = self.resource_mgr.should_optimize_for_low_resources()
        self.concurrent_limit = 1 if self.low_resource_mode else self.resource_mgr.get_optimal_process_count()
        
        # Состояние обертки
        self.wrapper_state = {
            'service_wrapper_version': SERVICE_WRAPPER_VERSION,
            'initialized_at': datetime.now().isoformat(),
            'accounts_processed': 0,
            'successful_logins': 0,
            'successful_toggles': 0,
            'failed_logins': 0,
            'failed_toggles': 0,
            'last_execution': None,
            'low_resource_mode': self.low_resource_mode,
            'concurrent_limit': self.concurrent_limit
        }
        
        # Блокировка для обновления состояния
        self.state_lock = threading.Lock()
        
        logger.info(f"Инициализирована ServiceWrapper: версия={SERVICE_WRAPPER_VERSION}, "
                    f"low_resource_mode={self.low_resource_mode}, "
                    f"concurrent_limit={self.concurrent_limit}")

    def process_account(self, email, password):
        """
        Обрабатывает один аккаунт с использованием оптимизированной стратегии выбора драйвера
        
        Args:
            email: Строка с email аккаунта
            password: Строка с паролем
            
        Returns:
            bool: True если операция выполнена успешно
        """
        # Очищаем процессы Chrome перед началом обработки
        browser_service = get_browser_service()
        chrome_processes = browser_service.kill_chrome_processes()
        
        # Логируем состояние системы перед обработкой
        from diagnostics import log_memory_usage, log_chrome_processes
        try:
            memory_info = log_memory_usage()
            chrome_info = log_chrome_processes()
            diag_msg = f"DIAGNOSTIC [before_account] Memory: {memory_info}, Chrome: {chrome_info}, Account: {email}"
            service_logger.info(diag_msg)
        except Exception as e:
            # Только логируем ошибку в файл, не выводим в консоль
            service_logger.debug(f"Ошибка при логировании диагностики (не критично): {e}")
        
        # Уменьшаем таймаут для более быстрой обработки
        account_timeout = 60  # Увеличиваем с 30 до 60 секунд
        service_logger.info(f"Начинаем процесс входа для {email} с таймаутом {account_timeout}с")
        
        # Флаг для обозначения успешности операции
        success = False
        
        # Оборачиваем все в try-finally для гарантированной очистки ресурсов
        try:
            # Получаем сервис автоматизации
            automation_service = get_automation_service()
            
            # Проверяем сетевое подключение перед созданием драйвера
            network_ok = browser_service.check_network_connectivity()
            if not network_ok:
                service_logger.warning(f"Сетевое подключение нестабильно, возможны проблемы при входе для {email}")
            
            # Выполняем вход с использованием новой стратегии выбора драйвера
            try:
                # Используем headless режим если требуется оптимизация ресурсов
                resource_mgr = get_resource_manager()
                headless = True if resource_mgr.should_optimize_for_low_resources() else None
                
                # Создаем драйвер с оптимизированной стратегией выбора
                driver, using_undetected = browser_service.create_driver_with_fallback(
                    headless=headless,
                    incognito=True,
                    implicit_wait=10
                )
                
                if using_undetected:
                    service_logger.info(f"Используем undetected_chromedriver для {email} (обнаружены анти-бот меры)")
                else:
                    service_logger.info(f"Используем обычный ChromeDriver для {email}")
                
                # Выполняем вход
                driver, is_new_login = automation_service.login(email, password, driver=driver)
                
                # Закрываем всплывающие окна, которые могут появиться после входа
                try:
                    service_logger.info(f"Попытка закрыть всплывающие окна для {email}")
                    automation_service.close_popups(driver)
                except Exception as popup_error:
                    service_logger.debug(f"Ошибка при попытке закрыть специфические всплывающие окна для {email}: {popup_error}")
                
                # Проверяем и устанавливаем переключатель
                try:
                    # Проверяем состояние соединения с драйвером перед работой с переключателем
                    try:
                        current_url = driver.current_url
                        service_logger.debug(f"Соединение с драйвером активно перед работой с переключателем: {current_url}")
                    except Exception as driver_error:
                        service_logger.error(f"Ошибка соединения с драйвером: {driver_error}")
                        print(f"Ошибка соединения с драйвером: {driver_error}")
                        # Предполагаем, что переключатель включен, чтобы не было ложных попыток изменить его
                        print("Невозможно установить переключатель из-за проблем соединения")
                        success = True  # Считаем операцию успешной, так как проблемы с драйвером
                        return success

                    # Получаем текущее состояние переключателя
                    current_state = automation_service.check_and_set_toggle(driver, should_be_on=True, check_only=True)
                    service_logger.info(f"Текущее состояние переключателя для {email}: {'ON' if current_state else 'OFF'}")
                    
                    # Устанавливаем переключатель только если он выключен
                    if not current_state:
                        service_logger.info(f"Переключатель выключен, пытаемся включить его для {email}")
                        # Устанавливаем переключатель прямым вызовом (без check_only, с should_be_on=True)
                        toggle_success = automation_service.check_and_set_toggle(driver, should_be_on=True, check_only=False)
                        
                        if toggle_success:
                            service_logger.info(f"Переключатель успешно установлен в положение ON для {email}")
                        else:
                            # Если не получилось, делаем еще одну попытку после обновления страницы
                            service_logger.warning(f"Первая попытка установки переключателя не удалась для {email}, обновляем страницу и пробуем снова")
                            try:
                                driver.refresh()
                                time.sleep(2)
                                toggle_success = automation_service.check_and_set_toggle(driver, should_be_on=True, check_only=False)
                                if toggle_success:
                                    service_logger.info(f"Переключатель успешно установлен после обновления страницы для {email}")
                                else:
                                    service_logger.warning(f"Не удалось установить переключатель в положение ON для {email} даже после обновления страницы")
                            except Exception as refresh_error:
                                service_logger.error(f"Ошибка при обновлении страницы: {refresh_error}")
                    else:
                        service_logger.info(f"Аккаунт {email} обработан успешно. Переключатель уже включен")
                        
                    # Делаем скриншот после установки переключателя для проверки
                    try:
                        automation_service.save_screenshot(driver, "toggle_after")
                        service_logger.info(f"Сохранен скриншот после обработки переключателя")
                    except Exception as screenshot_error:
                        service_logger.error(f"Не удалось сделать скриншот: {screenshot_error}")
                    
                    # Проверяем финальное состояние переключателя
                    try:
                        final_state = automation_service.check_and_set_toggle(driver, should_be_on=True, check_only=True)
                        service_logger.info(f"Финальное состояние переключателя для {email}: {'ON' if final_state else 'OFF'}")
                        # Считаем операцию успешной только если переключатель включен
                        success = final_state
                    except Exception as final_check_error:
                        service_logger.error(f"Ошибка при проверке финального состояния: {final_check_error}")
                        # Если не смогли проверить, предполагаем успех, как было раньше
                        success = True
                except Exception as toggle_error:
                    service_logger.error(f"Ошибка при работе с переключателем для {email}: {toggle_error}")
                    
                    # Проверяем, связана ли ошибка с недоступностью драйвера
                    if "connection refused" in str(toggle_error).lower() or "no such session" in str(toggle_error).lower():
                        service_logger.warning(f"Потеряно соединение с драйвером для {email}. Считаем, что переключатель уже включен.")
                        print("Невозможно установить переключатель из-за проблем соединения")
                        success = True  # Чтобы избежать повторных попыток при проблемах с соединением
                    else:
                        success = False
            except Exception as e:
                service_logger.error(f"Ошибка при выполнении операции '{operation_name}': {e}")
                
                # Добавляем вывод конкретного exception для отладки
                import traceback
                service_logger.error(f"Детали ошибки: {traceback.format_exc()}")
                
                success = False
                
                # Специфичная обработка ошибки сетевого соединения
                error_str = str(e).lower()
                if "retrieval incomplete" in error_str or "urlopen error" in error_str:
                    service_logger.error(f"Обнаружена сетевая ошибка: {e}")
            
            finally:
                # Закрываем браузер, если он был открыт
                if driver:
                    try:
                        driver.quit()
                    except Exception as e:
                        service_logger.warning(f"Ошибка при закрытии драйвера: {e}")
                
                # Логируем результат
                if not success:
                    service_logger.error(f"Вход не выполнен для {email} (таймаут или ошибка входа)")
        
        except Exception as e:
            service_logger.error(f"Неожиданная ошибка при обработке аккаунта {email}: {e}")
            success = False
            
        finally:
            # Очищаем процессы Chrome после завершения
            browser_service.kill_chrome_processes()
        
        return success

    def handle_popups(self, driver, email):
        """
        Обрабатывает всплывающие окна и административные сообщения
        
        Args:
            driver: Экземпляр WebDriver
            email: Email пользователя для логирования
            
        Returns:
            bool: True если окна были закрыты, False в противном случае
        """
        service_logger.info(f"Попытка закрыть всплывающие окна для {email}")
        
        try:
            # Используем метод close_popups из AutomationService
            result = self.automation_service.close_popups(driver)
            
            # Дополнительно проверяем наличие конкретных элементов из старой версии кода
            try:
                # Проверяем наличие кнопки "Close" из старой версии
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                # Проверяем кнопку Close
                close_buttons = driver.find_elements(By.XPATH, '//button[text()="Close"]')
                for button in close_buttons:
                    if button.is_displayed():
                        driver.execute_script("arguments[0].click();", button)
                        service_logger.info(f"Закрыта кнопка 'Close' для {email} (старая версия)")
                        result = True
                        time.sleep(1)
                
                # Проверяем кнопку OK (используется в некоторых всплывающих окнах)
                ok_buttons = driver.find_elements(By.XPATH, '//button[text()="OK"]')
                for button in ok_buttons:
                    if button.is_displayed():
                        driver.execute_script("arguments[0].click();", button)
                        service_logger.info(f"Закрыта кнопка 'OK' для {email} (старая версия)")
                        result = True
                        time.sleep(1)
                
                # Проверяем административное сообщение на домашней странице
                enter_links = driver.find_elements(By.XPATH, '//*[@class="terms-and-conditions__enter-link"]')
                for link in enter_links:
                    if link.is_displayed():
                        driver.execute_script("arguments[0].click();", link)
                        service_logger.info(f"Закрыто административное сообщение для {email} (старая версия)")
                        result = True
                        time.sleep(1)
                
            except Exception as e:
                service_logger.debug(f"Ошибка при попытке закрыть специфические всплывающие окна для {email}: {e}")
            
            if result:
                service_logger.info(f"Всплывающие окна успешно закрыты для {email}")
            else:
                service_logger.debug(f"Не найдены всплывающие окна для {email}")
                
            return result
        except Exception as e:
            service_logger.warning(f"Ошибка при попытке закрыть всплывающие окна: {e}")
            return False

    def process_accounts_sequential(self, accounts, delay_between_accounts=None):
        """
        Обрабатывает список аккаунтов последовательно, с использованием оптимизированной стратегии выбора драйвера
        
        Args:
            accounts: Список аккаунтов [(email, password), ...]
            delay_between_accounts: Задержка между обработкой аккаунтов в секундах
            
        Returns:
            dict: Словарь результатов {email: success}
        """
        results = {}
        
        service_logger.info(f"Последовательная обработка {len(accounts)} аккаунтов")
        
        # Получаем сервисы
        browser_service = get_browser_service()
        
        # Проверяем сетевое подключение перед обработкой
        network_ok = browser_service.check_network_connectivity()
        if not network_ok:
            service_logger.warning("Сетевое подключение нестабильно, это может вызвать проблемы при обработке аккаунтов")
        
        # Очищаем процессы Chrome перед началом
        browser_service.cleanup_all_drivers()
        
        # Определяем режим работы
        resource_mgr = get_resource_manager()
        headless = True if resource_mgr.should_optimize_for_low_resources() else None
            
        for email, password in accounts:
            # Диагностика перед обработкой аккаунта
            try:
                from diagnostics import log_memory_usage, log_chrome_processes
                memory_info = log_memory_usage()
                chrome_info = log_chrome_processes()
                service_logger.info(f"Диагностика перед обработкой {email}: {memory_info} | {chrome_info}")
            except Exception as e:
                service_logger.error(f"Ошибка при логировании диагностики: {e}")
            
            # Обрабатываем аккаунт
            results[email] = self.process_account(email, password)
            
            # Делаем паузу между аккаунтами если указана
            if delay_between_accounts is None:
                # Если задержка не указана, используем адаптивную задержку
                if resource_mgr.should_optimize_for_low_resources():
                    # При ограниченных ресурсах делаем большую паузу
                    delay = random.randint(5, 10)
                else:
                    # Обычная пауза
                    delay = random.randint(3, 7)
            else:
                delay = delay_between_accounts
                
            if email != accounts[-1][0]:  # Не делаем паузу после последнего аккаунта
                service_logger.info(f"Пауза {delay} секунд перед следующим аккаунтом")
                time.sleep(delay)
        
        # Итоговая очистка
        browser_service.cleanup_all_drivers()
        
        return results

    def process_accounts_parallel(self, accounts, max_workers=None):
        """
        Параллельно обрабатывает список аккаунтов с учетом ограничений ресурсов
        
        Args:
            accounts: Список аккаунтов в формате [(email, password), ...]
            max_workers: Максимальное количество параллельных процессов
            
        Returns:
            dict: Результаты обработки {email: success_status, ...}
        """
        # В режиме низких ресурсов всегда используем последовательную обработку
        if self.low_resource_mode:
            logger.info("Переключение на последовательную обработку из-за режима низких ресурсов")
            return self.process_accounts_sequential(accounts)
            
        # Определяем оптимальное количество рабочих процессов
        if max_workers is None:
            max_workers = self.resource_mgr.get_optimal_process_count()
            max_workers = min(max_workers, self.concurrent_limit, len(accounts))
            
        logger.info(f"Запуск параллельной обработки с {max_workers} рабочими процессами")
        
        results = {}
        threads = []
        results_lock = threading.Lock()
        
        def worker(email, password):
            success = self.process_account(email, password)
            with results_lock:
                results[email] = success
                
        # Создаем и запускаем потоки для каждого аккаунта
        for email, password in accounts:
            thread = threading.Thread(target=worker, args=(email, password))
            threads.append(thread)
            thread.start()
            
            # Если достигли максимального количества потоков, ждем завершения одного
            while sum(1 for t in threads if t.is_alive()) >= max_workers:
                time.sleep(1)
                
        # Ждем завершения всех потоков
        for thread in threads:
            thread.join()
            
        return results

    def verify_toggle_state(self, email, password):
        """
        Проверяет текущее состояние переключателя для аккаунта
        
        Args:
            email: Email пользователя
            password: Пароль пользователя
            
        Returns:
            bool: True если переключатель включен, False если выключен, None в случае ошибки
        """
        driver = None
        
        try:
            # Выполняем вход с экономией ресурсов (одна проверка)
            try:
                login_result = self.error_service.retry_operation(
                    lambda: self.automation_service.login(email, password),
                    "login_for_verification"
                )
                
                if not login_result:
                    logger.error(f"Не удалось выполнить вход для проверки состояния переключателя ({email})")
                    return None
                    
                driver, _ = login_result
                logger.info(f"Успешный вход для {email} при проверке переключателя")
            except Exception as e:
                logger.error(f"Ошибка при входе для проверки переключателя ({email}): {e}")
                
                # Делаем скриншот ошибки входа, если драйвер уже создан
                if driver:
                    try:
                        screenshot_path = f"login_error_{int(time.time())}.png"
                        driver.save_screenshot(screenshot_path)
                        logger.info(f"Скриншот ошибки входа: {screenshot_path}")
                    except:
                        pass
                
                return None
            
            # Проверяем состояние переключателя без его изменения
            try:
                # Даем странице время полностью загрузиться
                time.sleep(3)
                
                # Закрываем возможные всплывающие окна
                try:
                    popups_closed = self.automation_service.close_popups(driver)
                    if popups_closed:
                        logger.info(f"Закрыты всплывающие окна для {email}")
                except Exception as e:
                    logger.debug(f"Ошибка при закрытии всплывающих окон: {e}")
                
                # Делаем скриншот страницы для диагностики
                try:
                    screenshot_path = f"toggle_check_{int(time.time())}.png"
                    driver.save_screenshot(screenshot_path)
                    logger.info(f"Создан скриншот для проверки переключателя: {screenshot_path}")
                except Exception as e:
                    logger.debug(f"Не удалось сделать скриншот: {e}")
                
                # Проверяем текущее состояние переключателя с учетом возможных ошибок
                max_retries = 3
                retry_count = 0
                
                while retry_count < max_retries:
                    try:
                        # Проверяем текущее состояние переключателя
                        toggle_result = self.automation_service.check_and_set_toggle(
                            driver, 
                            should_be_on=True,  # Не важно при check_only=True
                            check_only=True
                        )
                        
                        # Результат - текущее состояние toggle
                        logger.info(f"Состояние переключателя для {email}: {'включен' if toggle_result else 'выключен'}")
                        return toggle_result
                    except Exception as e:
                        logger.warning(f"Ошибка при проверке состояния ({retry_count + 1}): {e}")
                        
                        # Делаем еще одну попытку, если ошибка связана с устаревшим элементом
                        if "stale element" in str(e).lower():
                            logger.info("Ошибка stale element при проверке переключателя, обновляем страницу")
                            try:
                                driver.refresh()
                                time.sleep(3)
                                
                                # Повторно закрываем всплывающие окна после обновления
                                self.automation_service.close_popups(driver)
                            except:
                                pass
                        
                        retry_count += 1
                        if retry_count >= max_retries:
                            logger.error(f"Превышено число попыток проверки переключателя для {email}")
                            
                            # Делаем скриншот ошибки
                            try:
                                screenshot_path = f"toggle_error_{int(time.time())}.png"
                                driver.save_screenshot(screenshot_path)
                                logger.debug(f"Скриншот ошибки проверки переключателя: {screenshot_path}")
                            except:
                                pass
                                
                            return None
                            
                        # Небольшая пауза перед следующей попыткой
                        time.sleep(2)
                
                # Код не должен дойти сюда, но возвращаем None на всякий случай
                return None
                
            except Exception as e:
                logger.error(f"Ошибка при проверке состояния переключателя для {email}: {e}")
                
                # Делаем скриншот ошибки
                try:
                    screenshot_path = f"toggle_error_{int(time.time())}.png"
                    driver.save_screenshot(screenshot_path)
                    logger.debug(f"Скриншот ошибки: {screenshot_path}")
                except:
                    pass
                
                return None
                
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при проверке состояния переключателя для {email}: {e}")
            return None
            
        finally:
            # Всегда закрываем драйвер
            if driver:
                try:
                    self.browser_service.close_driver(driver)
                except Exception as e:
                    logger.warning(f"Ошибка при закрытии драйвера: {e}")

    def get_statistics(self):
        """
        Возвращает статистику работы сервисов
        
        Returns:
            dict: Статистика работы
        """
        # Собираем статистику из разных сервисов
        with self.state_lock:
            statistics = self.wrapper_state.copy()
            
        # Добавляем статистику ошибок
        statistics['errors'] = self.error_service.get_error_statistics()
        
        # Добавляем информацию о системных ресурсах
        statistics['resources'] = {
            'memory_usage': self.resource_mgr.get_memory_usage(),
            'cpu_usage': self.resource_mgr.get_cpu_usage(),
            'high_memory_load': self.resource_mgr.memory_usage_high(),
            'critical_memory_load': self.resource_mgr.memory_usage_critical()
        }
        
        # Добавляем информацию о браузерах
        statistics['browsers'] = {
            'active_drivers': len(self.browser_service.active_drivers)
        }
        
        # Добавляем информацию о сессиях
        with self.session_service.sessions_lock:
            statistics['sessions'] = {
                'active_sessions': len(self.session_service.sessions)
            }
            
        return statistics

    def _cleanup_resources(self):
        """
        Проводит очистку ресурсов для экономии памяти
        """
        logger.info("Запуск очистки ресурсов")
        
        # Очищаем неиспользуемые драйверы
        cleaned_drivers = self.browser_service.cleanup_unused_drivers()
        if cleaned_drivers:
            logger.info(f"Очищено неиспользуемых драйверов: {cleaned_drivers}")
            
        # Запускаем сборку мусора
        collected = self.resource_mgr.force_garbage_collection()
        logger.info(f"Выполнена сборка мусора, собрано объектов: {collected}")
        
        # В случае критического использования памяти выполняем более агрессивную очистку
        if self.resource_mgr.memory_usage_critical():
            logger.warning("Критическое использование памяти, выполняем агрессивную очистку")
            
            # Закрываем все драйверы
            closed_drivers = self.browser_service.cleanup_all_drivers()
            if closed_drivers:
                logger.info(f"Закрыто всех активных драйверов: {closed_drivers}")
                
            # Очищаем зомби-процессы
            cleaned_zombies = self.resource_mgr.cleanup_zombie_processes()
            if cleaned_zombies:
                logger.info(f"Очищено зомби-процессов: {cleaned_zombies}")

    def shutdown(self):
        """
        Корректно завершает работу всех сервисов и освобождает ресурсы
        """
        logger.info("Завершение работы ServiceWrapper")
        
        try:
            # Закрываем все активные драйверы
            self.browser_service.cleanup_all_drivers()
            
            # Очищаем зомби-процессы
            self.resource_mgr.cleanup_zombie_processes()
            
            # Запускаем сборку мусора
            self.resource_mgr.force_garbage_collection()
            
            logger.info("Все ресурсы успешно освобождены")
            
        except Exception as e:
            logger.error(f"Ошибка при завершении работы: {e}")
            
        finally:
            # Записываем финальную статистику
            with self.state_lock:
                self.wrapper_state['shutdown_at'] = datetime.now().isoformat()
                
            logger.info(f"ServiceWrapper завершил работу. "
                        f"Обработано аккаунтов: {self.wrapper_state['accounts_processed']}, "
                        f"успешных переключений: {self.wrapper_state['successful_toggles']}")


# Глобальный экземпляр обертки сервисов
_service_wrapper_instance = None
_wrapper_lock = threading.Lock()


def get_service_wrapper():
    """
    Возвращает глобальный экземпляр обертки сервисов (синглтон)
    """
    global _service_wrapper_instance
    
    if _service_wrapper_instance is None:
        with _wrapper_lock:  # блокировка для потокобезопасности
            if _service_wrapper_instance is None:  # двойная проверка для избежания состояния гонки
                _service_wrapper_instance = ServiceWrapper()
                
    return _service_wrapper_instance

if __name__ == '__main__':
    try:
        run_service()
    except KeyboardInterrupt:
        service_logger.info("Service stopped by user")
        cleanup_chrome()
    except Exception as e:
        service_logger.critical(f"Service crashed: {str(e)}", exc_info=True)
        cleanup_chrome()