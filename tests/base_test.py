import os
import sys
import unittest
import logging
from unittest.mock import patch, MagicMock

# Добавляем родительский каталог в путь для импорта модулей
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Настройка логирования для тестов
logging.basicConfig(level=logging.ERROR)


class BaseTestCase(unittest.TestCase):
    """Базовый класс для всех тестов приложения AutoAU"""
    
    @classmethod
    def setUpClass(cls):
        """Выполняется один раз перед всеми тестами класса"""
        # Отключаем логирование в файл для тестов
        cls.logging_patcher = patch('app_logger.get_logger')
        mock_logger = cls.logging_patcher.start()
        mock_logger.return_value = logging.getLogger('test')
        
        # Создаем временную директорию для тестовых данных
        cls.test_dir = os.path.join(os.path.dirname(__file__), 'test_data')
        os.makedirs(cls.test_dir, exist_ok=True)
        
    @classmethod
    def tearDownClass(cls):
        """Выполняется один раз после всех тестов класса"""
        # Восстанавливаем логирование
        cls.logging_patcher.stop()
        
        # Очищаем временную директорию (при необходимости)
        # Это опционально и зависит от того, нужно ли сохранять тестовые данные
        
    def setUp(self):
        """Выполняется перед каждым тестом"""
        # Сбрасываем каталог с текущей директории на директорию проекта
        os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        
    def tearDown(self):
        """Выполняется после каждого теста"""
        pass
        
    def create_mock_driver(self):
        """Создает мок-объект WebDriver для тестирования без реального браузера"""
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/dashboard"
        mock_driver.page_source = "<html><body>Test Page</body></html>"
        
        # Настройка метода find_element
        mock_element = MagicMock()
        mock_element.is_selected.return_value = True
        mock_element.is_displayed.return_value = True
        mock_element.is_enabled.return_value = True
        mock_driver.find_element.return_value = mock_element
        
        # Настройка get_cookies
        mock_driver.get_cookies.return_value = [
            {'name': 'session_id', 'value': 'test_session', 'domain': 'example.com'}
        ]
        
        return mock_driver
    
    def create_test_user(self):
        """Создает тестового пользователя"""
        return ('test@example.com', 'password123')
        
    def assertFileExists(self, file_path, msg=None):
        """Проверяет существование файла"""
        if not os.path.exists(file_path):
            msg = self._formatMessage(msg, f"Файл не существует: {file_path}")
            raise self.failureException(msg)
            
    def assertDirectoryExists(self, dir_path, msg=None):
        """Проверяет существование директории"""
        if not os.path.isdir(dir_path):
            msg = self._formatMessage(msg, f"Директория не существует: {dir_path}")
            raise self.failureException(msg) 