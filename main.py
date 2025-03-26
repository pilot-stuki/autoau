import os
import time
import logging
import threading
import argparse
import signal
import sys
import random
from datetime import datetime, timedelta

# Импорт логгера
import app_logger

# Импорт обертки сервисов
from service_wrapper import get_service_wrapper

# Импорт сервисов
from resource_manager import get_resource_manager
from browser_service import get_browser_service
from error_service import get_error_service
from config import Config

# Глобальные переменные
RUNNING = True  # Флаг для контроля выполнения программы
VERSION = "2.0.0"  # Версия приложения

# Инициализация конфигурации
config = Config()

# Настройка логирования
if config.get_log_file():
    if not os.path.exists('logs'):
        os.makedirs('logs', exist_ok=True)
    logger = app_logger.get_logger(__name__)
else:
    logging.basicConfig(level=logging.INFO,
                      format=f'{app_logger.get_log_format()}')
    logger = logging.getLogger(__name__)

# Получение списка пользователей
ACCOUNTS = config.get_users()
TARGET_URL = config.get_target_url()

# Инициализация менеджера ресурсов
resource_mgr = get_resource_manager()


def signal_handler(sig, frame):
    """
    Обработчик сигналов для корректного завершения программы
    """
    global RUNNING
    logger.info("Получен сигнал завершения, очистка ресурсов...")
    RUNNING = False
    
    # Очистка ресурсов Chrome
    browser_service = get_browser_service()
    browser_service.cleanup_all_drivers()
    
    # Завершение работы обертки сервисов
    wrapper = get_service_wrapper()
    wrapper.shutdown()
    
    # Очистка старых логов
    app_logger.cleanup_old_logs(max_days=30)
    
    logger.info("Ресурсы очищены, завершение работы")
    sys.exit(0)

# Регистрация обработчиков сигналов
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def process_batch(accounts, batch_size=None, parallel=False):
    """
    Обрабатывает пакет аккаунтов
    
    Args:
        accounts: Список аккаунтов [(email, password), ...]
        batch_size: Размер пакета для обработки
        parallel: Использовать ли параллельную обработку
    """
    if not accounts:
        logger.warning("Пустой список аккаунтов для обработки")
        return
        
    # Определяем оптимальный размер пакета
    if batch_size is None:
        if resource_mgr.should_optimize_for_low_resources():
            # В режиме низких ресурсов обрабатываем по одному аккаунту
            batch_size = 1
        else:
            # В обычном режиме адаптируем размер пакета
            batch_size = min(
                resource_mgr.get_optimal_process_count() * 2,
                len(accounts)
            )
    
    # Получаем обертку сервисов        
    wrapper = get_service_wrapper()
    
    # Разбиваем аккаунты на пакеты
    for i in range(0, len(accounts), batch_size):
        # Проверка на сигнал завершения
        if not RUNNING:
            logger.info("Обнаружен сигнал завершения, прерывание обработки")
            break
            
        batch = accounts[i:i + batch_size]
        logger.info(f"Обработка пакета аккаунтов {i//batch_size + 1}/{(len(accounts) + batch_size - 1)//batch_size} "
                    f"(размер: {len(batch)})")
        
        # Обрабатываем пакет аккаунтов
        if parallel and not resource_mgr.should_optimize_for_low_resources():
            # Параллельная обработка
            results = wrapper.process_accounts_parallel(batch)
        else:
            # Последовательная обработка для экономии ресурсов
            results = wrapper.process_accounts_sequential(batch)
            
        # Логируем результаты
        success_count = sum(1 for success in results.values() if success)
        logger.info(f"Пакет обработан. Успешно: {success_count}/{len(batch)}")
        
        # Проверяем, нужно ли выполнить очистку после пакета
        if resource_mgr.memory_usage_high():
            logger.warning("Высокое использование памяти после обработки пакета. Запуск очистки.")
            browser_service = get_browser_service()
            browser_service.cleanup_unused_drivers()
            resource_mgr.force_garbage_collection()
            
        # Делаем паузу между пакетами для снижения нагрузки
        if i + batch_size < len(accounts) and RUNNING:
            # Адаптивный интервал в зависимости от нагрузки
            if resource_mgr.system_under_high_load():
                # Увеличиваем интервал при высокой нагрузке
                interval = random.uniform(15, 30)
                logger.info(f"Система под нагрузкой, увеличенный интервал между пакетами: {interval:.1f}с")
            else:
                interval = random.uniform(5, 10)
                
            logger.info(f"Пауза между пакетами: {interval:.1f} секунд")
            time.sleep(interval)


