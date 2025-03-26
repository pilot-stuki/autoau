import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# Добавляем путь к корневому каталогу проекта
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from browser_service import BrowserService

class TestBrowserService(unittest.TestCase):
    
    def setUp(self):
        # Мокируем необходимые зависимости
        self.resource_mgr_patcher = patch('browser_service.get_resource_manager')
        self.mock_resource_mgr = self.resource_mgr_patcher.start()
        
        # Настраиваем моки
        mock_resource_manager = MagicMock()
        mock_resource_manager.should_optimize_for_low_resources.return_value = False
        mock_resource_manager.is_running_in_github_codespace.return_value = False
        self.mock_resource_mgr.return_value = mock_resource_manager
        
        # Отключаем реальные вызовы webdriver
        self.webdriver_patcher = patch('browser_service.webdriver.Chrome')
        self.mock_webdriver = self.webdriver_patcher.start()
        
        # Создаем экземпляр сервиса для тестирования
        self.browser_service = BrowserService()
        
        # Мокируем методы, которые нам не нужно реально вызывать
        self.browser_service.create_driver = MagicMock()
        self.browser_service.create_undetected_driver = MagicMock()
        self.browser_service.check_network_connectivity = MagicMock(return_value=True)
        self.browser_service.cleanup_unused_drivers = MagicMock()
        self.browser_service.cleanup_all_drivers = MagicMock()
    
    def tearDown(self):
        # Останавливаем патчи
        self.resource_mgr_patcher.stop()
        self.webdriver_patcher.stop()
    
    def test_create_driver_with_fallback_uses_regular_driver_first(self):
        # Настраиваем мок create_driver для возврата успешного результата
        mock_driver = MagicMock()
        self.browser_service.create_driver.return_value = mock_driver
        
        # Вызываем тестируемый метод
        driver, is_undetected = self.browser_service.create_driver_with_fallback(
            headless=True, 
            incognito=True
        )
        
        # Проверяем, что create_driver был вызван с правильными параметрами
        self.browser_service.create_driver.assert_called_once_with(
            headless=True, 
            incognito=True, 
            implicit_wait=10
        )
        
        # Проверяем, что undetected_chromedriver не использовался
        self.browser_service.create_undetected_driver.assert_not_called()
        
        # Проверяем возвращаемые значения
        self.assertEqual(driver, mock_driver)
        self.assertFalse(is_undetected)
    
    def test_create_driver_with_fallback_uses_undetected_when_regular_fails(self):
        # Настраиваем create_driver, чтобы он выбрасывал исключение с сообщением о боте
        self.browser_service.create_driver.side_effect = Exception("Detected automated browser")
        
        # Настраиваем create_undetected_driver для возврата успешного результата
        mock_undetected_driver = MagicMock()
        self.browser_service.create_undetected_driver.return_value = mock_undetected_driver
        
        # Вызываем тестируемый метод
        driver, is_undetected = self.browser_service.create_driver_with_fallback(
            headless=True, 
            incognito=True
        )
        
        # Проверяем, что create_driver был вызван
        self.browser_service.create_driver.assert_called_once()
        
        # Проверяем, что undetected_chromedriver был вызван
        self.browser_service.create_undetected_driver.assert_called_once()
        
        # Проверяем возвращаемые значения
        self.assertEqual(driver, mock_undetected_driver)
        self.assertTrue(is_undetected)
    
    def test_create_driver_with_fallback_raises_exception_when_both_fail(self):
        # Настраиваем create_driver, чтобы он выбрасывал исключение, не связанное с ботом
        self.browser_service.create_driver.side_effect = Exception("Some other error")
        
        # Вызываем тестируемый метод и ожидаем исключение
        with self.assertRaises(Exception):
            self.browser_service.create_driver_with_fallback(
                headless=True, 
                incognito=True
            )
        
        # Проверяем, что create_driver был вызван
        self.browser_service.create_driver.assert_called_once()
        
        # Проверяем, что undetected_chromedriver не был вызван, т.к. ошибка не связана с ботом
        self.browser_service.create_undetected_driver.assert_not_called()
    
    def test_create_driver_with_fallback_checks_network_connectivity(self):
        # Настраиваем check_network_connectivity для проверки ее вызова
        self.browser_service.check_network_connectivity.return_value = True
        
        # Настраиваем create_driver для возврата успешного результата
        mock_driver = MagicMock()
        self.browser_service.create_driver.return_value = mock_driver
        
        # Вызываем тестируемый метод
        self.browser_service.create_driver_with_fallback()
        
        # Проверяем, что check_network_connectivity был вызван
        self.browser_service.check_network_connectivity.assert_called_once()

if __name__ == '__main__':
    unittest.main() 