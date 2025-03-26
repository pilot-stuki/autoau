import os
import sys
import time
import random
import threading
import logging
import traceback
from datetime import datetime, timedelta
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import importlib

# Создаем свой класс TimeoutError, если он не доступен
try:
    from concurrent.futures import TimeoutError
except ImportError:
    class TimeoutError(Exception):
        """The operation timed out."""
        pass

# Получение логгера
logger = logging.getLogger(__name__)

# Синглтон и блокировка для потокобезопасности
_error_service_instance = None
_instance_lock = threading.Lock()


class ErrorSeverity(Enum):
    """Уровни серьезности ошибок"""
    LOW = 1        # Некритичные ошибки, можно продолжать работу
    MEDIUM = 2     # Ошибки среднего уровня, требуют внимания
    HIGH = 3       # Серьезные ошибки, требуют немедленной реакции
    CRITICAL = 4   # Критические ошибки, невозможно продолжать работу
    
    
class ErrorScope(Enum):
    """Типы ошибок для классификации"""
    NETWORK = "network"              # Сетевые ошибки
    BROWSER = "browser"              # Ошибки браузера
    ELEMENT = "element"              # Ошибки при работе с элементами страницы
    AUTH = "auth"                    # Ошибки авторизации
    SYSTEM = "system"                # Системные ошибки (нехватка памяти и т.д.)
    TIMEOUT = "timeout"              # Ошибки таймаута
    RESOURCE = "resource"            # Ошибки ресурсов
    PERMISSION = "permission"        # Ошибки прав доступа
    SESSION = "session"              # Ошибки сессии
    INTERACTION = "interaction"      # Ошибки взаимодействия с элементами
    UNKNOWN = "unknown"              # Неклассифицированные ошибки


