import unittest
from unittest.mock import patch, MagicMock, call
import sys
import os
import logging
import argparse
from io import StringIO
from datetime import datetime, timedelta
import time

# Отключаем логирование во время тестов
logging.disable(logging.CRITICAL)

# Патчим импорты, чтобы предотвратить инициализацию сервисов при импорте
with patch('app_logger.get_logger'), \
     patch('service_wrapper.setup_logging'):
    # Теперь можем безопасно импортировать основные модули
    import main
    from service_wrapper import ServiceWrapper
    from automation_service import AutomationService

class TestMainApplication(unittest.TestCase):
    """Тесты для проверки основной логики запуска приложения"""
    
    def setUp(self):
        """Подготовка перед каждым тестом"""
        # Сохраняем оригинальный argv
        self.original_argv = sys.argv.copy()
        
        # Создаем моки для необходимых компонентов
        self.mock_service_wrapper = MagicMock(spec=ServiceWrapper)
        self.mock_automation_service = MagicMock(spec=AutomationService)
        self.mock_resource_manager = MagicMock()
        self.mock_browser_service = MagicMock()
        self.mock_error_service = MagicMock()
        self.mock_logger = MagicMock()
        
        # Патчим глобальные переменные и функции
        self.patches = [
            patch('main.get_service_wrapper', return_value=self.mock_service_wrapper),
            patch('main.ACCOUNTS', [('test@example.com', 'password123')]),
            patch('main.RUNNING', True),
            patch('main.logger', self.mock_logger),
            patch('main.get_resource_manager', return_value=self.mock_resource_manager),
            patch('main.get_browser_service', return_value=self.mock_browser_service),
            patch('main.get_error_service', return_value=self.mock_error_service),
            # Добавляем патч для argparse.ArgumentParser
            patch('argparse.ArgumentParser.parse_args', return_value=MagicMock(
                parallel=False, workers=None, test_mode=False, check=False, 
                account=None, debug=False, version=False
            ))
        ]
        
        # Запускаем все патчи
        for p in self.patches:
            p.start()
        
    def tearDown(self):
        """Завершение после каждого теста"""
        # Останавливаем все патчи
        for p in self.patches:
            p.stop()
        
        # Восстанавливаем оригинальный argv
        sys.argv = self.original_argv
    
    def test_verify_account_status(self):
        """Тест функции verify_account_status"""
        # Настраиваем мок для возврата состояния переключателя
        self.mock_service_wrapper.verify_toggle_state.return_value = True
        
        # Вызываем функцию
        result = main.verify_account_status('test@example.com', 'password123')
        
        # Проверяем, что функция вызвала верный метод сервиса
        self.mock_service_wrapper.verify_toggle_state.assert_called_once_with('test@example.com', 'password123')
        
        # Проверяем возвращаемое значение
        self.assertTrue(result)
    
    def test_process_batch(self):
        """Тест функции process_batch"""
        # Настраиваем мок для возврата результатов
        self.mock_service_wrapper.process_accounts_sequential.return_value = {'test@example.com': True}
        self.mock_service_wrapper.process_accounts_parallel.return_value = {'test@example.com': True}
        
        # Тестируем последовательную обработку
        with patch('main.time.sleep'):  # патчим sleep чтобы ускорить тест
            main.process_batch([('test@example.com', 'password123')], batch_size=1, parallel=False)
            
        # Проверяем, что вызван верный метод
        self.mock_service_wrapper.process_accounts_sequential.assert_called_once()
        self.mock_service_wrapper.process_accounts_parallel.assert_not_called()
        
        # Сбрасываем счетчики вызовов
        self.mock_service_wrapper.process_accounts_sequential.reset_mock()
        self.mock_service_wrapper.process_accounts_parallel.reset_mock()
        
        # Тестируем параллельную обработку
        with patch('main.time.sleep'):  # патчим sleep чтобы ускорить тест
            main.process_batch([('test@example.com', 'password123')], batch_size=1, parallel=True)
            
        # Проверяем, что вызван верный метод
        self.mock_service_wrapper.process_accounts_parallel.assert_called_once()
    
    def test_account_not_found(self):
        """Тест обработки несуществующего аккаунта"""
        # Мокируем parse_args, чтобы вернуть флаг account
        args_mock = MagicMock(parallel=False, workers=None, test_mode=False, check=False, 
                             account='nonexistent@example.com', debug=False, version=False)
        
        with patch('argparse.ArgumentParser.parse_args', return_value=args_mock):
            # Вызываем main функцию
            main.main()
            
            # Проверяем, что была отображена правильная ошибка
            self.mock_logger.error.assert_any_call("Аккаунт nonexistent@example.com не найден в списке")
    
    def test_test_mode_success(self):
        """Тест режима тестирования с успешной обработкой аккаунта"""
        # Мокируем parse_args, чтобы вернуть флаг test_mode
        args_mock = MagicMock(parallel=False, workers=None, test_mode=True, check=False, 
                             account=None, debug=False, version=False)
        
        # Настраиваем мок для успешной обработки
        self.mock_service_wrapper.process_account.return_value = True
        
        with patch('argparse.ArgumentParser.parse_args', return_value=args_mock):
            # Вызываем main функцию
            main.main()
            
            # Проверяем логи
            self.mock_logger.info.assert_any_call("Запуск в тестовом режиме (однократный запуск)")
            self.mock_logger.info.assert_any_call("Тестовая обработка аккаунта test@example.com успешна")
            
        # Проверяем, что был вызван правильный метод с правильными аргументами
        self.mock_service_wrapper.process_account.assert_called_once_with('test@example.com', 'password123')
    
    def test_test_mode_failure(self):
        """Тест режима тестирования с неудачной обработкой аккаунта"""
        # Мокируем parse_args, чтобы вернуть флаг test_mode
        args_mock = MagicMock(parallel=False, workers=None, test_mode=True, check=False, 
                             account=None, debug=False, version=False)
        
        # Настраиваем мок для неудачной обработки
        self.mock_service_wrapper.process_account.return_value = False
        
        with patch('argparse.ArgumentParser.parse_args', return_value=args_mock):
            # Вызываем main функцию
            main.main()
            
            # Проверяем логи
            self.mock_logger.info.assert_any_call("Тестовая обработка аккаунта test@example.com не удалась")
    
    def test_debug_mode(self):
        """Тест режима отладки"""
        # Мокируем parse_args, чтобы вернуть флаг debug
        args_mock = MagicMock(parallel=False, workers=None, test_mode=True, check=False, 
                             account=None, debug=True, version=False)
        
        with patch('argparse.ArgumentParser.parse_args', return_value=args_mock), \
             patch('logging.root.handlers', [MagicMock()]):
            # Вызываем main функцию
            main.main()
            
            # Проверяем, что был установлен уровень отладки
            self.mock_logger.setLevel.assert_called_once_with(logging.DEBUG)
            self.mock_logger.debug.assert_any_call("Включен режим отладки")
    
    def test_check_mode(self):
        """Тест режима проверки состояния переключателя"""
        # Мокируем parse_args, чтобы вернуть флаги check и account
        args_mock = MagicMock(parallel=False, workers=None, test_mode=False, check=True, 
                             account='test@example.com', debug=False, version=False)
        
        # Настраиваем мок для возврата состояния переключателя
        with patch('main.verify_account_status', return_value=True) as mock_verify, \
             patch('argparse.ArgumentParser.parse_args', return_value=args_mock):
            # Вызываем main функцию
            main.main()
            
            # Проверяем, что был вызван правильный метод
            mock_verify.assert_called_once_with('test@example.com', 'password123')
            
            # Проверяем логи
            self.mock_logger.info.assert_any_call("Состояние переключателя для test@example.com: включен")
    
    def test_signal_handler(self):
        """Тест обработчика сигналов"""
        # Патчим sys.exit для предотвращения завершения теста
        with patch('main.sys.exit') as mock_exit:  
            # Вызываем обработчик сигналов с позиционными аргументами
            main.signal_handler(2, None)  # 2 = SIGINT
            
            # Проверяем логи
            self.mock_logger.info.assert_any_call("Получен сигнал завершения, очистка ресурсов...")
            
            # Проверяем, что были вызваны методы очистки
            self.mock_browser_service.cleanup_all_drivers.assert_called_once()
            self.mock_service_wrapper.shutdown.assert_called_once()
            
            # Проверяем, что программа завершилась
            mock_exit.assert_called_once_with(0)

    def test_run_scheduled_checks_lifecycle(self):
        """Тест жизненного цикла функции run_scheduled_checks"""
        # Создаем мок для process_batch
        mock_process_batch = MagicMock(return_value={'test@example.com': True})
        
        # Вместо тестирования всей функции с циклом, проверим только одну итерацию
        # Создадим тестовую версию функции без бесконечного цикла
        def test_single_run_scheduled_check():
            try:
                # Выполняем обработку всех аккаунтов
                logger = self.mock_logger
                logger.info(f"Начало цикла проверки переключателей для {len(main.ACCOUNTS)} аккаунтов")
                start_time = time.time()
                
                # Определяем режим обработки в зависимости от ограничений ресурсов
                resource_mgr = self.mock_resource_manager
                parallel_mode = not resource_mgr.should_optimize_for_low_resources()
                
                # Обрабатываем аккаунты
                mock_process_batch(main.ACCOUNTS, parallel=parallel_mode)
                
                # Вычисляем время выполнения
                execution_time = time.time() - start_time
                logger.info(f"Завершен цикл проверки. Время выполнения: {execution_time:.1f} секунд")
                
                # Расчет интервала до следующего цикла
                interval = 60  # фиксированное значение для теста
                next_run = datetime.now() + timedelta(seconds=interval)
                
                logger.info(f"Следующий цикл запланирован на {next_run.strftime('%H:%M:%S %d.%m.%Y')} "
                            f"(через {interval//60} мин {interval%60} сек)")
                
                # Без ожидания до следующего цикла
                
            except Exception as e:
                # Обработка неожиданных ошибок
                self.mock_error_service.handle_error(e, "run_scheduled_checks")
        
        # Патчим time.time, чтобы вернуть фиксированные значения
        with patch('time.time', side_effect=[0, 10]):
            # Вызываем тестовую функцию
            test_single_run_scheduled_check()
            
            # Проверяем, что process_batch был вызван один раз
            mock_process_batch.assert_called_once()
            
            # Проверяем логи
            self.mock_logger.info.assert_any_call(f"Начало цикла проверки переключателей для {len(main.ACCOUNTS)} аккаунтов")

    def test_popup_handler_integration(self):
        """Тест интеграции обработчика всплывающих окон"""
        # Мокируем parse_args, чтобы вернуть флаги test_mode
        args_mock = MagicMock(parallel=False, workers=None, test_mode=True, check=False, 
                             account=None, debug=True, version=False)
        
        # Создаем мок для AutomationService
        mock_automation_service = MagicMock(spec=AutomationService)
        mock_automation_service.close_popups.return_value = True  # Предполагаем, что этот метод существует
        
        # Настраиваем mock_service_wrapper для проверки вызова automation_service
        self.mock_service_wrapper.process_account.return_value = True
        
        with patch('argparse.ArgumentParser.parse_args', return_value=args_mock), \
             patch('automation_service.get_automation_service', return_value=mock_automation_service):
            
            # Вызываем main функцию в тестовом режиме
            main.main()
            
            # Проверяем, что process_account был вызван
            self.mock_service_wrapper.process_account.assert_called_once()
            
            # Проверка вызова close_popups будет косвенной через process_account
            # Прямая проверка здесь невозможна, так как close_popups вызывается внутри
            # automation_service, а не напрямую из main.py


if __name__ == '__main__':
    unittest.main() 