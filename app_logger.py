import logging
from logging.handlers import RotatingFileHandler


def get_log_format():
    return '%(asctime)s %(levelname)s %(message)s'


def get_file_handler():
    file_handler = RotatingFileHandler('logs/autoAustralia.log',
                                       maxBytes=1000000,
                                       backupCount=7)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(get_log_format()))

    return file_handler


def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Enable debug logging
    
    # Create formatters
    debug_formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    error_formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s\n%(exc_info)s')
    
    # Main log file handler
    file_handler = RotatingFileHandler('logs/autoAustralia.log',
                                     maxBytes=1000000,
                                     backupCount=7)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(debug_formatter)
    
    # Debug log file handler
    debug_handler = RotatingFileHandler('logs/debug.log',
                                      maxBytes=1000000,
                                      backupCount=3)
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(debug_formatter)
    
    # Error log file handler
    error_handler = RotatingFileHandler('logs/error.log',
                                      maxBytes=1000000,
                                      backupCount=3)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(error_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(debug_handler)
    logger.addHandler(error_handler)
    
    return logger
