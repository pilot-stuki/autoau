import os
import subprocess
import threading
import time
import logging
import psutil
import platform
import stat
from pathlib import Path
from datetime import datetime

# Настройка логгера
logger = logging.getLogger(__name__)

def log_memory_usage():
    """
    Логирует информацию об использовании памяти
    
    Returns:
        str: Строка с информацией о памяти
    """
    try:
        # Получаем информацию о виртуальной памяти
        mem = psutil.virtual_memory()
        
        # Получаем информацию о текущем процессе
        try:
            current_process = psutil.Process(os.getpid())
            process_memory = current_process.memory_info().rss / (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            process_memory = 0
        
        return f"{mem.percent}% used, {process_memory:.1f}MB for this process"
    except Exception as e:
        logger.error(f"Ошибка при получении информации о памяти: {e}")
        return "Error"

def log_chrome_processes():
    """
    Логирует информацию о запущенных процессах Chrome
    
    Returns:
        str: Строка с информацией о процессах
    """
    try:
        # Безопасное получение информации о Chrome процессах
        chrome_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cmdline']):
            try:
                proc_name = proc.info['name'].lower() if proc.info.get('name') else ''
                is_chrome = 'chrome' in proc_name or 'google-chrome' in proc_name
                if is_chrome:
                    memory = proc.info.get('memory_info')
                    if memory:
                        memory_mb = memory.rss / (1024 * 1024)
                        chrome_processes.append((proc.info['pid'], memory_mb))
                    else:
                        chrome_processes.append((proc.info['pid'], 0))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # Пропускаем процессы, к которым нет доступа или которые уже завершились
                continue

        if chrome_processes:
            return f"{len(chrome_processes)} processes, {sum(m for _, m in chrome_processes):.1f}MB"
        else:
            return "0 processes"
    except Exception as e:
        logger.error(f"Ошибка при получении информации о Chrome процессах: {e}")
        return "Error"

def log_system_info():
    """
    Логирует общую информацию о системе
    """
    try:
        # Информация о системе
        logger.info(f"Операционная система: {platform.system()} {platform.version()}")
        logger.info(f"Имя компьютера: {platform.node()}")
        logger.info(f"Процессор: {platform.processor()}")
        
        # Информация о CPU
        cpu_count = psutil.cpu_count(logical=False)
        cpu_logical = psutil.cpu_count(logical=True)
        cpu_percent = psutil.cpu_percent(interval=1)
        logger.info(f"Физические ядра: {cpu_count}, Логические ядра: {cpu_logical}")
        logger.info(f"Текущая загрузка CPU: {cpu_percent}%")
        
        # Информация о памяти
        mem = psutil.virtual_memory()
        logger.info(f"Оперативная память: {mem.total / 1024 / 1024 / 1024:.2f} GB")
        logger.info(f"Использовано памяти: {mem.used / 1024 / 1024 / 1024:.2f} GB ({mem.percent}%)")
        
        # Информация о дисках
        disk = psutil.disk_usage('/')
        logger.info(f"Диск: Всего={disk.total / 1024 / 1024 / 1024:.2f} GB, "
                   f"Свободно={disk.free / 1024 / 1024 / 1024:.2f} GB ({disk.percent}% использовано)")
        
        # Время работы системы
        boot_time = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Система запущена с: {boot_time}")
        
    except Exception as e:
        logger.error(f"Ошибка при логировании системной информации: {e}")

def log_network_status():
    """
    Проверяет и логирует состояние сетевого подключения
    """
    try:
        # Проверяем доступность популярных сайтов
        targets = [
            "google.com",
            "microsoft.com",
            "cloudflare.com",
            "scarletblue.com.au"  # Целевой сайт
        ]
        
        for target in targets:
            try:
                # Используем разные команды в зависимости от ОС
                param = '-n' if platform.system().lower() == 'windows' else '-c'
                
                # Выполняем ping с тайм-аутом для предотвращения зависаний
                cmd = ['ping', param, '1', '-W', '2', target]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                
                if result.returncode == 0:
                    logger.info(f"Сайт {target} доступен")
                else:
                    logger.warning(f"Сайт {target} недоступен: {result.stdout}")
            except subprocess.TimeoutExpired:
                logger.warning(f"Таймаут при проверке {target}")
            except Exception as e:
                logger.warning(f"Ошибка при проверке {target}: {e}")
        
        # Сетевые соединения
        connections = len(psutil.net_connections())
        logger.info(f"Активных сетевых соединений: {connections}")
        
    except Exception as e:
        logger.error(f"Ошибка при проверке сетевого статуса: {e}")

def verify_chrome_installation():
    """
    Проверяет установку Chrome и связанные компоненты
    
    Returns:
        dict: Словарь с результатами проверки
    """
    results = {
        "chrome_binary_exists": False,
        "chrome_binary_path": None,
        "chrome_binary_executable": False,
        "chrome_binary_permissions": None,
        "chrome_driver_exists": False,
        "chrome_driver_path": None,
        "chrome_driver_executable": False,
        "tmp_dir_writable": False,
        "display_set": False
    }
    
    # Проверяем Chrome бинарный файл
    chrome_paths = [
        "/opt/google/chrome/google-chrome",
        "/opt/google/chrome/chrome",
        "/usr/bin/google-chrome",
        "/opt/autoau/bin/google-chrome"
    ]
    
    for path in chrome_paths:
        if os.path.exists(path):
            results["chrome_binary_exists"] = True
            results["chrome_binary_path"] = path
            
            # Проверяем запускаемость
            is_executable = os.access(path, os.X_OK)
            results["chrome_binary_executable"] = is_executable
            
            # Получаем права доступа
            try:
                file_stat = os.stat(path)
                permissions = stat.filemode(file_stat.st_mode)
                results["chrome_binary_permissions"] = permissions
            except Exception as e:
                logger.warning(f"Не удалось получить права доступа для {path}: {e}")
            
            break
    
    # Проверяем ChromeDriver
    chromedriver_paths = [
        "/opt/autoau/drivers/chromedriver",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "drivers", "chromedriver")
    ]
    
    for path in chromedriver_paths:
        if os.path.exists(path):
            results["chrome_driver_exists"] = True
            results["chrome_driver_path"] = path
            results["chrome_driver_executable"] = os.access(path, os.X_OK)
            break
    
    # Проверяем наличие переменной DISPLAY
    display = os.environ.get("DISPLAY")
    results["display_set"] = display is not None
    results["display_value"] = display
    
    # Проверяем доступность /tmp для записи
    try:
        tmp_dir = "/tmp"
        test_file = os.path.join(tmp_dir, f"chrome_test_{int(time.time())}")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        results["tmp_dir_writable"] = True
    except Exception as e:
        logger.warning(f"Директория /tmp недоступна для записи: {e}")
    
    return results

