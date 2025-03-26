import os
import sys
import unittest
from unittest.mock import patch, MagicMock, call
import logging
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By

# Импортируем базовый тестовый класс
from tests.base_test import BaseTestCase

# Импортируем тестируемый модуль
from automation_service import (
    AutomationService, 
    get_automation_service, 
    AutomationServiceError,
    LoginError,
    ToggleError
)


class TestAutomationService(BaseTestCase):
    """Тесты для сервиса автоматизации"""
    
    def setUp(self):
        """Выполняется перед каждым тестом"""
        super().setUp()
        
        # Загружаем реальные учетные данные для тестов
        self.real_credentials = self.load_test_credentials()
        
        # Создаем моки для зависимостей
        self.mock_browser_service = MagicMock()
        self.mock_session_service = MagicMock()
        self.mock_error_service = MagicMock()
        self.mock_resource_mgr = MagicMock()
        
        # Создаем патчи для получения сервисов
        self.browser_service_patcher = patch('automation_service.get_browser_service', 
                                          return_value=self.mock_browser_service)
        self.session_service_patcher = patch('automation_service.get_session_service', 
                                           return_value=self.mock_session_service)
        self.error_service_patcher = patch('automation_service.get_error_service', 
                                         return_value=self.mock_error_service)
        self.resource_mgr_patcher = patch('automation_service.get_resource_manager', 
                                        return_value=self.mock_resource_mgr)
        
        # Запускаем патчи
        self.mock_get_browser_service = self.browser_service_patcher.start()
        self.mock_get_session_service = self.session_service_patcher.start()
        self.mock_get_error_service = self.error_service_patcher.start()
        self.mock_get_resource_mgr = self.resource_mgr_patcher.start()
        
        # Создаем моки для Selenium
        self.mock_by = patch('automation_service.By').start()
        self.mock_ec = patch('automation_service.EC').start()
        self.mock_wait = patch('automation_service.WebDriverWait').start()
        
        # Устанавливаем возвращаемые значения
        self.mock_driver = self.create_mock_driver()
        self.mock_browser_service.create_driver.return_value = self.mock_driver
        self.mock_browser_service.create_driver_with_fallback.return_value = (self.mock_driver, False)
        self.mock_browser_service.close_driver = MagicMock()
        
        # Настройка параметров ресурсов
        self.mock_resource_mgr.should_optimize_for_low_resources.return_value = False
        
        # Патч для Config
        self.mock_config = MagicMock()
        self.mock_config.get_target_url.return_value = "https://example.com/login"
        self.mock_config.get_visibility.return_value = False
        self.config_patcher = patch('automation_service.config', self.mock_config)
        self.config_patcher.start()
        
    def load_test_credentials(self):
        """Загружает реальные учетные данные из файла users.txt"""
        try:
            credentials = []
            with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'users.txt'), 'r') as file:
                for line in file:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        email = parts[0]
                        password = ' '.join(parts[1:])
                        credentials.append((email, password))
            
            # Используем первую пару учетных данных, если они есть
            return credentials[0] if credentials else ("test@example.com", "password123")
        except Exception as e:
            logging.warning(f"Не удалось загрузить учетные данные: {e}")
            return ("test@example.com", "password123")
    
    def tearDown(self):
        """Выполняется после каждого теста"""
        # Останавливаем патчи
        self.browser_service_patcher.stop()
        self.session_service_patcher.stop()
        self.error_service_patcher.stop()
        self.resource_mgr_patcher.stop()
        patch.stopall()  # останавливаем все остальные патчи
        
        super().tearDown()
        
    def test_singleton_pattern(self):
        """Проверка, что AutomationService реализует паттерн синглтон"""
        # Вызываем get_automation_service дважды и проверяем, что это один и тот же объект
        service1 = get_automation_service()
        service2 = get_automation_service()
        self.assertIs(service1, service2, "Должен быть возвращен один и тот же экземпляр")
        
    def test_init_with_resource_optimization(self):
        """Проверка инициализации с оптимизацией ресурсов"""
        # Устанавливаем, что система работает с ограниченными ресурсами
        self.mock_resource_mgr.should_optimize_for_low_resources.return_value = True
        
        # Создаем экземпляр сервиса
        service = AutomationService()
        
        # Проверяем, что был установлен режим headless
        self.mock_browser_service.set_headless_mode.assert_called_once_with(True)
        
    def test_login_with_session(self):
        """Проверка входа с использованием сессии"""
        # Настраиваем необходимые моки
        email, password = self.real_credentials
        
        # Мокируем current_url для указания успешного входа
        self.mock_driver.current_url = "https://example.com/dashboard"
        
        # Создаем моки для элементов формы
        mock_email_field = MagicMock()
        mock_password_field = MagicMock()
        mock_login_button = MagicMock()
        
        # Настраиваем wait.until для последовательного возврата элементов
        self.mock_wait.return_value.until.side_effect = [
            mock_email_field, mock_password_field, mock_login_button
        ]

        # Создаем экземпляр сервиса
        service = AutomationService()
        
        # Патчим необходимые методы
        with patch('automation_service.time.sleep'):
            with patch.object(service, 'close_popups', return_value=False):
                # Выполняем вход
                driver, is_new_login = service.login(email, password, driver=self.mock_driver)
        
        # Проверяем, что был загружен URL
        self.mock_driver.get.assert_called_with(self.mock_config.get_target_url())
        
        # Проверяем возвращаемые значения
        self.assertEqual(driver, self.mock_driver)
        self.assertTrue(is_new_login)  # Теперь всегда True, так как мы используем готовый драйвер
        
    def test_login_without_session(self):
        """Проверка входа без использования сессии"""
        # Мокируем current_url для указания успешного входа
        self.mock_driver.current_url = "https://example.com/dashboard"
        
        # Создаем моки для элементов формы
        mock_email_field = MagicMock()
        mock_password_field = MagicMock()
        mock_login_button = MagicMock()
        
        # Настраиваем wait.until для последовательного возврата элементов
        self.mock_wait.return_value.until.side_effect = [
            mock_email_field, mock_password_field, mock_login_button
        ]
        
        # Создаем сервис
        service = AutomationService()
        
        # Используем реальные учетные данные
        email, password = self.real_credentials
        
        # Патчим time.sleep для ускорения теста и close_popups
        with patch('automation_service.time.sleep'):
            with patch.object(service, 'close_popups', return_value=False):
                # Выполняем вход
                driver, is_new_login = service.login(email, password, driver=self.mock_driver)
        
        # Проверяем результат
        self.assertEqual(driver, self.mock_driver)
        self.assertTrue(is_new_login)
        
    def test_login_failure(self):
        """Проверка неудачного входа"""
        # Настраиваем current_url для имитации того, что мы остались на странице входа
        self.mock_driver.current_url = "https://example.com/login"
        
        # Создаем моки для элементов формы
        mock_email_field = MagicMock()
        mock_password_field = MagicMock()
        mock_login_button = MagicMock()
        
        # Настраиваем wait.until для последовательного возврата элементов
        self.mock_wait.return_value.until.side_effect = [
            mock_email_field, mock_password_field, mock_login_button
        ]
        
        # Создаем экземпляр сервиса
        service = AutomationService()
        
        # Выполняем вход с ожиданием исключения
        email, password = "test@example.com", "password123"
        
        # Патчим time.sleep и close_popups
        with patch('automation_service.time.sleep'):
            with patch.object(service, 'close_popups', return_value=False):
                with self.assertRaises(LoginError) as context:
                    service.login(email, password, driver=self.mock_driver)
                
        # Проверяем сообщение об ошибке
        error_message = str(context.exception)
        self.assertIn("URL остался", error_message, f"Неожиданное сообщение об ошибке: {error_message}")
        
    def test_check_and_set_toggle_when_off(self):
        """Проверка установки переключателя, когда он выключен"""
        # Создаем мок для контейнера available-now
        mock_container = MagicMock()
        
        # Настраиваем wait.until для возврата контейнера
        self.mock_wait.return_value.until.return_value = mock_container
        
        # Настраиваем driver.execute_script, чтобы сначала вернуть False (выключен), а потом True (включен)
        self.mock_driver.execute_script.side_effect = [False, True]
        
        # Создаем экземпляр сервиса и патчим time.sleep и BTN_OK поиск
        service = AutomationService()
        
        # Патчим поиск кнопки OK
        with patch.object(self.mock_wait.return_value, 'until', side_effect=[mock_container, None]):
            # Патчим time.sleep, чтобы не ждать
            with patch('automation_service.time.sleep'):
                # Проверяем и устанавливаем переключатель
                result = service.check_and_set_toggle(self.mock_driver)
        
        # Проверяем, что переключатель был кликнут один раз (это важно)
        self.assertEqual(mock_container.click.call_count, 1)
        
        # Проверяем возвращаемое значение (переключатель был изменен)
        self.assertTrue(result)
        
    def test_check_and_set_toggle_when_on(self):
        """Проверка установки переключателя, когда он уже включен"""
        # Создаем мок для контейнера available-now
        mock_container = MagicMock()
        
        # Настраиваем wait.until для возврата контейнера
        self.mock_wait.return_value.until.return_value = mock_container
        
        # Настраиваем driver.execute_script, чтобы вернуть True (переключатель уже включен)
        self.mock_driver.execute_script.return_value = True
        
        # Создаем экземпляр сервиса
        service = AutomationService()
        
        # Проверяем и устанавливаем переключатель
        with patch('automation_service.time.sleep'):
            result = service.check_and_set_toggle(self.mock_driver)
        
        # Проверяем, что переключатель НЕ был кликнут
        mock_container.click.assert_not_called()
        
        # Проверяем возвращаемое значение (переключатель не был изменен)
        self.assertFalse(result)
        
    def test_check_and_set_toggle_failure(self):
        """Проверка ошибки при установке переключателя"""
        # Создаем мок для WebDriverWait, который будет выбрасывать TimeoutException 
        # при каждом вызове until
        self.mock_wait.return_value.until.side_effect = TimeoutException("Элемент не найден")
        
        # Убедимся, что find_elements тоже не находит чекбоксов
        self.mock_driver.find_elements.return_value = []
        
        # Создаем сервис автоматизации
        service = AutomationService()
        service.max_toggle_retries = 1  # Уменьшаем до 1 для ускорения теста
        
        # Запускаем тест с ожиданием исключения
        with self.assertRaises(ToggleError):
            service.check_and_set_toggle(self.mock_driver)
        
    def test_handle_refresh_cycle(self):
        """Проверка цикла обновления переключателя"""
        # Создаем мок для login
        mock_login = MagicMock()
        mock_login.return_value = (self.mock_driver, True)
        
        # Создаем мок для retry_operation
        def mock_retry_side_effect(operation, *args, **kwargs):
            return operation()
            
        self.mock_error_service.retry_operation.side_effect = mock_retry_side_effect
        
        # Создаем экземпляр сервиса с патчем для login
        service = AutomationService()
        service.login = mock_login
        
        # Патчим check_and_set_toggle
        service.check_and_set_toggle = MagicMock(return_value=True)
        
        # Патчим time.sleep, чтобы не ждать
        with patch('automation_service.time.sleep'):
            # Выполняем цикл обновления переключателя с реальными учетными данными
            email, password = self.real_credentials
            result = service.handle_refresh_cycle(email, password, max_checks=3)
        
        # Проверяем, что login был вызван с правильными параметрами
        mock_login.assert_called_once_with(email, password)
        
        # Проверяем, что check_and_set_toggle был вызван нужное количество раз
        self.assertEqual(service.check_and_set_toggle.call_count, 3)
        
        # Проверяем, что драйвер был обновлен между проверками
        self.assertEqual(self.mock_driver.refresh.call_count, 2)  # 2 обновления для 3 проверок
        
        # Проверяем, что драйвер был закрыт
        self.mock_browser_service.close_driver.assert_called_once_with(self.mock_driver)
        
        # Проверяем возвращаемое значение
        self.assertTrue(result)
        
    def test_handle_refresh_cycle_login_failure(self):
        """Проверка цикла обновления переключателя при ошибке входа"""
        # Настраиваем retry_operation для возврата None (ошибка входа)
        self.mock_error_service.retry_operation.return_value = None
        
        # Создаем экземпляр сервиса
        service = AutomationService()
        
        # Используем реальные учетные данные
        email, password = self.real_credentials
        
        # Выполняем цикл обновления переключателя
        result = service.handle_refresh_cycle(email, password)
        
        # Проверяем, что retry_operation был вызван с правильным именем операции
        self.mock_error_service.retry_operation.assert_called_once()
        self.assertEqual(self.mock_error_service.retry_operation.call_args[0][1], "login")
        
        # Проверяем возвращаемое значение
        self.assertFalse(result)

    def test_check_and_set_toggle_with_different_selectors(self):
        """Проверка установки переключателя с использованием различных селекторов"""
        # Создаем мок для контейнера available-now
        mock_container = MagicMock()
        
        # Настраиваем wait.until, чтобы возвращать mock_container
        self.mock_wait.return_value.until.return_value = mock_container
        
        # Настраиваем driver.execute_script для имитации состояния переключателя
        self.mock_driver.execute_script.side_effect = [False, True]
        
        # Создаем экземпляр сервиса
        service = AutomationService()
        
        # Заменяем стандартный селектор на наш тестовый
        original_selector = service.toggle_selector
        service.toggle_selector = "div.test-selector input[name='test-toggle']"
        
        try:
            # Запускаем тест
            with patch('automation_service.time.sleep'):
                with patch.object(self.mock_wait.return_value, 'until', side_effect=[mock_container, None]):
                    result = service.check_and_set_toggle(self.mock_driver)
                    
            # Проверяем, что container был кликнут
            self.assertEqual(mock_container.click.call_count, 1)
            
            # Проверяем возвращаемое значение (переключатель был изменен)
            self.assertTrue(result)
            
        finally:
            # Восстанавливаем оригинальный селектор
            service.toggle_selector = original_selector


if __name__ == '__main__':
    unittest.main() 