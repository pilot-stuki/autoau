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
