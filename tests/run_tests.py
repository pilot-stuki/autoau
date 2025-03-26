#!/usr/bin/env python3
import unittest
import sys
import os
import time
import argparse

# Добавляем родительский каталог в путь для импорта модулей
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Импорт тестовых модулей
from tests.test_resource_manager import TestResourceManager
from tests.test_session_service import TestSessionService
from tests.test_automation_service import TestAutomationService
from tests.test_error_service import TestErrorService


def run_tests(verbosity=2, failfast=False, test_names=None, pattern=None):
    """
    Запускает тесты с указанными параметрами
    
    Args:
        verbosity: Уровень детализации вывода (1-3)
        failfast: Прекращать выполнение после первой ошибки
        test_names: Список имен тестов для запуска
        pattern: Шаблон имен тестов для запуска
    """
    # Создаем загрузчик тестов
    loader = unittest.TestLoader()
    
    # Настраиваем дополнительные опции загрузчика
    if pattern:
        loader.testNamePatterns = [pattern]
    
    # Загружаем тесты
    if test_names:
        suite = unittest.TestSuite()
        for test_name in test_names:
            suite.addTests(loader.loadTestsFromName(test_name))
    else:
        # Загружаем все тесты из каталога
        start_dir = os.path.dirname(os.path.abspath(__file__))
        suite = loader.discover(start_dir, pattern='test_*.py')
    
    # Запускаем тесты
    runner = unittest.TextTestRunner(verbosity=verbosity, failfast=failfast)
    start_time = time.time()
    result = runner.run(suite)
    end_time = time.time()
    
    # Выводим итоговую статистику
    print("\n" + "=" * 70)
    print(f"Запущено тестов: {result.testsRun}")
    print(f"Успешно: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Ошибок: {len(result.errors)}")
    print(f"Неудач: {len(result.failures)}")
    print(f"Время выполнения: {end_time - start_time:.2f} сек.")
    print("=" * 70)
    
    # Возвращаем код завершения
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    # Парсим аргументы командной строки
    parser = argparse.ArgumentParser(description='Запуск тестов для AutoAU')
    parser.add_argument('-v', '--verbosity', type=int, default=2, choices=[1, 2, 3],
                      help='Уровень детализации вывода (1-3)')
    parser.add_argument('-f', '--failfast', action='store_true',
                      help='Прекращать выполнение после первой ошибки')
    parser.add_argument('-p', '--pattern', type=str,
                      help='Шаблон имен тестов для запуска')
    parser.add_argument('test_names', nargs='*',
                      help='Имена тестов для запуска (например, tests.test_resource_manager.TestResourceManager.test_singleton_pattern)')
    
    args = parser.parse_args()
    
    # Запускаем тесты
    sys.exit(run_tests(
        verbosity=args.verbosity,
        failfast=args.failfast,
        test_names=args.test_names,
        pattern=args.pattern
    )) 