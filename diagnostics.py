import psutil
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def get_process_info(proc):
    """Get detailed process information"""
    try:
        return {
            'pid': proc.pid,
            'memory': proc.memory_info().rss / 1024 / 1024,  # MB
            'cpu': proc.cpu_percent(),
            'status': proc.status(),
            'create_time': datetime.fromtimestamp(proc.create_time())
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None

def log_system_status():
    """Log current system status"""
    mem = psutil.virtual_memory()
    logger.info(f"Memory usage: {mem.percent}% (Available: {mem.available/1024/1024:.1f}MB)")
    
    chrome_processes = []
    for proc in psutil.process_iter(['name']):
        try:
            if proc.name() in ['chrome', 'chromedriver']:
                info = get_process_info(proc)
                if info:
                    chrome_processes.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
            
    logger.info(f"Chrome processes: {len(chrome_processes)}")
    for proc in chrome_processes:
        logger.info(f"Chrome PID {proc['pid']}: {proc['memory']:.1f}MB, CPU: {proc['cpu']}%")

def kill_orphaned_processes():
    """Kill chrome processes older than threshold"""
    threshold = 3600  # 1 hour
    now = datetime.now()
    killed = 0
    
    for proc in psutil.process_iter(['name', 'pid', 'create_time']):
        try:
            if proc.name() in ['chrome', 'chromedriver']:
                age = (now - datetime.fromtimestamp(proc.create_time())).total_seconds()
                if age > threshold:
                    proc.kill()
                    killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
            
    if killed:
        logger.info(f"Killed {killed} orphaned chrome processes")

def log_memory_usage():
    """
    Логирует и возвращает информацию об использовании памяти системой.
    
    Returns:
        str: Строка с информацией об использовании памяти
    """
    mem = psutil.virtual_memory()
    memory_info = f"Memory: {mem.percent}% used (Available: {mem.available/1024/1024:.1f}MB)"
    logger.info(memory_info)
    return memory_info

def log_chrome_processes():
    """
    Логирует и возвращает информацию о процессах Chrome и ChromeDriver.
    
    Returns:
        str: Строка с информацией о процессах Chrome
    """
    chrome_processes = []
    
    try:
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                proc_name = proc.name().lower()
                if 'chrome' in proc_name or 'chromedriver' in proc_name:
                    # Получаем информацию о процессе
                    proc_info = {
                        'pid': proc.pid,
                        'name': proc.name(),
                        'memory_mb': proc.memory_info().rss / 1024 / 1024  # Конвертируем в МБ
                    }
                    chrome_processes.append(proc_info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        logger.error(f"Ошибка при получении информации о процессах Chrome: {e}")
        
    # Формируем строку с информацией
    total_memory = sum(p['memory_mb'] for p in chrome_processes)
    info = f"Chrome processes: {len(chrome_processes)}"
    
    if chrome_processes:
        info += f", Total memory: {total_memory:.1f}MB"
        # Добавляем детали о процессах
        for proc in chrome_processes:
            info += f"\nPID {proc['pid']} ({proc['name']}): {proc['memory_mb']:.1f}MB"
    
    logger.info(info)
    return info
