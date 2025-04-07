import os
import subprocess
import threading
import time
import logging
import psutil
import platform
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
        for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                if 'chrome' in proc.info['name'].lower():
                    memory = proc.info.get('memory_info')
                    if memory:
                        memory_mb = memory.rss / (1024 * 1024)
                        chrome_processes.append((proc.info['pid'], memory_mb))
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

def diagnose_system():
    """
    Проводит комплексную диагностику системы
    """
    logger.info("==== Начало системной диагностики ====")
    
    # Логируем базовую информацию о системе
    log_system_info()
    
    # Проверяем использование памяти
    log_memory_usage()
    
    # Проверяем процессы Chrome (с таймаутом 3 секунды)
    log_chrome_processes()
    
    # Проверяем сетевое подключение
    log_network_status()
    
    logger.info("==== Конец системной диагностики ====")

if __name__ == "__main__":
    # Настройка логирования для тестирования
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    # Запуск диагностики
    diagnose_system() 