def run_scheduled_checks():
    """
    Запускает периодическую проверку переключателей для всех аккаунтов
    с адаптивным интервалом.
    """
    while RUNNING:
        try:
            # Выполняем обработку всех аккаунтов
            logger.info(f"Начало цикла проверки переключателей для {len(ACCOUNTS)} аккаунтов")
            start_time = time.time()
            
            # Определяем режим обработки в зависимости от ограничений ресурсов
            parallel_mode = not resource_mgr.should_optimize_for_low_resources()
            
            # Обрабатываем аккаунты
            process_batch(ACCOUNTS, parallel=parallel_mode)
            
            # Вычисляем время выполнения
            execution_time = time.time() - start_time
            logger.info(f"Завершен цикл проверки. Время выполнения: {execution_time:.1f} секунд")
            
            # Расчет интервала до следующего цикла
            interval = calculate_next_run_interval()
            next_run = datetime.now() + timedelta(seconds=interval)
            
            logger.info(f"Следующий цикл запланирован на {next_run.strftime('%H:%M:%S %d.%m.%Y')} "
                        f"(через {interval//60} мин {interval%60} сек)")
            
            # Ожидание до следующего цикла с проверкой сигнала завершения
            wait_with_check(interval)
            
        except Exception as e:
            # Обработка неожиданных ошибок
            error_service = get_error_service()
            error_service.handle_error(e, "run_scheduled_checks")
            
            # В случае ошибки делаем паузу перед следующей попыткой
            logger.error(f"Ошибка в цикле проверки: {e}. Пауза 60 секунд.")
            wait_with_check(60)


def wait_with_check(seconds):
    """
    Ожидание с проверкой флага RUNNING для возможности прерывания
    
    Args:
        seconds: Время ожидания в секундах
    """
    step = 1  # проверка каждую секунду
    for _ in range(int(seconds / step)):
        if not RUNNING:
            break
        time.sleep(step)


def calculate_next_run_interval():
    """
    Расчет интервала до следующего запуска с учетом нагрузки на систему
    
    Returns:
        int: Количество секунд до следующего запуска
    """
    # Базовый интервал от 30 до 90 минут
    base_minutes = random.randint(30, 90)
    
    # Добавление случайности
    seconds = random.randint(0, 59)
    
    # Общий интервал
    interval = base_minutes * 60 + seconds
    
    # Адаптация интервала в зависимости от нагрузки на ресурсы
    if resource_mgr.system_under_high_load():
        # Увеличиваем интервал при высокой нагрузке
        interval = int(interval * 1.5)
        logger.info(f"Система под высокой нагрузкой, интервал увеличен до {interval // 60} минут {interval % 60} секунд")
    elif resource_mgr.memory_usage_critical():
        # Максимально увеличиваем интервал при критическом использовании памяти
        interval = int(interval * 2)
        logger.warning(f"Критическое использование памяти, интервал увеличен до {interval // 60} минут {interval % 60} секунд")
    
    return interval


def verify_account_status(email, password):
    """
    Проверяет текущее состояние переключателя для одного аккаунта
    
    Args:
        email: Email пользователя
        password: Пароль пользователя
        
    Returns:
        bool: True если переключатель включен, False если выключен, None в случае ошибки
    """
    wrapper = get_service_wrapper()
    return wrapper.verify_toggle_state(email, password)


