import os
import time
import logging
import random
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementNotInteractableException,
    StaleElementReferenceException,
    WebDriverException
)

from browser_service import get_browser_service
from session_service import get_session_service
from error_service import get_error_service, ErrorScope
from resource_manager import get_resource_manager
from config import Config
import sys

# Получение конфигурации
config = Config()

# Получение логгера
logger = logging.getLogger(__name__)

# Создание синглтона для сервиса автоматизации
_automation_service_instance = None


class AutomationServiceError(Exception):
    """Ошибки, специфичные для сервиса автоматизации"""
    pass


class LoginError(AutomationServiceError):
    """Ошибки авторизации"""
    pass


class ToggleError(AutomationServiceError):
    """Ошибки управления переключателем"""
    pass


class AutomationService:
    """
    Сервис для автоматизации основных операций: авторизация и управление переключателем
    """
    
    def __init__(self):
        """Инициализация сервиса автоматизации"""
        self.browser_service = get_browser_service()
        self.session_service = get_session_service()
        self.error_service = get_error_service()
        self.resource_mgr = get_resource_manager()
        
        # URL и селекторы - исправленные для поддержки различных вариантов страниц входа
        self.target_url = config.get_target_url()
        
        # Селектор для переключателя (установлен конкретно для scarletblue.com.au)
        self.toggle_selector = "div.available-now.smart-form input[name='checkbox-toggle'], #available-now input[type='checkbox'], #available-now div.toggle-switch"
        
        # Селекторы для элементов формы входа (установлены конкретно для scarletblue.com.au)
        self.login_button_selector = "button[name='login'], input[name='login']"
        self.email_field_selector = "#email, input[id='email'], input[name='email']"
        self.password_field_selector = "#password, input[id='password'], input[name='password']"
        
        # Селекторы для кнопок закрытия всплывающих окон
        self.close_button_selector = "button:contains('Close'), button[text()='Close']"
        self.ok_button_selector = "button:contains('OK'), button[text()='OK']"
        self.enter_link_selector = ".terms-and-conditions__enter-link"
        
        # Интервалы для проверки переключателя
        self.toggle_check_interval = 3  # секунды между проверками во время одной сессии
        self.min_toggle_checks = 3      # минимальное количество проверок за одну сессию
        
        # Настройки времени ожидания (увеличены для более надежной работы)
        self.page_load_timeout = 60     # таймаут загрузки страницы
        self.element_wait_timeout = 20  # таймаут ожидания элемента
        self.max_login_retries = 3      # максимальное количество попыток входа
        self.max_toggle_retries = 3     # максимальное количество попыток для обработки переключателя
        
        # Оптимизации для работы в GitHub Codespace
        if self.resource_mgr.should_optimize_for_low_resources():
            self.browser_service.set_headless_mode(True)  # всегда используем безголовый режим
            logger.info("Автоматизация настроена на оптимизацию для ограниченных ресурсов")
            
        logger.info(f"Инициализирован AutomationService: target_url={self.target_url}")

    def close_popups(self, driver):
        """
        Закрывает всплывающие окна и модальные диалоги на странице
        
        Args:
            driver: Экземпляр WebDriver
            
        Returns:
            bool: True если какое-либо окно было закрыто, False в противном случае
        """
        popup_closed = False
        
        try:
            logger.info("Безопасное закрытие всплывающих окон")
            
            # Ограничиваем время выполнения метода для предотвращения зависаний
            max_popup_close_time = time.time() + 10  # Максимум 10 секунд на все попытки
            
            # Диагностическая информация о странице
            logger.info(f"URL={driver.current_url}, Title={driver.title}")
            
            # Конкретные селекторы для scarletblue.com.au с приоритетами
            selectors_to_try = [
                # Приоритетные селекторы (быстрая проверка)
                {"type": By.XPATH, "selector": '//button[text()="Close"]', "priority": "high"},
                {"type": By.XPATH, "selector": '//button[text()="OK"]', "priority": "high"},
                {"type": By.XPATH, "selector": '//*[@class="terms-and-conditions__enter-link"]', "priority": "high"},
                {"type": By.CSS_SELECTOR, "selector": ".modal-close", "priority": "high"},
                {"type": By.CSS_SELECTOR, "selector": ".popup-close", "priority": "high"},
                # Другие возможные селекторы (проверяем, если есть время)
                {"type": By.CSS_SELECTOR, "selector": ".close-btn", "priority": "medium"},
                {"type": By.CSS_SELECTOR, "selector": "[data-dismiss='modal']", "priority": "medium"},
                {"type": By.CSS_SELECTOR, "selector": ".close", "priority": "medium"},
                {"type": By.CSS_SELECTOR, "selector": ".dismiss", "priority": "medium"},
                {"type": By.CSS_SELECTOR, "selector": ".modal .close", "priority": "low"},
                {"type": By.CSS_SELECTOR, "selector": ".popup .close", "priority": "low"},
                {"type": By.CSS_SELECTOR, "selector": "button.close", "priority": "low"},
                {"type": By.CSS_SELECTOR, "selector": ".modal-header .close", "priority": "low"},
                {"type": By.CSS_SELECTOR, "selector": ".ui-dialog-titlebar-close", "priority": "low"},
                {"type": By.CSS_SELECTOR, "selector": ".closeButton", "priority": "low"},
                {"type": By.CSS_SELECTOR, "selector": "div.cookie-modal button", "priority": "low"},
                {"type": By.CSS_SELECTOR, "selector": ".cookie-banner button", "priority": "low"},
                {"type": By.CSS_SELECTOR, "selector": ".cookie-notice button", "priority": "low"},
                {"type": By.CSS_SELECTOR, "selector": "button.accept-cookies", "priority": "low"},
                {"type": By.CSS_SELECTOR, "selector": "button[aria-label='Close']", "priority": "low"},
                {"type": By.CSS_SELECTOR, "selector": "div[role='dialog'] button", "priority": "low"}
            ]
            
            # Делаем скриншот до закрытия для отладки
            try:
                screenshot_path = f"popup_before_{int(time.time())}.png"
                driver.save_screenshot(screenshot_path)
                logger.info(f"Сохранен скриншот перед закрытием всплывающих окон: {screenshot_path}")
            except Exception as e:
                logger.error(f"Не удалось сохранить скриншот: {e}")
            
            # Логируем информацию о DOM кратко для экономии времени
            try:
                logger.info(f"Элементы: div={len(driver.find_elements(By.TAG_NAME, 'div'))}, "+
                          f"button={len(driver.find_elements(By.TAG_NAME, 'button'))}")
            except Exception as e:
                logger.debug(f"Ошибка при анализе DOM: {e}")
            
            # Пробуем закрыть по разным селекторам с учетом приоритета
            # Сначала проверяем высокоприоритетные селекторы
            for priority in ["high", "medium", "low"]:
                # Проверяем таймаут
                if time.time() > max_popup_close_time:
                    logger.info(f"Превышен таймаут (10с) при обработке селекторов {priority} приоритета")
                    break
                
                for selector_info in [s for s in selectors_to_try if s["priority"] == priority]:
                    # Повторная проверка таймаута
                    if time.time() > max_popup_close_time:
                        break
                    
                    try:
                        selector_type = selector_info["type"]
                        selector = selector_info["selector"]
                        
                        # Быстрый поиск элементов без долгого ожидания
                        elements = driver.find_elements(selector_type, selector)
                        
                        if elements:
                            logger.info(f"Найдено {len(elements)} элементов: {selector} ({priority})")
                            
                            for element in elements:
                                # Еще раз проверяем таймаут
                                if time.time() > max_popup_close_time:
                                    break
                                
                                try:
                                    # Проверяем, что элемент отображается
                                    if element.is_displayed():
                                        # Пробуем JavaScript клик как наиболее надежный
                                        driver.execute_script("arguments[0].click();", element)
                                        logger.info(f"Закрыт элемент: {selector}")
                                        
                                        popup_closed = True
                                        
                                        # Короткая пауза после клика
                                        time.sleep(0.5)
                                        
                                        # Если это был высокоприоритетный элемент, завершаем обработку
                                        if priority == "high":
                                            return True
                                except Exception as e:
                                    logger.debug(f"Ошибка клика: {e}")
                    except Exception as e:
                        logger.debug(f"Ошибка селектора {selector}: {e}")
            
            return popup_closed
            
        except Exception as e:
            logger.warning(f"Ошибка при закрытии всплывающих окон: {e}")
            return False

    def login(self, email, password, use_session=True, bypass_antibot=False, driver=None):
        """
        Выполняет авторизацию пользователя на сайте
        
        Args:
            email: Email пользователя
            password: Пароль пользователя
            use_session: Использовать ли сохраненную сессию
            bypass_antibot: Применять ли дополнительные методы обхода защиты от ботов
            driver: Созданный экземпляр драйвера (чтобы не создавать новый)
            
        Returns:
            tuple: (driver, is_new_login) - экземпляр драйвера и флаг новой авторизации
        """
        logger.info(f"Авторизация для {email}")
        logger.info(f"Целевой URL: {self.target_url}")
        
        # Отслеживаем время операций для диагностики
        start_time = time.time()
        step_times = {}
        
        def log_step(step_name):
            """Логирует время выполнения шага"""
            current_time = time.time()
            elapsed = current_time - start_time
            step_times[step_name] = elapsed
            logger.info(f"ШАГ ВХОДА [{step_name}] - {elapsed:.2f}с для {email}")
        
        retry_count = 0
        max_retries = 2
        
        # Используем переданный драйвер или создаем новый
        if driver is None:
            log_step("начало_создания_драйвера")
            
            # Для обратной совместимости создаем драйвер
            logger.info("Драйвер не предоставлен, создаю стандартный")
            headless = True if self.resource_mgr.should_optimize_for_low_resources() else config.get_visibility() is False
            
            # Создаем драйвер с оптимизированной стратегией выбора
            try:
                driver, using_undetected = self.browser_service.create_driver_with_fallback(
                    headless=headless,
                    incognito=True,
                    implicit_wait=5  # Уменьшено с 10 до 5 для ускорения
                )
                
                if using_undetected:
                    logger.info(f"Используем undetected_chromedriver для {email} (обнаружены анти-бот меры)")
                else:
                    logger.info(f"Используем обычный ChromeDriver для {email}")
                    
                log_step("драйвер_создан")
            except Exception as e:
                logger.error(f"Не удалось создать драйвер для {email}: {e}")
                raise LoginError(f"Не удалось создать драйвер для входа: {e}")
        
        # Установка таймаута загрузки страницы - уменьшено с 30 до 20
        driver.set_page_load_timeout(20)
        
        try:
            # Переход на страницу логина (с отслеживанием времени)
            logger.info(f"Переход на страницу входа: {self.target_url}")
            
            # Устанавливаем максимальное время для операции загрузки страницы
            page_load_start = time.time()
            page_load_timeout = 15  # Уменьшено до 15 секунд
            
            try:
                driver.get(self.target_url)
                logger.info(f"Страница загружена за {time.time() - page_load_start:.2f}с")
            except Exception as e:
                # Если загрузка не удалась, логируем и бросаем исключение
                logger.error(f"Ошибка при загрузке страницы: {e}")
                raise LoginError(f"Не удалось загрузить страницу входа: {e}")
            
            logger.info(f"Текущий URL после загрузки: {driver.current_url}")
            log_step("страница_загружена")
            
            # Небольшая пауза для загрузки JS
            time.sleep(1.5)  # Уменьшено с 2 до 1.5 секунд
            
            # Закрываем всплывающие окна при загрузке страницы (с ограниченным временем)
            logger.info("Закрытие всплывающих окон перед входом")
            try:
                popups_closed = self.close_popups(driver)
                logger.info(f"Закрытие всплывающих окон: {popups_closed}")
            except Exception as e:
                logger.warning(f"Ошибка при закрытии всплывающих окон: {e}")
                # Продолжаем работу даже если не удалось закрыть окна
            
            log_step("всплывающие_окна_закрыты")
            
            # Проверяем, есть ли поле Email на странице
            try:
                # Проверка наличия селекторов
                if not self.email_field_selector or not self.password_field_selector or not self.login_button_selector:
                    logger.error("Один или несколько селекторов для формы входа не заданы!")
                    raise LoginError("Не заданы необходимые селекторы для формы входа")
                
                # Краткий анализ DOM для диагностики
                input_count = len(driver.find_elements(By.TAG_NAME, "input"))
                button_count = len(driver.find_elements(By.TAG_NAME, "button"))
                logger.info(f"Элементы на странице: inputs={input_count}, buttons={button_count}")
                
                # Поиск полей формы с таймаутами
                logger.info(f"Поиск поля email по селектору: {self.email_field_selector}")
                email_field_timeout = 8
                
                try:
                    email_field = WebDriverWait(driver, email_field_timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, self.email_field_selector))
                    )
                    logger.info("Поле email найдено")
                except TimeoutException:
                    logger.error(f"Таймаут при поиске поля email ({email_field_timeout}с)")
                    raise LoginError(f"Не удалось найти поле email за {email_field_timeout} секунд")
                
                log_step("поле_email_найдено")
                
                # Находим поле пароля (с коротким таймаутом)
                logger.info(f"Поиск поля password по селектору: {self.password_field_selector}")
                try:
                    password_field = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, self.password_field_selector))
                    )
                    logger.info("Поле password найдено")
                except TimeoutException:
                    logger.error("Таймаут при поиске поля password (3с)")
                    raise LoginError("Не удалось найти поле password")
                
                log_step("поле_password_найдено")
                
                # Находим кнопку входа (с коротким таймаутом)
                logger.info(f"Поиск кнопки login по селектору: {self.login_button_selector}")
                try:
                    login_button = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, self.login_button_selector))
                    )
                    logger.info("Кнопка login найдена")
                except TimeoutException:
                    logger.error("Таймаут при поиске кнопки login (3с)")
                    raise LoginError("Не удалось найти кнопку входа")
                
                log_step("форма_входа_найдена")
                
                # Вводим email и пароль
                logger.info(f"Ввод email: {email}")
                try:
                    email_field.clear()
                    email_field.send_keys(email)
                except Exception as e:
                    logger.error(f"Ошибка при вводе email: {e}")
                    raise LoginError(f"Не удалось ввести email: {e}")
                
                logger.info("Ввод password")
                try:
                    password_field.clear()
                    password_field.send_keys(password)
                except Exception as e:
                    logger.error(f"Ошибка при вводе password: {e}")
                    raise LoginError(f"Не удалось ввести пароль: {e}")
                
                log_step("данные_формы_заполнены")
                
                # Нажимаем кнопку входа
                logger.info("Нажатие кнопки login")
                button_click_success = False
                
                # Пробуем разные методы клика
                # 1. JavaScript клик
                try:
                    driver.execute_script("arguments[0].click();", login_button)
                    logger.info("Кнопка login нажата (JS click)")
                    button_click_success = True
                except Exception as e:
                    logger.warning(f"JS клик не сработал: {e}, пробуем другие методы")
                
                # 2. Прямой клик если предыдущий не сработал
                if not button_click_success:
                    try:
                        login_button.click()
                        logger.info("Кнопка login нажата (direct click)")
                        button_click_success = True
                    except Exception as e:
                        logger.warning(f"Прямой клик не сработал: {e}, пробуем другие методы")
                
                # 3. Клик через Actions если предыдущие методы не сработали
                if not button_click_success:
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        ActionChains(driver).move_to_element(login_button).click().perform()
                        logger.info("Кнопка login нажата (action chains)")
                        button_click_success = True
                    except Exception as e:
                        logger.error(f"Не удалось нажать кнопку входа даже через ActionChains: {e}")
                        raise LoginError(f"Все методы клика по кнопке входа не сработали: {e}")
                
                log_step("кнопка_входа_нажата")
                
                # Ждем завершения загрузки страницы после входа
                form_submit_timeout = 10
                form_submit_start = time.time()
                
                # Ждем изменения URL (признак успешной обработки формы)
                initial_url = driver.current_url
                url_change_detected = False
                
                for i in range(form_submit_timeout):
                    current_url = driver.current_url
                    if current_url != initial_url:
                        logger.info(f"URL изменился после входа: {current_url}")
                        url_change_detected = True
                        break
                        
                    time.sleep(1)
                
                if not url_change_detected:
                    logger.warning(f"URL не изменился после отправки формы, возможны проблемы с входом")
                
                log_step("ожидание_после_входа")
                
                # Закрываем всплывающие окна после входа (с защитой от зависаний)
                logger.info("Закрытие всплывающих окон после входа")
                try:
                    popups_closed = self.close_popups(driver)
                    logger.info(f"Всплывающие окна после входа: {popups_closed}")
                except Exception as e:
                    logger.warning(f"Ошибка при закрытии окон после входа: {e}")
                
                log_step("всплывающие_окна_после_входа")
                
                # Проверяем успешность входа
                logger.info(f"Проверка успешности входа, текущий URL: {driver.current_url}")
                if "login" not in driver.current_url.lower() and "auth" not in driver.current_url.lower():
                    logger.info(f"Успешный вход для {email}, текущий URL: {driver.current_url}")
                    
                    # Выводим полную статистику времени
                    total_time = time.time() - start_time
                    logger.info(f"Вход выполнен успешно за {total_time:.2f}с")
                    for step, step_time in step_times.items():
                        logger.info(f"  - {step}: {step_time:.2f}с")
                    
                    return driver, True  # True означает новый вход
                else:
                    logger.warning(f"Возможно неудачный вход для {email}, URL остался: {driver.current_url}")
                    
                    # Делаем скриншот при неудачном входе
                    try:
                        screenshot_path = f"login_failed_{int(time.time())}.png"
                        driver.save_screenshot(screenshot_path)
                        logger.info(f"Сохранен скриншот при неудачном входе: {screenshot_path}")
                    except Exception as e:
                        logger.error(f"Не удалось сделать скриншот: {e}")
                    
                    raise LoginError(f"Не удалось выполнить вход для {email} - URL остался прежним")
            
            except Exception as e:
                logger.error(f"Ошибка при заполнении формы входа: {e}")
                raise LoginError(f"Ошибка при заполнении формы входа: {e}")
                
        except Exception as e:
            logger.error(f"Ошибка при входе: {e}")
            raise LoginError(f"Не удалось выполнить вход: {e}")
            
        # Этот код не должен выполниться из-за возвратов и исключений выше
        raise LoginError("Непредвиденная ошибка в логике авторизации")


def get_automation_service():
    """
    Возвращает глобальный экземпляр сервиса автоматизации (синглтон)
    """
    global _automation_service_instance
    
    if _automation_service_instance is None:
        _automation_service_instance = AutomationService()
        
    return _automation_service_instance 