class ErrorService:
    """
    Сервис для стандартизированной обработки и классификации ошибок
    """
    
    def __init__(self):
        """Инициализация сервиса обработки ошибок"""
        # Счетчики ошибок для отслеживания трендов
        self.error_counters = {scope: 0 for scope in ErrorScope}
        
        # История ошибок для анализа паттернов
        self.recent_errors = []
        self.max_error_history = 100
        self.error_history_lock = threading.Lock()
        
        # Настройки повторных попыток по умолчанию
        self.default_retry_count = 3
        self.default_retry_delay = 2  # секунды
        self.max_retry_delay = 60  # максимальная задержка между повторами
        
        # Порог для адаптивного увеличения задержки
        self.consecutive_errors_threshold = 5
        
        # Настройки для политик обработки ошибок
        self.error_policies = {
            ErrorScope.NETWORK: {
                'max_retries': 3,
                'retry_delay': 5,
                'exponential_backoff': True
            },
            ErrorScope.BROWSER: {
                'max_retries': 2,
                'retry_delay': 3,
                'exponential_backoff': True
            },
            ErrorScope.ELEMENT: {
                'max_retries': 4,
                'retry_delay': 2,
                'exponential_backoff': True
            },
            ErrorScope.AUTH: {
                'max_retries': 3,
                'retry_delay': 3,
                'exponential_backoff': True
            },
            ErrorScope.SYSTEM: {
                'max_retries': 2,
                'retry_delay': 10,
                'exponential_backoff': True
            },
            ErrorScope.TIMEOUT: {
                'max_retries': 1,
                'retry_delay': 10,
                'exponential_backoff': False
            },
            ErrorScope.RESOURCE: {
                'max_retries': 2,
                'retry_delay': 5,
                'exponential_backoff': True
            },
            ErrorScope.PERMISSION: {
                'max_retries': 2,
                'retry_delay': 5,
                'exponential_backoff': True
            },
            ErrorScope.UNKNOWN: {
                'max_retries': 2,
                'retry_delay': 5,
                'exponential_backoff': True
            }
        }
        
        logger.info("Инициализирован ErrorService")
        
    def classify_error(self, exception):
        """
        Классифицирует ошибку по типу и серьезности
        
        Args:
            exception: Экземпляр исключения для классификации
            
        Returns:
            tuple: (ErrorScope, ErrorSeverity) - тип и серьезность ошибки
        """
        error_type = str(type(exception).__name__)
        error_msg = str(exception).lower()
        
        # Ошибки таймаута (проверяем первыми)
        if 'TimeoutException' in error_type or 'timeout' in error_msg:
            return ErrorScope.TIMEOUT, ErrorSeverity.MEDIUM
            
        # Ошибки сети
        if any(net_err in error_type for net_err in ['ConnectionError', 'TimeoutError', 'ConnectionRefusedError']) or \
           any(net_msg in error_msg for net_msg in ['network', 'connection', 'refused']):
            return ErrorScope.NETWORK, ErrorSeverity.MEDIUM
            
        # Ошибки сессии
        if 'session' in error_msg.lower() or 'cookie' in error_msg.lower() or 'expired' in error_msg.lower():
            return ErrorScope.SESSION, ErrorSeverity.MEDIUM
            
        # Ошибки взаимодействия с элементами (проверяем перед ошибками элементов)
        if 'ElementNotInteractableException' in error_type or 'ElementClickInterceptedException' in error_type or \
           'not clickable' in error_msg or 'not interactable' in error_msg:
            return ErrorScope.INTERACTION, ErrorSeverity.MEDIUM
            
        # Ошибки браузера
        if 'WebDriverException' in error_type or \
           any(browser_msg in error_msg for browser_msg in ['chrome', 'browser', 'driver', 'selenium']):
            return ErrorScope.BROWSER, ErrorSeverity.HIGH
            
        # Ошибки элементов страницы
        if any(elem_err in error_type for elem_err in ['ElementNotVisibleException', 'NoSuchElementException']) or \
           any(elem_msg in error_msg for elem_msg in ['element', 'input', 'form']):
            return ErrorScope.ELEMENT, ErrorSeverity.MEDIUM
            
        # Ошибки авторизации
        if any(auth_msg in error_msg for auth_msg in ['auth', 'login', 'password', 'credentials']):
            return ErrorScope.AUTH, ErrorSeverity.HIGH
            
        # Системные ошибки
        if any(sys_err in error_type for sys_err in ['OSError', 'IOError', 'PermissionError']):
            return ErrorScope.SYSTEM, ErrorSeverity.HIGH
            
        # Ошибки ресурсов
        if 'memory' in error_msg or 'resource' in error_msg or 'out of' in error_msg:
            return ErrorScope.RESOURCE, ErrorSeverity.HIGH
            
        # Если не удалось классифицировать
        return ErrorScope.UNKNOWN, ErrorSeverity.MEDIUM

    def handle_error(self, exception, operation_name=None, retry_callback=None, retry_timeout=60):
        """
        Обрабатывает ошибку с возможностью повторных попыток
        
        Args:
            exception: Экземпляр исключения
            operation_name: Название операции, вызвавшей ошибку
            retry_callback: Функция обратного вызова для повторной попытки
            retry_timeout: Таймаут для выполнения повторной попытки в секундах
            
        Returns:
            tuple: (success, result) - результат повторной попытки или (False, None)
        """
        error_scope, error_severity = self.classify_error(exception)
        
        # Особая обработка для таймаутов
        if isinstance(exception, TimeoutError) or "timeout" in str(exception).lower():
            logger.error(f"Таймаут операции '{operation_name}': {exception}")
            error_scope = ErrorScope.TIMEOUT
            error_severity = ErrorSeverity.HIGH
        
        # Логируем информацию об ошибке
        if operation_name:
            logger.error(f"Ошибка при выполнении '{operation_name}': {exception} "
                        f"(тип: {error_scope.value}, серьезность: {error_severity.name})")
        else:
            logger.error(f"Ошибка: {exception} (тип: {error_scope.value}, серьезность: {error_severity.name})")
            
        # Показываем трассировку только для серьезных ошибок
        if error_severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            logger.error(f"Трассировка: {''.join(traceback.format_tb(exception.__traceback__))}")
            
        # Записываем ошибку в историю
        self._record_error(error_scope, error_severity, exception, operation_name)
        
        # Если нет функции повторной попытки, просто возвращаем ошибку
        if not retry_callback:
            return False, None
            
        # Получаем политику обработки для данного типа ошибки
        policy = self.error_policies.get(error_scope, self.error_policies[ErrorScope.UNKNOWN])
        max_retries = policy['max_retries']
        retry_delay = policy['retry_delay']
        exponential_backoff = policy['exponential_backoff']
        
        # Для таймаутов ограничиваем количество повторных попыток
        if error_scope == ErrorScope.TIMEOUT:
            max_retries = min(max_retries, 1)  # Максимум 1 повторная попытка для таймаутов
            retry_delay = max(retry_delay, 5)  # Минимум 5 секунд задержки
        
        # Адаптивная настройка интервала повторных попыток
        recent_scope_errors = self._count_recent_errors(error_scope, timedelta(minutes=10))
        if recent_scope_errors > self.consecutive_errors_threshold:
            # Увеличиваем время между повторами для частых ошибок
            retry_delay *= 2
            max_retries = max(1, max_retries // 2)  # уменьшаем количество попыток
            
        # Выполняем повторные попытки
        for attempt in range(max_retries):
            # Рассчитываем задержку перед повторной попыткой
            current_delay = retry_delay
            if exponential_backoff:
                # Экспоненциальное увеличение задержки + случайный компонент
                current_delay = min(
                    retry_delay * (2 ** attempt) + random.uniform(0, 1),
                    self.max_retry_delay
                )
                
            # Логируем информацию о повторной попытке
            logger.info(f"Повторная попытка {attempt+1}/{max_retries} через {current_delay:.1f} секунд "
                       f"для операции '{operation_name or 'unknown'}'")
                       
            # Ждем перед повторной попыткой
            time.sleep(current_delay)
            
            try:
                # Создаем класс для обмена данными между потоками
                class RetryResultContainer:
                    def __init__(self):
                        self.result = None
                        self.exception = None
                        self.completed = False
                
                container = RetryResultContainer()
                
                # Функция для выполнения retry_callback в отдельном потоке
                def run_retry():
                    try:
                        result = retry_callback()
                        container.result = result
                        container.completed = True
                    except Exception as e:
                        container.exception = e
                
                # Создаем и запускаем поток
                retry_thread = threading.Thread(target=run_retry)
                retry_thread.daemon = True
                retry_thread.start()
                
                # Ждем завершения с таймаутом
                retry_thread.join(retry_timeout)
                
                # Проверяем результат
                if retry_thread.is_alive():
                    # Повторная попытка не завершилась в течение таймаута
                    logger.error(f"Таймаут повторной попытки #{attempt+1} для '{operation_name}' после {retry_timeout}с")
                    continue  # Пробуем следующую попытку
                
                if container.completed:
                    # Повторная попытка завершилась успешно
                    logger.info(f"Повторная попытка {attempt+1} успешна для операции '{operation_name or 'unknown'}'")
                    return True, container.result
                
                if container.exception:
                    # Повторная попытка завершилась с ошибкой
                    retry_ex = container.exception
                    # Классифицируем новую ошибку
                    new_scope, new_severity = self.classify_error(retry_ex)
                    
                    # Если тип ошибки изменился, возможно стоит прекратить повторные попытки
                    if new_scope != error_scope:
                        logger.warning(f"Изменение типа ошибки при повторной попытке: {error_scope.value} -> {new_scope.value}")
                        
                    # Если серьезность повысилась, прекращаем повторные попытки
                    if new_severity.value > error_severity.value:
                        logger.warning(f"Повышение серьезности ошибки при повторной попытке. Прекращение повторных попыток.")
                        self._record_error(new_scope, new_severity, retry_ex, operation_name)
                        break
                        
                    # Записываем ошибку повторной попытки
                    self._record_error(new_scope, new_severity, retry_ex, operation_name)
                    logger.error(f"Повторная попытка {attempt+1} не удалась: {retry_ex}")
                    
            except Exception as e:
                logger.error(f"Ошибка при выполнении повторной попытки {attempt+1}: {e}")
                
        # Если все повторные попытки не удались
        logger.error(f"Все повторные попытки ({max_retries}) не удались для операции '{operation_name or 'unknown'}'")
        return False, None

    def retry_operation(self, operation, operation_name=None, max_retries=None, retry_delay=None, timeout=60):
        """
        Выполняет операцию с автоматическими повторными попытками
        
        Args:
            operation: Функция для выполнения
            operation_name: Название операции для логирования
            max_retries: Максимальное количество повторных попыток
            retry_delay: Задержка между повторными попытками
            timeout: Таймаут для выполнения операции в секундах
            
        Returns:
            Результат выполнения operation или None в случае неудачи
        """
        logger.debug(f"Начало операции '{operation_name}' с таймаутом {timeout}с")
        
        if max_retries is None:
            max_retries = self.default_retry_count
            
        if retry_delay is None:
            retry_delay = self.default_retry_delay
            
        # Создаем класс для обмена данными между потоками
        class ResultContainer:
            def __init__(self):
                self.result = None
                self.exception = None
                self.completed = False
                
        result_container = ResultContainer()
        
        # Функция для выполнения операции в отдельном потоке
        def run_operation():
            try:
                result = operation()
                result_container.result = result
                result_container.completed = True
            except Exception as e:
                result_container.exception = e
                logger.error(f"Ошибка при выполнении операции '{operation_name}': {e}")
                
        # Создаем и запускаем поток
        import threading
        operation_thread = threading.Thread(target=run_operation)
        operation_thread.daemon = True  # Поток не будет блокировать завершение программы
        operation_thread.start()
        
        # Ждем завершения с таймаутом
        operation_thread.join(timeout)
        
        # Проверяем результат
        if operation_thread.is_alive():
            # Операция не завершилась в течение таймаута
            logger.error(f"Таймаут операции '{operation_name}' после {timeout}с")
            return None
            
        if result_container.completed:
            # Операция завершилась успешно
            logger.debug(f"Операция '{operation_name}' успешно выполнена")
            return result_container.result
            
        # Операция завершилась с ошибкой, пробуем повторные попытки
        if result_container.exception:
            # В случае ошибки используем обработчик
            def retry_func():
                retry_result_container = ResultContainer()
                
                def run_retry():
                    try:
                        retry_result = operation()
                        retry_result_container.result = retry_result
                        retry_result_container.completed = True
                    except Exception as e:
                        retry_result_container.exception = e
                        
                # Запускаем повторную попытку в отдельном потоке
                retry_thread = threading.Thread(target=run_retry)
                retry_thread.daemon = True
                retry_thread.start()
                retry_thread.join(timeout)
                
                if retry_thread.is_alive():
                    logger.error(f"Таймаут повторной попытки '{operation_name}' после {timeout}с")
                    raise TimeoutError(f"Таймаут операции '{operation_name}'")
                    
                if retry_result_container.completed:
                    return retry_result_container.result
                    
                if retry_result_container.exception:
                    raise retry_result_container.exception
                    
                raise Exception(f"Неизвестная ошибка при повторной попытке '{operation_name}'")
                
            success, result = self.handle_error(result_container.exception, operation_name, retry_func)
            return result if success else None
            
        # Неизвестная ошибка
        logger.error(f"Неизвестная ошибка при выполнении операции '{operation_name}'")
        return None

    def _record_error(self, error_scope, error_severity, exception, operation_name=None):
        """
        Записывает информацию об ошибке в историю
        
        Args:
            error_scope: Тип ошибки
            error_severity: Серьезность ошибки
            exception: Экземпляр исключения
            operation_name: Название операции, вызвавшей ошибку
        """
        with self.error_history_lock:
            # Увеличиваем счетчик для данного типа ошибки
            self.error_counters[error_scope] += 1
            
            # Создаем запись об ошибке
            error_record = {
                'timestamp': datetime.now(),
                'scope': error_scope,
                'severity': error_severity,
                'operation': operation_name,
                'message': str(exception),
                'type': type(exception).__name__
            }
            
            # Добавляем в историю
            self.recent_errors.append(error_record)
            
            # Ограничиваем размер истории
            if len(self.recent_errors) > self.max_error_history:
                self.recent_errors = self.recent_errors[-self.max_error_history:]

    def _count_recent_errors(self, error_scope, time_window):
        """
        Подсчитывает количество недавних ошибок определенного типа
        
        Args:
            error_scope: Тип ошибки для подсчета
            time_window: Временное окно для подсчета (timedelta)
            
        Returns:
            int: Количество ошибок указанного типа в данном временном окне
        """
        with self.error_history_lock:
            now = datetime.now()
            count = 0
            
            for error in self.recent_errors:
                if error['scope'] == error_scope and (now - error['timestamp']) < time_window:
                    count += 1
                    
            return count

    def get_error_statistics(self):
        """
        Возвращает статистику ошибок
        
        Returns:
            dict: Статистика ошибок по типам
        """
        with self.error_history_lock:
            stats = {scope.value: 0 for scope in ErrorScope}
            
            # Подсчитываем ошибки за последние 24 часа
            time_window = timedelta(hours=24)
            now = datetime.now()
            
            for error in self.recent_errors:
                if (now - error['timestamp']) < time_window:
                    stats[error['scope'].value] += 1
                    
            return stats

    def reset_error_counters(self):
        """Сбрасывает счетчики ошибок"""
        with self.error_history_lock:
            self.error_counters = {scope: 0 for scope in ErrorScope}

    def clear_error_history(self):
        """Очищает историю ошибок"""
        with self.error_history_lock:
            self.recent_errors.clear()


def get_error_service():
    """
    Возвращает глобальный экземпляр сервиса обработки ошибок (синглтон)
    """
    global _error_service_instance
    
    if _error_service_instance is None:
        with _instance_lock:  # блокировка для потокобезопасности
            if _error_service_instance is None:  # двойная проверка для избежания состояния гонки
                _error_service_instance = ErrorService()
                
    return _error_service_instance 