def main():
    """
    Основная функция приложения
    """
    # Настройка и парсинг аргументов командной строки
    parser = argparse.ArgumentParser(description='AutoAU - автоматическое управление переключателями на сайте')
    parser.add_argument('--parallel', action='store_true', help='Запустить в параллельном режиме')
    parser.add_argument('--workers', type=int, help='Количество рабочих процессов (только для параллельного режима)')
    parser.add_argument('--test-mode', action='store_true', help='Тестовый режим (одиночный запуск)')
    parser.add_argument('--check', action='store_true', help='Проверить состояние переключателя без изменения')
    parser.add_argument('--account', type=str, help='Обработать только указанный аккаунт (email)')
    parser.add_argument('--debug', action='store_true', help='Режим отладки')
    parser.add_argument('--version', action='store_true', help='Показать версию и выйти')
    
    args = parser.parse_args()
    
    # Вывод версии и выход
    if args.version:
        print(f"AutoAU версия {VERSION}")
        return
    
    # Настройка режима отладки
    if args.debug:
        for handler in logging.root.handlers:
            handler.setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        logger.debug("Включен режим отладки")
    
    # Вывод информации о запуске
    logger.info(f"Запуск AutoAU v{VERSION}")
    logger.info(f"Целевой URL: {TARGET_URL}")
    logger.info(f"Количество аккаунтов: {len(ACCOUNTS)}")
    
    # Создаем папку для сессий
    if not os.path.exists('sessions'):
        os.makedirs('sessions', exist_ok=True)
    
    # Проверка окружения
    if resource_mgr.is_running_in_container():
        logger.info("Обнаружено контейнерное окружение")
    
    if resource_mgr.should_optimize_for_low_resources():
        logger.info("Активирован режим оптимизации для ограниченных ресурсов")
    
    # Получаем обертку сервисов (инициализирует все необходимые сервисы)
    wrapper = get_service_wrapper()
    
    # Обработка одного указанного аккаунта
    if args.account:
        # Ищем аккаунт в списке
        account_found = False
        for email, password in ACCOUNTS:
            if email.lower() == args.account.lower():
                account_found = True
                logger.info(f"Обработка указанного аккаунта: {email}")
                
                if args.check:
                    # Только проверка состояния переключателя
                    is_on = verify_account_status(email, password)
                    if is_on is not None:
                        logger.info(f"Состояние переключателя для {email}: {'включен' if is_on else 'выключен'}")
                    else:
                        logger.error(f"Не удалось определить состояние переключателя для {email}")
                else:
                    # Полная обработка аккаунта
                    success = wrapper.process_account(email, password)
                    logger.info(f"Обработка аккаунта {email} {'успешна' if success else 'не удалась'}")
                break
                
        if not account_found:
            logger.error(f"Аккаунт {args.account} не найден в списке")
            return
            
        logger.info("Обработка завершена")
        return
    
    # Режим тестирования (однократный запуск)
    if args.test_mode:
        logger.info("Запуск в тестовом режиме (однократный запуск)")
        
        if not ACCOUNTS:
            logger.error("Список аккаунтов пуст")
            return
            
        # Берем первый аккаунт для теста
        test_email, test_password = ACCOUNTS[0]
        
        if args.check:
            # Только проверка состояния переключателя
            is_on = verify_account_status(test_email, test_password)
            if is_on is not None:
                logger.info(f"Состояние переключателя для {test_email}: {'включен' if is_on else 'выключен'}")
            else:
                logger.error(f"Не удалось определить состояние переключателя для {test_email}")
        else:
            # Полная обработка тестового аккаунта
            success = wrapper.process_account(test_email, test_password)
            logger.info(f"Тестовая обработка аккаунта {test_email} {'успешна' if success else 'не удалась'}")
            
        logger.info("Тестовый запуск завершен")
        return
    
    # Определение режима запуска для планового выполнения
    running_in_codespace = resource_mgr.is_running_in_github_codespace()
    if running_in_codespace:
        logger.info("Обнаружен запуск в GitHub Codespace - активированы оптимизации для ограниченных ресурсов")
    
    # Режим проверки для всех аккаунтов
    if args.check:
        logger.info(f"Проверка состояния переключателей для всех аккаунтов ({len(ACCOUNTS)})")
        
        for email, password in ACCOUNTS:
            is_on = verify_account_status(email, password)
            if is_on is not None:
                logger.info(f"Состояние переключателя для {email}: {'включен' if is_on else 'выключен'}")
            else:
                logger.error(f"Не удалось определить состояние переключателя для {email}")
                
        logger.info("Проверка завершена")
        return
        
    # Запуск периодической проверки переключателей
    logger.info("Запуск периодической проверки переключателей")
    run_scheduled_checks()


if __name__ == "__main__":
    main()