def check_chrome_process_health():
    """
    Проверяет здоровье процессов Chrome и выполняет очистку при необходимости
    
    Returns:
        dict: Информация о процессах Chrome
    """
    results = {
        "total_processes": 0,
        "zombie_processes": 0,
        "hanging_processes": 0,
        "processes_cleaned": 0,
        "total_memory_mb": 0
    }
    
    try:
        chrome_processes = []
        zombie_procs = []
        hanging_procs = []
        
        for proc in psutil.process_iter(['pid', 'name', 'status', 'memory_info', 'cpu_percent', 'create_time']):
            try:
                proc_name = proc.info['name'].lower() if proc.info.get('name') else ''
                
                is_chrome = 'chrome' in proc_name or 'google-chrome' in proc_name
                if not is_chrome:
                    continue
                    
                chrome_processes.append(proc)
                
                # Проверка на зомби-процесс
                if proc.info.get('status') == psutil.STATUS_ZOMBIE:
                    zombie_procs.append(proc)
                    continue
                
                # Проверка на зависший процесс (0% CPU и давно работает)
                if proc.info.get('cpu_percent', 0) == 0 and proc.info.get('create_time'):
                    proc_age = time.time() - proc.info['create_time']
                    if proc_age > 300:  # Более 5 минут без активности CPU
                        hanging_procs.append(proc)
                
                # Суммируем память
                memory = proc.info.get('memory_info')
                if memory:
                    results["total_memory_mb"] += memory.rss / (1024 * 1024)
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        results["total_processes"] = len(chrome_processes)
        results["zombie_processes"] = len(zombie_procs)
        results["hanging_processes"] = len(hanging_procs)
        
        # Очистка проблемных процессов, если их слишком много
        if len(zombie_procs) > 3 or len(hanging_procs) > 2:
            logger.warning(f"Обнаружено {len(zombie_procs)} зомби и {len(hanging_procs)} зависших процессов Chrome. Запуск очистки.")
            
            for proc in zombie_procs + hanging_procs:
                try:
                    proc.kill()
                    results["processes_cleaned"] += 1
                except Exception:
                    pass
    
    except Exception as e:
        logger.error(f"Ошибка при проверке здоровья процессов Chrome: {e}")
    
    return results

def diagnose_system():
    """
    Проводит комплексную диагностику системы
    """
    logger.info("==== Начало системной диагностики ====")
    
    # Логируем базовую информацию о системе
    log_system_info()
    
    # Проверяем использование памяти
    memory_info = log_memory_usage()
    logger.info(f"Использование памяти: {memory_info}")
    
    # Проверяем процессы Chrome
    chrome_info = log_chrome_processes()
    logger.info(f"Процессы Chrome: {chrome_info}")
    
    # Проверяем установку Chrome
    chrome_installation = verify_chrome_installation()
    logger.info(f"Проверка Chrome: бинарный файл={chrome_installation['chrome_binary_path']}, "  
                f"существует={chrome_installation['chrome_binary_exists']}, "  
                f"исполняемый={chrome_installation['chrome_binary_executable']}")
    logger.info(f"Проверка ChromeDriver: существует={chrome_installation['chrome_driver_exists']}, "  
                f"путь={chrome_installation['chrome_driver_path']}")
    logger.info(f"Переменная DISPLAY: {chrome_installation['display_value']}")
    
    # Проверяем здоровье процессов Chrome
    chrome_health = check_chrome_process_health()
    logger.info(f"Здоровье Chrome: всего={chrome_health['total_processes']}, "  
                f"зомби={chrome_health['zombie_processes']}, "  
                f"зависшие={chrome_health['hanging_processes']}, "  
                f"очищено={chrome_health['processes_cleaned']}")
    
    # Проверяем сетевое подключение
    log_network_status()
    
    logger.info("==== Конец системной диагностики ====")

if __name__ == "__main__":
    # Настройка логирования для тестирования
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    # Запуск диагностики
    diagnose_system()