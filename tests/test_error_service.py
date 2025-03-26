import os
import sys
import unittest
from unittest.mock import patch, MagicMock, call
import time
from datetime import datetime
import json
import logging
import threading
from freezegun import freeze_time

# Импортируем базовый тестовый класс
from tests.base_test import BaseTestCase

# Импортируем тестируемый модуль
from error_service import (
    ErrorService, 
    get_error_service, 
    ErrorScope, 
    ErrorSeverity
)

# Отключаем логирование во время тестов
logging.disable(logging.CRITICAL)

class TestErrorService(BaseTestCase):
    """Тесты для сервиса обработки ошибок"""
    
    def setUp(self):
        """Выполняется перед каждым тестом"""
        super().setUp()
        
    def test_singleton_pattern(self):
        """Проверка, что ErrorService реализует паттерн синглтон"""
        # Вызываем get_error_service дважды и проверяем, что это один и тот же объект
        service1 = get_error_service()
        service2 = get_error_service()
        self.assertIs(service1, service2, "Должен быть возвращен один и тот же экземпляр")
        
    def test_error_classification(self):
        """Проверка классификации ошибок"""
        service = ErrorService()
        
        # Проверка классификации ошибок сети
        network_error = ConnectionError("Failed to connect to server")
        scope, severity = service.classify_error(network_error)
        self.assertEqual(scope, ErrorScope.NETWORK)
        self.assertEqual(severity, ErrorSeverity.MEDIUM)
        
        # Проверка классификации ошибок браузера
        browser_error = Exception("WebDriverException: chrome driver crashed")
        scope, severity = service.classify_error(browser_error)
        self.assertEqual(scope, ErrorScope.BROWSER)
        self.assertEqual(severity, ErrorSeverity.HIGH)
        
        # Проверка классификации ошибок сессии
        session_error = Exception("Session expired or invalid")
        scope, severity = service.classify_error(session_error)
        self.assertEqual(scope, ErrorScope.SESSION)
        self.assertEqual(severity, ErrorSeverity.MEDIUM)
        
        # Проверка классификации ошибок авторизации
        auth_error = Exception("Invalid login credentials")
        scope, severity = service.classify_error(auth_error)
        self.assertEqual(scope, ErrorScope.AUTH)
        self.assertEqual(severity, ErrorSeverity.HIGH)
        
        # Проверка классификации ошибок взаимодействия
        interaction_error = Exception("ElementNotInteractableException: element not clickable")
        scope, severity = service.classify_error(interaction_error)
        self.assertEqual(scope, ErrorScope.INTERACTION)
        self.assertEqual(severity, ErrorSeverity.MEDIUM)
        
        # Проверка классификации ошибок ресурсов
        resource_error = Exception("Out of memory")
        scope, severity = service.classify_error(resource_error)
        self.assertEqual(scope, ErrorScope.RESOURCE)
        self.assertEqual(severity, ErrorSeverity.HIGH)
        
        # Проверка классификации системных ошибок
        system_error = OSError("File not found")
        scope, severity = service.classify_error(system_error)
        self.assertEqual(scope, ErrorScope.SYSTEM)
        self.assertEqual(severity, ErrorSeverity.HIGH)
        
        # Проверка классификации ошибок таймаута
        timeout_error = Exception("TimeoutException: loading took too long")
        scope, severity = service.classify_error(timeout_error)
        self.assertEqual(scope, ErrorScope.TIMEOUT)
        self.assertEqual(severity, ErrorSeverity.MEDIUM)
        
        # Проверка классификации неизвестных ошибок
        unknown_error = Exception("Some random error")
        scope, severity = service.classify_error(unknown_error)
        self.assertEqual(scope, ErrorScope.UNKNOWN)
        self.assertEqual(severity, ErrorSeverity.MEDIUM)
        
    def test_handle_error_without_retry(self):
        """Проверка обработки ошибки без повторной попытки"""
        service = ErrorService()
        
        # Создаем исключение
        error = ValueError("Test error")
        
        # Патчим _record_error чтобы отследить вызов
        with patch.object(service, '_record_error') as mock_record_error:
            # Вызываем handle_error без функции повторной попытки
            success, result = service.handle_error(error, "test_operation")
            
            # Проверяем, что _record_error был вызван
            mock_record_error.assert_called_once()
            
            # Проверяем результат
            self.assertFalse(success)
            self.assertIsNone(result)
            
    def test_handle_error_with_successful_retry(self):
        """Проверка обработки ошибки с успешной повторной попыткой"""
        service = ErrorService()
        
        # Создаем исключение
        error = ValueError("Test error")
        
        # Создаем функцию повторной попытки, которая возвращает успешный результат
        retry_result = "Success"
        retry_callback = MagicMock(return_value=retry_result)
        
        # Патчим _record_error и time.sleep
        with patch.object(service, '_record_error') as mock_record_error, \
             patch('time.sleep') as mock_sleep:
            # Вызываем handle_error с функцией повторной попытки
            success, result = service.handle_error(error, "test_operation", retry_callback)
            
            # Проверяем, что _record_error был вызван
            mock_record_error.assert_called_once()
            
            # Проверяем, что retry_callback был вызван
            retry_callback.assert_called_once()
            
            # Проверяем результат
            self.assertTrue(success)
            self.assertEqual(result, retry_result)
            
            # Проверяем, что time.sleep был вызван
            mock_sleep.assert_called_once()
            
    def test_handle_error_with_failed_retries(self):
        """Проверка обработки ошибки с неудачными повторными попытками"""
        service = ErrorService()
        
        # Создаем исключение
        error = ValueError("Test error")
        
        # Получаем политику обработки для UNKNOWN
        policy = service.error_policies[ErrorScope.UNKNOWN]
        max_retries = policy['max_retries']
        
        # Создаем функцию повторной попытки, которая всегда вызывает исключение
        retry_exception = ValueError("Retry failed")
        retry_callback = MagicMock(side_effect=retry_exception)
        
        # Патчим _record_error, classify_error и time.sleep
        with patch.object(service, '_record_error') as mock_record_error, \
             patch.object(service, 'classify_error', return_value=(ErrorScope.UNKNOWN, ErrorSeverity.MEDIUM)) as mock_classify, \
             patch('time.sleep') as mock_sleep:
            # Вызываем handle_error с функцией повторной попытки
            success, result = service.handle_error(error, "test_operation", retry_callback)
            
            # Проверяем, что _record_error был вызван для исходной ошибки
            # и для каждой ошибки повторной попытки
            self.assertEqual(mock_record_error.call_count, max_retries + 1)
            
            # Проверяем, что retry_callback был вызван max_retries раз
            self.assertEqual(retry_callback.call_count, max_retries)
            
            # Проверяем, что time.sleep был вызван max_retries раз
            self.assertEqual(mock_sleep.call_count, max_retries)
            
            # Проверяем результат
            self.assertFalse(success)
            self.assertIsNone(result)
            
    def test_retry_operation_success(self):
        """Проверка retry_operation при успешном выполнении"""
        service = ErrorService()
        
        # Создаем операцию, которая успешно выполняется
        operation_result = "Success"
        operation = MagicMock(return_value=operation_result)
        
        # Вызываем retry_operation
        result = service.retry_operation(operation, "test_operation")
        
        # Проверяем, что операция была вызвана один раз
        operation.assert_called_once()
        
        # Проверяем результат
        self.assertEqual(result, operation_result)
        
    def test_retry_operation_with_error(self):
        """Проверка retry_operation при ошибке"""
        service = ErrorService()
        
        # Создаем операцию, которая вызывает исключение
        operation_error = ValueError("Operation failed")
        operation = MagicMock(side_effect=operation_error)
        
        # Патчим handle_error для возврата (False, None)
        with patch.object(service, 'handle_error', return_value=(False, None)) as mock_handle_error:
            # Вызываем retry_operation
            result = service.retry_operation(operation, "test_operation")
            
            # Проверяем, что операция была вызвана один раз
            operation.assert_called_once()
            
            # Проверяем, что handle_error был вызван с правильными аргументами
            mock_handle_error.assert_called_once()
            args, kwargs = mock_handle_error.call_args
            self.assertEqual(args[0], operation_error)
            self.assertEqual(args[1], "test_operation")
            
            # Проверяем результат
            self.assertIsNone(result)
            
    def test_record_error(self):
        """Проверка записи информации об ошибке"""
        service = ErrorService()
        
        # Параметры ошибки
        error_scope = ErrorScope.NETWORK
        error_severity = ErrorSeverity.MEDIUM
        exception = ValueError("Test error")
        operation_name = "test_operation"
        
        # Начальное состояние
        initial_count = service.error_counters[error_scope]
        initial_history_len = len(service.recent_errors)
        
        # Вызываем _record_error с фиксированным временем
        with freeze_time("2023-01-01 12:00:00"):
            service._record_error(error_scope, error_severity, exception, operation_name)
            
        # Проверяем, что счетчик был увеличен
        self.assertEqual(service.error_counters[error_scope], initial_count + 1)
        
        # Проверяем, что запись была добавлена в историю
        self.assertEqual(len(service.recent_errors), initial_history_len + 1)
        
        # Проверяем содержимое записи
        error_record = service.recent_errors[-1]
        self.assertEqual(error_record['scope'], error_scope)
        self.assertEqual(error_record['severity'], error_severity)
        self.assertEqual(error_record['operation'], operation_name)
        self.assertEqual(error_record['message'], str(exception))
        self.assertEqual(error_record['type'], type(exception).__name__)
        self.assertEqual(error_record['timestamp'], datetime(2023, 1, 1, 12, 0, 0))
        
    def test_count_recent_errors(self):
        """Проверка подсчета количества недавних ошибок"""
        service = ErrorService()
        
        # Создаем тестовые ошибки
        error_scope = ErrorScope.NETWORK
        error_severity = ErrorSeverity.MEDIUM
        exception = ValueError("Test error")
        
        # Очищаем историю ошибок
        service.recent_errors.clear()
        
        # Устанавливаем текущее время для тестов и добавляем ошибки
        with freeze_time("2023-01-01 12:00:00"):
            # Добавляем ошибку в текущее время
            service._record_error(error_scope, error_severity, exception)
        
        with freeze_time("2023-01-01 11:55:00"):  # 5 минут назад
            # Добавляем ошибку в пределах окна с другим типом
            service._record_error(ErrorScope.BROWSER, error_severity, exception)
        
        with freeze_time("2023-01-01 11:51:00"):  # 9 минут назад
            # Добавляем ошибку в пределах окна
            service._record_error(error_scope, error_severity, exception)
        
        # Возвращаем текущее время
        with freeze_time("2023-01-01 12:00:00"):
            # Подсчитываем ошибки за последние 10 минут
            from datetime import timedelta
            count = service._count_recent_errors(error_scope, timedelta(minutes=10))
            
            # Проверяем, что найдены только ошибки в пределах окна
            self.assertEqual(count, 2)  # 2 ошибки типа NETWORK за последние 10 минут
            
    def test_get_error_statistics(self):
        """Проверка получения статистики ошибок"""
        service = ErrorService()
        
        # Очищаем историю ошибок
        service.recent_errors.clear()
        service.reset_error_counters()
        
        # Счетчики ошибок должны быть сброшены для теста
        for scope in ErrorScope:
            service.error_counters[scope] = 0
        
        # Добавляем тестовые ошибки с разными временными метками
        error_scope1 = ErrorScope.NETWORK
        error_scope2 = ErrorScope.BROWSER
        error_severity = ErrorSeverity.MEDIUM
        exception = ValueError("Test error")
        
        with freeze_time("2023-01-01 12:00:00"):
            # Текущее время для тестов
            # Добавляем несколько разных ошибок (увеличиваем счетчики)
            service._record_error(error_scope1, error_severity, exception)
            service._record_error(error_scope1, error_severity, exception)
            service._record_error(error_scope2, error_severity, exception)
            
            # Считаем количество ошибок, а не зависим от внутренних счетчиков
            # Получаем статистику
            stats = service.get_error_statistics()
            
            # Проверяем результат
            self.assertEqual(stats[ErrorScope.NETWORK.value], 2)  # 2 ошибки сети
            self.assertEqual(stats[ErrorScope.BROWSER.value], 1)  # 1 ошибка браузера
            
    def test_reset_error_counters(self):
        """Проверка сброса счетчиков ошибок"""
        service = ErrorService()
        
        # Устанавливаем счетчики
        service.error_counters[ErrorScope.NETWORK] = 5
        service.error_counters[ErrorScope.BROWSER] = 3
        
        # Сбрасываем счетчики
        service.reset_error_counters()
        
        # Проверяем, что все счетчики сброшены
        for scope in ErrorScope:
            self.assertEqual(service.error_counters[scope], 0)
            
    def test_clear_error_history(self):
        """Проверка очистки истории ошибок"""
        service = ErrorService()
        
        # Добавляем несколько ошибок
        service._record_error(ErrorScope.NETWORK, ErrorSeverity.MEDIUM, Exception())
        service._record_error(ErrorScope.BROWSER, ErrorSeverity.HIGH, Exception())
        
        # Проверяем, что история не пуста
        self.assertGreater(len(service.recent_errors), 0)
        
        # Очищаем историю
        service.clear_error_history()
        
        # Проверяем, что история пуста
        self.assertEqual(len(service.recent_errors), 0)


if __name__ == '__main__':
    unittest.main() 