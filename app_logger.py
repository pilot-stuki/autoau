import logging
import os
import time
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime
import gzip
import shutil


def compress_log(source_path):
    """Сжимает старые лог-файлы для экономии места на диске"""
    with open(source_path, 'rb') as f_in:
        with gzip.open(f"{source_path}.gz", 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    os.remove(source_path)  # Удаляем оригинальный файл после сжатия


class CompressedRotatingFileHandler(RotatingFileHandler):
    """Расширенный обработчик логов с поддержкой сжатия старых файлов"""
    
    def doRollover(self):
        """
        Переопределенный метод ротации с добавлением сжатия старых файлов
        """
        if self.stream:
            self.stream.close()
            self.stream = None
            
        if self.backupCount > 0:
            # Сдвигаем все существующие файлы
            for i in range(self.backupCount - 1, 0, -1):
                sfn = self.rotation_filename("%s.%d" % (self.baseFilename, i))
                dfn = self.rotation_filename("%s.%d" % (self.baseFilename, i + 1))
                if os.path.exists(sfn):
                    if os.path.exists(dfn):
                        os.remove(dfn)
                    os.rename(sfn, dfn)
                    # Сжимаем файл после перемещения
                    if not dfn.endswith('.gz'):
                        compress_log(dfn)
                        
            dfn = self.rotation_filename(self.baseFilename + ".1")
            if os.path.exists(dfn):
                os.remove(dfn)
            self.rotate(self.baseFilename, dfn)
            
        self.mode = 'w'
        self.stream = self._open()


def get_log_format(detailed=False):
    """Возвращает формат логов с разной степенью детализации"""
    if detailed:
        return '%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s'
    return '%(asctime)s [%(levelname)s] %(message)s'


def setup_log_directory():
    """Создает директорию для логов с учетом текущей даты"""
    base_log_dir = 'logs'
    if not os.path.exists(base_log_dir):
        os.makedirs(base_log_dir, exist_ok=True)
    
    today = datetime.now().strftime('%Y-%m-%d')
    daily_log_dir = os.path.join(base_log_dir, today)
    if not os.path.exists(daily_log_dir):
        os.makedirs(daily_log_dir, exist_ok=True)
    
    return daily_log_dir


def get_file_handler(log_file, max_bytes=5*1024*1024, backup_count=5, level=logging.INFO):
    """
    Создает обработчик файла логов с сжатием
    
    Args:
        log_file: путь к файлу логов
        max_bytes: максимальный размер файла до ротации
        backup_count: количество файлов бэкапа
        level: уровень логирования
    """
    file_handler = CompressedRotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(get_log_format()))
    
    return file_handler


def get_timed_file_handler(log_file, when='midnight', interval=1, backup_count=7, level=logging.INFO):
    """
    Создает обработчик файла логов с ротацией по времени
    
    Args:
        log_file: путь к файлу логов
        when: интервал ротации (S, M, H, D, midnight)
        interval: количество интервалов между ротациями
        backup_count: количество файлов бэкапа
        level: уровень логирования
    """
    file_handler = TimedRotatingFileHandler(
        log_file,
        when=when,
        interval=interval,
        backupCount=backup_count
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(get_log_format()))
    
    # Добавляем сжатие для старых файлов
    original_doRollover = file_handler.doRollover
    
    def custom_rollover():
        original_doRollover()
        # Находим и сжимаем старые файлы логов
        log_dir = os.path.dirname(log_file)
        base_filename = os.path.basename(log_file)
        for filename in os.listdir(log_dir):
            if filename.startswith(base_filename) and not filename.endswith('.gz') and filename != base_filename:
                compress_log(os.path.join(log_dir, filename))
    
    file_handler.doRollover = custom_rollover
    return file_handler


def get_logger(name, log_to_console=True, log_directory=None):
    """
    Возвращает настроенный логгер с поддержкой ротации и сжатия
    
    Args:
        name: имя логгера
        log_to_console: выводить ли логи в консоль
        log_directory: директория для хранения логов
        
    Returns:
        logging.Logger: настроенный логгер
    """
    if log_directory is None:
        log_directory = setup_log_directory()
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # Очищаем существующие обработчики, если они уже были добавлены
    if logger.handlers:
        logger.handlers.clear()
    
    # Настройка форматов логов
    basic_formatter = logging.Formatter(get_log_format())
    detailed_formatter = logging.Formatter(get_log_format(detailed=True))
    error_formatter = logging.Formatter('%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s\n%(exc_info)s')
    
    # Основной файл логов (по размеру)
    main_log = os.path.join(log_directory, 'autoau.log')
    main_handler = get_file_handler(main_log, max_bytes=5*1024*1024, backup_count=5)
    main_handler.setFormatter(basic_formatter)
    logger.addHandler(main_handler)
    
    # Файл логов ошибок (по времени)
    error_log = os.path.join(log_directory, 'error.log')
    error_handler = get_timed_file_handler(error_log, when='midnight', backup_count=14)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(error_formatter)
    logger.addHandler(error_handler)
    
    # Файл отладочных логов для разработки
    debug_log = os.path.join(log_directory, 'debug.log')
    debug_handler = get_file_handler(debug_log, max_bytes=10*1024*1024, backup_count=3)
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(detailed_formatter)
    logger.addHandler(debug_handler)
    
    # Логирование в консоль для интерактивного использования
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(basic_formatter)
        logger.addHandler(console_handler)
    
    return logger


def cleanup_old_logs(max_days=30, log_directory='logs'):
    """
    Очищает старые логи для экономии дискового пространства
    
    Args:
        max_days: максимальное количество дней хранения логов
        log_directory: директория с логами
    """
    if not os.path.exists(log_directory):
        return
        
    current_time = time.time()
    max_age = max_days * 86400  # переводим дни в секунды
    
    for root, dirs, files in os.walk(log_directory):
        for file in files:
            file_path = os.path.join(root, file)
            file_age = current_time - os.path.getmtime(file_path)
            
            if file_age > max_age:
                try:
                    os.remove(file_path)
                    print(f"Удален старый лог: {file_path}")
                except Exception as e:
                    print(f"Ошибка при удалении файла {file_path}: {e}")
