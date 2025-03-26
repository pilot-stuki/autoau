import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# Добавляем путь к корневому каталогу проекта
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from diagnostics import log_memory_usage, log_chrome_processes

class TestDiagnostics(unittest.TestCase):
    
    @patch('psutil.virtual_memory')
    def test_log_memory_usage(self, mock_virtual_memory):
        # Настраиваем мок для psutil.virtual_memory
        mock_memory = MagicMock()
        mock_memory.percent = 45.5
        mock_memory.available = 4 * 1024 * 1024 * 1024  # 4 GB
        mock_memory.total = 8 * 1024 * 1024 * 1024  # 8 GB
        mock_virtual_memory.return_value = mock_memory
        
        # Вызываем тестируемую функцию
        result = log_memory_usage()
        
        # Проверяем, что функция возвращает правильную строку с информацией о памяти
        self.assertIn("45.5%", result)
        self.assertIn("4096.0MB", result)
    
    @patch('psutil.process_iter')
    def test_log_chrome_processes(self, mock_process_iter):
        # Настраиваем мок для psutil.process_iter
        mock_chrome1 = MagicMock()
        mock_chrome1.name.return_value = 'chrome'
        mock_chrome1.pid = 12345
        mock_chrome1.memory_info.return_value.rss = 100 * 1024 * 1024  # 100 MB
        
        mock_chrome2 = MagicMock()
        mock_chrome2.name.return_value = 'chromedriver'
        mock_chrome2.pid = 67890
        mock_chrome2.memory_info.return_value.rss = 50 * 1024 * 1024  # 50 MB
        
        mock_process_iter.return_value = [mock_chrome1, mock_chrome2]
        
        # Вызываем тестируемую функцию
        result = log_chrome_processes()
        
        # Проверяем, что функция возвращает правильную строку с информацией о процессах Chrome
        self.assertIn("Chrome processes: 2", result)
        self.assertIn("12345", result)
        self.assertIn("67890", result)
    
    @patch('psutil.process_iter')
    def test_log_chrome_processes_empty(self, mock_process_iter):
        # Проверяем случай, когда нет процессов Chrome
        mock_process_iter.return_value = []
        
        # Вызываем тестируемую функцию
        result = log_chrome_processes()
        
        # Проверяем, что функция корректно обрабатывает случай без процессов
        self.assertIn("Chrome processes: 0", result)

if __name__ == '__main__':
    unittest.main() 