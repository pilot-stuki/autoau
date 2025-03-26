import os
import sys
import unittest
import json
import shutil
import tempfile
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime, timedelta
from freezegun import freeze_time
import logging
import threading
import time

# Импортируем базовый тестовый класс
from tests.base_test import BaseTestCase

# Импортируем тестируемый модуль
from session_service import SessionService, get_session_service, SessionServiceError

# Отключаем логирование во время тестов
logging.disable(logging.CRITICAL)


class TestSessionService(BaseTestCase):
    """Тесты для сервиса управления сессиями"""
    
    def setUp(self):
        """Настройка для каждого теста"""
        self.temp_session_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_sessions")
        
        # Создаем временную директорию для сессий, если она не существует
        if not os.path.exists(self.temp_session_dir):
            os.makedirs(self.temp_session_dir)
            
        # Патчим путь к сессиям для тестов
        self.session_dir_patcher = patch('session_service.SessionService._ensure_session_dir',
                                       return_value=self.temp_session_dir)
        self.mock_session_dir = self.session_dir_patcher.start()
        
        # Создаем патч для браузера
        self.browser_service_patcher = patch('session_service.get_browser_service')
        self.mock_browser_service = self.browser_service_patcher.start()
        self.mock_browser = MagicMock()
        self.mock_browser.close_driver = MagicMock()
        self.mock_browser.create_driver = MagicMock(return_value=self.create_mock_driver())
        self.mock_browser_service.return_value = self.mock_browser
        
    def tearDown(self):
        """Выполняется после каждого теста"""
        # Останавливаем патчи
        self.browser_service_patcher.stop()
        
        # Удаляем временную директорию
        shutil.rmtree(self.temp_session_dir)
        
        super().tearDown()
        
    def create_session_service(self):
        """Создает экземпляр SessionService для тестирования"""
        service = SessionService()
        # Устанавливаем тестовую директорию для сессий
        service.session_dir = self.temp_session_dir
        return service
        
    def create_test_session_data(self):
        """Создает тестовые данные сессии"""
        now = datetime.now().isoformat()
        return {
            'cookies': [
                {'name': 'session_id', 'value': 'test_session', 'domain': 'example.com'}
            ],
            'created_at': now,
            'last_used': now,
            'user_agent': 'Mozilla/5.0 (Test) Chrome/99.0'
        }
        
    def create_mock_driver(self):
        """Создает мок для веб-драйвера"""
        mock_driver = MagicMock()
        # Устанавливаем возвращаемое значение для get_cookies
        mock_driver.get_cookies.return_value = [
            {"name": "test_cookie1", "value": "test_value1", "domain": "example.com"},
            {"name": "test_cookie2", "value": "test_value2", "domain": "example.com"}
        ]
        return mock_driver
        
    def test_singleton_pattern(self):
        """Проверка, что SessionService реализует паттерн синглтон"""
        # Вызываем get_session_service дважды и проверяем, что это один и тот же объект
        service1 = get_session_service()
        service2 = get_session_service()
        self.assertIs(service1, service2, "Должен быть возвращен один и тот же экземпляр")
        
    def test_session_directory_creation(self):
        """Проверка создания директории для сессий"""
        # Создаем тестовую директорию
        test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_test_sessions")
        
        # Убедимся, что директория не существует
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
        
        try:
            # Патчим _ensure_session_dir, чтобы возвращать и создавать нашу тестовую директорию
            original_ensure_dir = SessionService._ensure_session_dir
            
            def mocked_ensure_dir(self):
                if not os.path.exists(test_dir):
                    os.makedirs(test_dir, exist_ok=True)
                return test_dir
            
            # Подменяем метод и создаем сервис
            SessionService._ensure_session_dir = mocked_ensure_dir
            service = SessionService()
            
            # Проверяем, что директория была создана
            self.assertTrue(os.path.exists(test_dir))
            self.assertTrue(os.path.isdir(test_dir))
        finally:
            # Восстанавливаем оригинальный метод
            SessionService._ensure_session_dir = original_ensure_dir
            
            # Удаляем тестовую директорию
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
        
    def test_save_session(self):
        """Проверка сохранения сессии"""
        service = self.create_session_service()
        email = "test@example.com"
        mock_driver = self.create_mock_driver()
        
        # Патчим _save_session_to_file, чтобы избежать реальной записи файла
        with patch.object(service, '_save_session_to_file') as mock_save_file:
            # Сохраняем сессию
            result = service.save_session(email, mock_driver)
            
            # Проверяем, что сессия была сохранена в памяти
            self.assertIn(email, service.sessions)
            self.assertEqual(service.sessions[email]['cookies'], 
                           mock_driver.get_cookies.return_value)
            
            # Проверяем, что _save_session_to_file был вызван
            mock_save_file.assert_called_once_with(email, service.sessions[email])
            
            # Проверяем возвращаемое значение
            self.assertEqual(result, service.sessions[email])
        
    def test_get_session(self):
        """Проверка получения сессии"""
        service = self.create_session_service()
        email = "test@example.com"
        session_data = self.create_test_session_data()
        
        # Добавляем сессию в память
        with service.sessions_lock:
            service.sessions[email] = session_data
            
        # Получаем сессию
        result = service.get_session(email)
        
        # Проверяем результат
        self.assertEqual(result, session_data)
        
        # Проверяем для несуществующего email
        result = service.get_session("nonexistent@example.com")
        self.assertIsNone(result)
        
    def test_apply_session(self):
        """Проверка применения сессии к драйверу"""
        service = self.create_session_service()
        email = "test@example.com"
        session_data = self.create_test_session_data()
        
        # Сохраняем старое время last_used
        old_last_used = session_data['last_used']
        
        # Добавляем сессию в память
        with service.sessions_lock:
            service.sessions[email] = session_data.copy()  # Используем копию
            
        # Создаем mock-драйвер
        mock_driver = self.create_mock_driver()
        
        # Применяем сессию с фиксированным временем
        with freeze_time("2023-01-01 12:00:00"):
            # Применяем сессию
            result = service.apply_session(email, mock_driver)
        
        # Проверяем, что add_cookie был вызван для каждого cookie
        for cookie in session_data['cookies']:
            mock_driver.add_cookie.assert_any_call(cookie)
            
        # Проверяем, что last_used был обновлен - должен отличаться от старого значения
        self.assertNotEqual(service.sessions[email]['last_used'], old_last_used)
        
        # Проверяем результат
        self.assertTrue(result)
        
        # Проверяем для несуществующего email
        result = service.apply_session("nonexistent@example.com", mock_driver)
        self.assertFalse(result)
        
    def test_validate_session_data(self):
        """Проверка валидации данных сессии"""
        service = self.create_session_service()
        
        # Корректные данные
        valid_data = self.create_test_session_data()
        self.assertTrue(service._validate_session_data(valid_data))
        
        # Отсутствует обязательное поле
        invalid_data = valid_data.copy()
        del invalid_data['cookies']
        self.assertFalse(service._validate_session_data(invalid_data))
        
        # Неверный формат даты
        invalid_data = valid_data.copy()
        invalid_data['created_at'] = "not-a-date"
        self.assertFalse(service._validate_session_data(invalid_data))
        
        # Пустые cookies
        invalid_data = valid_data.copy()
        invalid_data['cookies'] = []
        self.assertFalse(service._validate_session_data(invalid_data))
        
        # Устаревшая сессия
        invalid_data = valid_data.copy()
        past_date = (datetime.now() - timedelta(hours=24)).isoformat()
        invalid_data['created_at'] = past_date
        service.max_session_age = timedelta(hours=12)  # устанавливаем меньший срок
        self.assertFalse(service._validate_session_data(invalid_data))
        
    def test_delete_session(self):
        """Проверка удаления сессии"""
        service = self.create_session_service()
        email = "test@example.com"
        session_data = self.create_test_session_data()
        
        # Добавляем сессию в память
        with service.sessions_lock:
            service.sessions[email] = session_data
            
        # Создаем файл сессии
        session_file_path = os.path.join(self.temp_session_dir, f"{email}.session")
        with open(session_file_path, 'w') as f:
            json.dump(session_data, f)
            
        # Удаляем сессию
        result = service.delete_session(email)
        
        # Проверяем, что сессия была удалена из памяти
        self.assertNotIn(email, service.sessions)
        
        # Проверяем, что файл сессии был удален
        self.assertFalse(os.path.exists(session_file_path))
        
        # Проверяем результат
        self.assertTrue(result)
        
        # Проверяем для несуществующего email
        result = service.delete_session("nonexistent@example.com")
        self.assertFalse(result)
        
    def test_cleanup_all_sessions(self):
        """Проверка очистки всех сессий"""
        service = self.create_session_service()
        
        # Добавляем несколько сессий в память
        emails = ["test1@example.com", "test2@example.com", "test3@example.com"]
        session_data = self.create_test_session_data()
        
        for email in emails:
            with service.sessions_lock:
                service.sessions[email] = session_data.copy()
                
            # Создаем файл сессии
            session_file_path = os.path.join(self.temp_session_dir, f"{email}.session")
            with open(session_file_path, 'w') as f:
                json.dump(session_data, f)
                
        # Очищаем все сессии
        count = service.cleanup_all_sessions()
        
        # Проверяем, что все сессии были удалены из памяти
        self.assertEqual(len(service.sessions), 0)
        
        # Проверяем, что все файлы сессий были удалены
        for email in emails:
            session_file_path = os.path.join(self.temp_session_dir, f"{email}.session")
            self.assertFalse(os.path.exists(session_file_path))
            
        # Проверяем возвращаемое значение
        self.assertEqual(count, len(emails))
        
    def test_check_session_validity(self):
        """Проверка проверки работоспособности сессии"""
        service = self.create_session_service()
        email = "test@example.com"
        session_data = self.create_test_session_data()
        
        # Добавляем сессию в память
        with service.sessions_lock:
            service.sessions[email] = session_data
            
        # Создаем mock-драйвер
        mock_driver = self.create_mock_driver()
        self.mock_browser.create_driver.return_value = mock_driver
        
        # Устанавливаем URL, который не содержит 'login'
        mock_driver.current_url = "https://example.com/dashboard"
        
        # Проверяем работоспособность сессии
        result = service.check_session_validity(email, "https://example.com/test")
        
        # Проверяем, что браузер был создан
        self.mock_browser.create_driver.assert_called_once()
        
        # Проверяем, что браузер был закрыт
        self.mock_browser.close_driver.assert_called_once_with(mock_driver)
        
        # Проверяем результат
        self.assertTrue(result)
        
        # Сбрасываем моки
        self.mock_browser.create_driver.reset_mock()
        self.mock_browser.close_driver.reset_mock()
        
        # Устанавливаем URL, который содержит 'login' (перенаправление на страницу входа)
        mock_driver = self.create_mock_driver()
        mock_driver.current_url = "https://example.com/login"
        self.mock_browser.create_driver.return_value = mock_driver
        
        # Проверяем работоспособность сессии
        result = service.check_session_validity(email, "https://example.com/test")
        
        # Проверяем результат
        self.assertFalse(result)
        
        # Проверяем для несуществующего email
        result = service.check_session_validity("nonexistent@example.com", "https://example.com/test")
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main() 