import os
import sys
import gc
import psutil
import platform
import logging
import threading
import time

# Получение логгера
logger = logging.getLogger(__name__)

# Синглтон для менеджера ресурсов
_resource_manager_instance = None
_instance_lock = threading.Lock()

class ResourceManager:
    """
    Менеджер системных ресурсов для оптимизации использования CPU и памяти
    """
    
    def __init__(self):
        self.system = platform.system()
        self.memory_threshold = 75  # порог высокого использования памяти, %
        self.memory_critical = 85   # порог критического использования памяти, %
        self.cpu_threshold = 80     # порог высокого использования CPU, %
        
        # Оптимальные настройки для разных систем
        if self.system == 'Linux':
            # Linux обычно имеет больше доступных ресурсов для фоновых задач
            self.max_processes = max(1, os.cpu_count() // 2)
            self.resource_check_interval = 30  # секунды
        elif self.system == 'Darwin':  # macOS
            # macOS может иметь ограничения на количество процессов браузера
            self.max_processes = max(1, os.cpu_count() // 4)
            self.resource_check_interval = 45  # секунды
        else:  # Windows или другие
            self.max_processes = max(1, os.cpu_count() // 3)
            self.resource_check_interval = 60  # секунды
            
        # Специальные настройки для ограниченных сред
        if self.is_running_in_github_codespace():
            self.memory_threshold = 60
            self.memory_critical = 75
            self.max_processes = 1  # минимизируем использование ресурсов
            self.resource_check_interval = 120  # реже проверяем ресурсы
            
        self.process = psutil.Process(os.getpid())
        self.last_check_time = 0
        self.last_memory_usage = 0
        self.last_cpu_usage = 0
        
        # Мониторинг использования ресурсов
        self._start_resource_monitoring()
        
        logger.info(f"Инициализирован ResourceManager: система={self.system}, "
                    f"макс_процессов={self.max_processes}, "
                    f"порог_памяти={self.memory_threshold}%, "
                    f"критическая_память={self.memory_critical}%")

    def _start_resource_monitoring(self):
        """Запускает фоновый мониторинг ресурсов"""
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(
            target=self._resource_monitor_loop,
            daemon=True
        )
        self.monitor_thread.start()
        
    def _resource_monitor_loop(self):
        """Фоновый мониторинг ресурсов"""
        while self.monitoring_active:
            try:
                self._check_resources()
                time.sleep(self.resource_check_interval)
            except Exception as e:
                logger.error(f"Ошибка в мониторинге ресурсов: {e}")
                time.sleep(self.resource_check_interval * 2)

    def _check_resources(self):
        """Проверяет текущее использование ресурсов и логирует превышения"""
        current_time = time.time()
        
        # Проверяем ресурсы только если прошел интервал с последней проверки
        if current_time - self.last_check_time < self.resource_check_interval:
            return
            
        self.last_check_time = current_time
        
        # Получаем текущее использование ресурсов
        memory_percent = psutil.virtual_memory().percent
        cpu_percent = psutil.cpu_percent(interval=0.5)
        
        self.last_memory_usage = memory_percent
        self.last_cpu_usage = cpu_percent
        
        # Проверяем критические пороги
        if memory_percent >= self.memory_critical:
            logger.warning(f"Критическое использование памяти: {memory_percent}%. "
                          f"Запуск очистки ресурсов.")
            self.force_garbage_collection()
            
        elif memory_percent >= self.memory_threshold:
            logger.info(f"Высокое использование памяти: {memory_percent}%")
            
        if cpu_percent >= self.cpu_threshold:
            logger.info(f"Высокое использование CPU: {cpu_percent}%")
            
        # Сохраняем использование ресурсов для данного процесса
        process_memory = self.process.memory_percent()
        process_cpu = self.process.cpu_percent() / psutil.cpu_count()
        
        if process_memory > 20:  # Если процесс занимает больше 20% памяти
            logger.info(f"Высокое использование памяти процессом: {process_memory:.1f}%")

    def get_memory_usage(self):
        """Возвращает текущий процент использования памяти"""
        # Обновляем значение, если последняя проверка была давно
        if time.time() - self.last_check_time > self.resource_check_interval:
            self._check_resources()
        return self.last_memory_usage

    def get_cpu_usage(self):
        """Возвращает текущий процент использования CPU"""
        # Обновляем значение, если последняя проверка была давно
        if time.time() - self.last_check_time > self.resource_check_interval:
            self._check_resources()
        return self.last_cpu_usage

    def memory_usage_high(self):
        """Проверяет, превышен ли порог высокого использования памяти"""
        memory_usage = self.get_memory_usage()
        return memory_usage >= self.memory_threshold
        
    def memory_usage_critical(self):
        """Проверяет, превышен ли порог критического использования памяти"""
        memory_usage = self.get_memory_usage()
        return memory_usage >= self.memory_critical
        
    def system_under_high_load(self):
        """Проверяет, находится ли система под высокой нагрузкой"""
        cpu_usage = self.get_cpu_usage()
        return cpu_usage >= self.cpu_threshold

    def force_garbage_collection(self):
        """Принудительно запускает сборку мусора для освобождения памяти"""
        try:
            logger.info("Запуск принудительной сборки мусора")
            collected = gc.collect()
            logger.info(f"Собрано объектов: {collected}")
            
            # Дополнительная очистка для PyPy (если используется)
            if hasattr(gc, 'collect_step'):
                gc.collect_step()
                
            return collected
        except Exception as e:
            logger.error(f"Ошибка при сборке мусора: {e}")
            return 0

    def get_optimal_process_count(self):
        """
        Возвращает оптимальное количество параллельных процессов с учетом текущей нагрузки
        """
        if self.is_running_in_github_codespace() or self.should_optimize_for_low_resources():
            return 1  # Минимизируем использование ресурсов
            
        # Базовое количество
        optimal = self.max_processes
        
        # Адаптация в зависимости от текущей нагрузки
        if self.memory_usage_critical():
            optimal = 1  # Минимум при критическом использовании памяти
        elif self.memory_usage_high():
            optimal = max(1, optimal // 2)  # Вдвое меньше при высоком использовании
        elif self.system_under_high_load():
            optimal = max(1, int(optimal * 0.75))  # Уменьшаем на 25% при высокой нагрузке
            
        return optimal

    def is_running_in_container(self):
        """Проверяет, запущено ли приложение в контейнере"""
        # Проверка на Docker
        if os.path.exists('/.dockerenv'):
            return True
            
        # Проверка на контейнер cgroup v1
        if os.path.exists('/proc/self/cgroup'):
            with open('/proc/self/cgroup', 'r') as f:
                if 'docker' in f.read() or 'lxc' in f.read():
                    return True
        
        return False

    def is_running_in_github_codespace(self):
        """Проверяет, запущено ли приложение в GitHub Codespace"""
        # Проверка на CODESPACES='true' или CODESPACES='1'
        if 'CODESPACES' in os.environ:
            codespaces_value = os.environ['CODESPACES'].lower()
            if codespaces_value in ('true', '1', 'yes'):
                return True
            
        # Проверка других переменных окружения GitHub Codespaces
        if any(env_var in os.environ for env_var in [
            'GITHUB_CODESPACE_TOKEN', 
            'CODESPACE_NAME'
        ]):
            return True
            
        return False

    def should_optimize_for_low_resources(self):
        """
        Проверяет, следует ли оптимизировать приложение для среды с ограниченными ресурсами
        """
        if self.is_running_in_github_codespace() or self.is_running_in_container():
            return True
            
        # Проверка доступной памяти
        available_memory_gb = psutil.virtual_memory().available / (1024 ** 3)
        if available_memory_gb < 2.0:  # Меньше 2 ГБ доступной памяти
            return True
            
        # Проверка количества ядер
        if os.cpu_count() < 2:
            return True
            
        return False

    def kill_process_by_name(self, process_name):
        """
        Принудительно убивает процессы по имени для освобождения ресурсов
        
        Args:
            process_name: Имя процесса (например, 'chrome', 'chromedriver')
        
        Returns:
            int: Количество убитых процессов
        """
        killed_count = 0
        
        try:
            for proc in psutil.process_iter(['name', 'pid']):
                if process_name.lower() in proc.info['name'].lower():
                    try:
                        process = psutil.Process(proc.info['pid'])
                        process.terminate()
                        killed_count += 1
                        logger.info(f"Завершен процесс {proc.info['name']} (PID: {proc.info['pid']})")
                    except Exception as e:
                        logger.error(f"Ошибка при завершении процесса {proc.info['name']}: {e}")
                        try:
                            process.kill()  # Пробуем более жесткое завершение
                            killed_count += 1
                            logger.info(f"Принудительно завершен процесс {proc.info['name']} (PID: {proc.info['pid']})")
                        except:
                            pass
        except Exception as e:
            logger.error(f"Ошибка при поиске процессов {process_name}: {e}")
        
        return killed_count
    
    def cleanup_zombie_processes(self):
        """
        Очищает зомби-процессы для освобождения ресурсов
        
        Returns:
            int: Количество очищенных зомби-процессов
        """
        if platform.system() == 'Windows':
            return 0  # На Windows нет концепции зомби-процессов
            
        cleaned_count = 0
        try:
            for proc in psutil.process_iter(['name', 'pid', 'status']):
                if proc.info['status'] == 'zombie':
                    try:
                        os.waitpid(proc.info['pid'], os.WNOHANG)
                        cleaned_count += 1
                        logger.info(f"Очищен зомби-процесс (PID: {proc.info['pid']})")
                    except:
                        pass
        except Exception as e:
            logger.error(f"Ошибка при очистке зомби-процессов: {e}")
            
        return cleaned_count


def get_resource_manager():
    """
    Возвращает глобальный экземпляр менеджера ресурсов (синглтон)
    """
    global _resource_manager_instance
    
    if _resource_manager_instance is None:
        with _instance_lock:  # Блокировка для потокобезопасности
            if _resource_manager_instance is None:  # Двойная проверка для избежания состояния гонки
                _resource_manager_instance = ResourceManager()
                
    return _resource_manager_instance 