import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import psutil

# Импортируем базовый тестовый класс
from tests.base_test import BaseTestCase

# Импортируем тестируемый модуль
from resource_manager import ResourceManager, get_resource_manager


class TestResourceManager(BaseTestCase):
    """Тесты для сервиса управления ресурсами"""
    
    def setUp(self):
        """Выполняется перед каждым тестом"""
        super().setUp()
        
        # Создаем патчи для psutil
        self.mock_virtual_memory = MagicMock()
        self.mock_virtual_memory.percent = 50  # 50% использования памяти
        self.mock_virtual_memory.available = 4 * 1024 * 1024 * 1024  # 4 ГБ доступной памяти
        
        self.psutil_vm_patcher = patch('psutil.virtual_memory', return_value=self.mock_virtual_memory)
        self.mock_psutil_vm = self.psutil_vm_patcher.start()
        
        self.psutil_cpu_patcher = patch('psutil.cpu_percent', return_value=30)  # 30% использования CPU
        self.mock_psutil_cpu = self.psutil_cpu_patcher.start()
        
        self.psutil_proc_patcher = patch('psutil.Process')
        self.mock_psutil_proc = self.psutil_proc_patcher.start()
        self.mock_process = MagicMock()
        self.mock_process.memory_percent.return_value = 10  # 10% использования памяти процессом
        self.mock_process.cpu_percent.return_value = 20  # 20% использования CPU процессом
        self.mock_psutil_proc.return_value = self.mock_process
        
    def tearDown(self):
        """Выполняется после каждого теста"""
        # Останавливаем патчи
        self.psutil_vm_patcher.stop()
        self.psutil_cpu_patcher.stop()
        self.psutil_proc_patcher.stop()
        super().tearDown()
        
    def test_singleton_pattern(self):
        """Проверка, что ResourceManager реализует паттерн синглтон"""
        # Вызываем get_resource_manager дважды и проверяем, что это один и тот же объект
        manager1 = get_resource_manager()
        manager2 = get_resource_manager()
        self.assertIs(manager1, manager2, "Должен быть возвращен один и тот же экземпляр")
        
    def test_memory_usage_detection(self):
        """Проверка обнаружения использования памяти"""
        # Создаем экземпляр ResourceManager напрямую для тестирования
        with patch('threading.Thread'):  # Патчим Thread, чтобы не запускать фоновый мониторинг
            manager = ResourceManager()
            
            # Проверяем нормальное использование памяти в разных сценариях
            with patch.object(manager, 'get_memory_usage', return_value=50):
                self.assertEqual(manager.get_memory_usage(), 50)
                self.assertFalse(manager.memory_usage_high())
                self.assertFalse(manager.memory_usage_critical())
                
            # Проверяем высокое использование памяти
            with patch.object(manager, 'get_memory_usage', return_value=80):
                self.assertTrue(manager.memory_usage_high())
                self.assertFalse(manager.memory_usage_critical())
                
            # Проверяем критическое использование памяти
            with patch.object(manager, 'get_memory_usage', return_value=90):
                self.assertTrue(manager.memory_usage_high())
                self.assertTrue(manager.memory_usage_critical())
        
    def test_cpu_usage_detection(self):
        """Проверка обнаружения использования CPU"""
        # Создаем экземпляр ResourceManager напрямую для тестирования
        with patch('threading.Thread'):  # Патчим Thread, чтобы не запускать фоновый мониторинг
            manager = ResourceManager()
            
            # Проверяем нормальное использование CPU
            with patch.object(manager, 'get_cpu_usage', return_value=30):
                self.assertEqual(manager.get_cpu_usage(), 30)
                self.assertFalse(manager.system_under_high_load())
                
            # Проверяем высокое использование CPU
            with patch.object(manager, 'get_cpu_usage', return_value=85):
                self.assertTrue(manager.system_under_high_load())
            
    def test_optimize_for_low_resources(self):
        """Проверка определения режима оптимизации для ограниченных ресурсов"""
        # Создаем экземпляр ResourceManager напрямую для тестирования
        with patch('threading.Thread'):  # Патчим Thread, чтобы не запускать фоновый мониторинг
            manager = ResourceManager()
            
            # Проверяем с нормальными ресурсами
            self.mock_virtual_memory.available = 4 * 1024 * 1024 * 1024  # 4 ГБ доступной памяти
            with patch('os.cpu_count', return_value=4):  # 4 ядра CPU
                self.assertFalse(manager.should_optimize_for_low_resources())
                
            # Проверяем с ограниченной памятью
            self.mock_virtual_memory.available = 1 * 1024 * 1024 * 1024  # 1 ГБ доступной памяти
            with patch('os.cpu_count', return_value=4):  # 4 ядра CPU
                self.assertTrue(manager.should_optimize_for_low_resources())
                
            # Проверяем с ограниченным CPU
            self.mock_virtual_memory.available = 4 * 1024 * 1024 * 1024  # 4 ГБ доступной памяти
            with patch('os.cpu_count', return_value=1):  # 1 ядро CPU
                self.assertTrue(manager.should_optimize_for_low_resources())
                
    def test_get_optimal_process_count(self):
        """Проверка расчета оптимального количества процессов"""
        # Создаем экземпляр ResourceManager напрямую для тестирования
        with patch('threading.Thread'):  # Патчим Thread, чтобы не запускать фоновый мониторинг
            # Патчим методы, чтобы они не влияли на наши тесты
            with patch.object(ResourceManager, 'is_running_in_github_codespace', return_value=False):
                with patch.object(ResourceManager, 'should_optimize_for_low_resources', return_value=False):
                    # Устанавливаем предсказуемое окружение теста
                    with patch('platform.system', return_value='Linux'):
                        with patch('os.cpu_count', return_value=4):  # 4 ядра CPU
                            manager = ResourceManager()
                            
                            # Подменяем max_processes для предсказуемого тестирования
                            manager.max_processes = 2
                            
                            # Тестируем нормальные условия
                            with patch.object(manager, 'memory_usage_high', return_value=False):
                                with patch.object(manager, 'memory_usage_critical', return_value=False):
                                    with patch.object(manager, 'system_under_high_load', return_value=False):
                                        # В нормальных условиях - используем max_processes
                                        self.assertEqual(manager.get_optimal_process_count(), 2)
                            
                            # Тестируем высокую нагрузку на память
                            with patch.object(manager, 'memory_usage_high', return_value=True):
                                with patch.object(manager, 'memory_usage_critical', return_value=False):
                                    # При высокой нагрузке - половина max_processes
                                    self.assertEqual(manager.get_optimal_process_count(), 1)
                            
                            # Тестируем критическую нагрузку на память
                            with patch.object(manager, 'memory_usage_critical', return_value=True):
                                # При критической нагрузке - всегда 1
                                self.assertEqual(manager.get_optimal_process_count(), 1)
                
    def test_force_garbage_collection(self):
        """Проверка принудительной сборки мусора"""
        # Создаем экземпляр ResourceManager напрямую для тестирования
        with patch('threading.Thread'):  # Патчим Thread, чтобы не запускать фоновый мониторинг
            manager = ResourceManager()
            
            # Патчим gc.collect
            with patch('gc.collect', return_value=100) as mock_gc_collect:
                # Вызываем метод и проверяем, что gc.collect был вызван
                result = manager.force_garbage_collection()
                mock_gc_collect.assert_called_once()
                self.assertEqual(result, 100)
                
    def test_github_codespace_detection(self):
        """Проверка определения GitHub Codespace"""
        # Создаем экземпляр ResourceManager напрямую для тестирования
        with patch('threading.Thread'):  # Патчим Thread, чтобы не запускать фоновый мониторинг
            manager = ResourceManager()
            
            # Проверяем с отсутствующей переменной окружения
            with patch.dict('os.environ', {}, clear=True):
                self.assertFalse(manager.is_running_in_github_codespace())
                
            # Проверяем с переменной CODESPACES='true'
            with patch.dict('os.environ', {'CODESPACES': 'true'}):
                self.assertTrue(manager.is_running_in_github_codespace())
                
            # Проверяем с переменной CODESPACES='1'
            with patch.dict('os.environ', {'CODESPACES': '1'}):
                self.assertTrue(manager.is_running_in_github_codespace())
                
            # Проверяем с переменной GITHUB_CODESPACE_TOKEN
            with patch.dict('os.environ', {'GITHUB_CODESPACE_TOKEN': 'some-token'}):
                self.assertTrue(manager.is_running_in_github_codespace())
                
            # Проверяем с переменной CODESPACE_NAME
            with patch.dict('os.environ', {'CODESPACE_NAME': 'some-name'}):
                self.assertTrue(manager.is_running_in_github_codespace())
                
            # Проверяем с CODESPACES='false'
            with patch.dict('os.environ', {'CODESPACES': 'false'}):
                self.assertFalse(manager.is_running_in_github_codespace())


if __name__ == '__main__':
    unittest.main() 