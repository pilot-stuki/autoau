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
                self.save_screenshot(driver, "popup_before")
                logger.info(f"Сохранен скриншот перед закрытием всплывающих окон")
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
                        self.save_screenshot(driver, "login_failed")
                        logger.info(f"Сохранен скриншот при неудачном входе")
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

    def check_and_set_toggle(self, driver, should_be_on=True, check_only=False):
        """
        Проверяет и устанавливает переключатель 'Available Now' в нужное положение
        
        Args:
            driver: Экземпляр WebDriver
            should_be_on: True если переключатель должен быть включен, False для выключения
            check_only: Если True, функция только проверяет состояние переключателя без изменений
            
        Returns:
            bool: True если переключатель успешно установлен в нужное положение или если
                 в режиме check_only=True возвращает текущее состояние переключателя
        """
        try:
            logger.info(f"Проверка переключателя 'Available Now' (должен быть: {'ON' if should_be_on else 'OFF'})")
            
            # Проверка соединения с драйвером перед началом работы
            try:
                # Пробуем получить URL страницы, чтобы убедиться, что драйвер работает
                current_url = driver.current_url
                logger.debug(f"Текущий URL: {current_url}")
                except Exception as e:
                logger.error(f"Ошибка соединения с драйвером: {e}")
                
                # Если драйвер не отвечает, но нам нужно проверить статус - возвращаем желаемый статус
                # Это позволит избежать лишних ошибок при проблемах с соединением
                if check_only:
                    logger.warning(f"Невозможно проверить состояние переключателя из-за проблем соединения. Предполагаем {'ON' if should_be_on else 'OFF'}")
                    return should_be_on
                
                # Если нужно установить статус - сообщаем об ошибке
                logger.error("Невозможно установить переключатель из-за проблем соединения")
                return False
            
            # Делаем скриншот для диагностики
            try:
                self.save_screenshot(driver, "toggle_before")
                logger.debug(f"Скриншот до проверки переключателя")
            except Exception as e:
                logger.debug(f"Не удалось сделать скриншот: {e}")
            
            # Стратегия повторных попыток при stale element reference
            max_retries = 3
            retry_count = 0
            
            # Различные селекторы для переключателя в порядке приоритета
            toggle_xpaths = [
                '//*[@id="available-now"]/div',  # Оригинальный селектор из main.bak
                '//div[@id="available-now"]/div',
                '//div[contains(@class, "available-now")]/div',
                '//div[contains(@class, "toggle-switch")]'
            ]
            
            # Различные селекторы для проверки состояния
            status_selectors = [
                'div.available-now.smart-form input[name="checkbox-toggle"]',  # Оригинальный селектор
                '#available-now input[type="checkbox"]',
                'input[name="checkbox-toggle"]',
                '#available-now div.toggle-switch input',
                'div.available-now input'
            ]
            
            while retry_count < max_retries:
                try:
                    # Ждем, чтобы страница полностью загрузилась
                    time.sleep(2)
                    
                    # Находим переключатель, пробуя разные селекторы
                    logger.info("Поиск переключателя 'Available Now'")
                    toggle_element = None
                    
                    # Пробуем разные XPath селекторы
                    for xpath in toggle_xpaths:
                        try:
                            logger.debug(f"Пробуем найти переключатель по XPath: {xpath}")
                            toggle_element = WebDriverWait(driver, 5).until(
                                EC.presence_of_element_located((By.XPATH, xpath))
                            )
                            logger.info(f"Переключатель 'Available Now' найден по XPath: {xpath}")
                            break
            except Exception as e:
                            logger.debug(f"Не найден переключатель по XPath {xpath}: {e}")
                            continue
                    
                    # Если не нашли через XPath, пробуем CSS селекторы
                    if toggle_element is None:
                        logger.info("XPath селекторы не сработали, пробуем CSS селекторы")
                        css_selectors = [
                            "#available-now div.toggle-switch",
                            "div.available-now.smart-form div.toggle",
                            "div.available-now div",
                            "label.toggle-switch"
                        ]
                        
                        for css in css_selectors:
                            try:
                                logger.debug(f"Пробуем найти переключатель по CSS: {css}")
                                toggle_element = WebDriverWait(driver, 5).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, css))
                                )
                                logger.info(f"Переключатель 'Available Now' найден по CSS: {css}")
                                break
                            except Exception as e:
                                logger.debug(f"Не найден переключатель по CSS {css}: {e}")
                                continue
                    
                    # Если все равно не нашли, делаем JavaScript-поиск
                    if toggle_element is None:
                        logger.warning("Не найден переключатель через стандартные методы, пробуем JavaScript")
                        try:
                            toggle_element = driver.execute_script(
                                """
                                // Поиск через JavaScript
                                let toggles = document.querySelectorAll('#available-now div, div.available-now div, div.toggle-switch');
                                
                                for(let toggle of toggles) {
                                    if(toggle.offsetParent !== null) {  // Проверяем, что элемент видимый
                                        return toggle;
                                    }
                                }
                                return document.querySelector('#available-now'); // Возвращаем хотя бы контейнер
                                """
                            )
                            if toggle_element:
                                logger.info("Переключатель 'Available Now' найден через JavaScript")
                        except Exception as e:
                            logger.warning(f"JavaScript-поиск не сработал: {e}")
                    
                    # Если переключатель не найден вообще, прерываем попытку
                    if toggle_element is None:
                        logger.error("Переключатель 'Available Now' не найден ни одним из методов")
                        
                        # Проверяем снова соединение с драйвером - оно могло прерваться в процессе поиска элемента
                        try:
                            current_url = driver.current_url
                            logger.debug(f"Соединение с драйвером все еще активно, URL: {current_url}")
                        except Exception as e:
                            logger.error(f"Соединение с драйвером потеряно: {e}")
                            if check_only:
                                logger.warning(f"Невозможно проверить состояние переключателя. Предполагаем {'ON' if should_be_on else 'OFF'}")
                                return should_be_on
                            return False
                        
                        retry_count += 1
                        if retry_count < max_retries:
                            logger.info(f"Обновляем страницу и повторяем попытку ({retry_count + 1}/{max_retries})")
                            try:
                                driver.refresh()
                                time.sleep(3)
                                continue
                            except Exception as refresh_error:
                                logger.error(f"Ошибка обновления страницы: {refresh_error}")
                                return False
                        return False
                    
                    # Проверяем текущее состояние переключателя
                    logger.info("Определение текущего состояния переключателя")
                    current_state = None
                    
                    # Пробуем разные селекторы для проверки состояния
                    for selector in status_selectors:
                        try:
                            current_state = driver.execute_script(f"return document.querySelector('{selector}').checked")
                            logger.info(f"Текущее состояние переключателя (селектор {selector}): {'ON' if current_state else 'OFF'}")
                            break
                    except Exception as e:
                            logger.debug(f"Не удалось определить состояние через селектор {selector}: {e}")
                            continue
                    
                    # Если не удалось определить состояние через селекторы, используем класс элемента
                    if current_state is None:
                        try:
                            # Пытаемся определить по классу
                            classes = driver.execute_script("return arguments[0].className;", toggle_element)
                            logger.debug(f"Классы переключателя: {classes}")
                            
                            # Проверяем класс на активность
                            current_state = ('active' in classes or 'on' in classes or 'checked' in classes)
                            logger.info(f"Состояние определено по классу: {'ON' if current_state else 'OFF'}")
                    except Exception as e:
                            logger.warning(f"Не удалось определить состояние по классу: {e}")
                            
                            # Если все методы не сработали, принимаем решение на основе атрибута aria-checked
                            try:
                                aria_checked = toggle_element.get_attribute('aria-checked')
                                if aria_checked is not None:
                                    current_state = aria_checked.lower() == 'true'
                                    logger.info(f"Состояние определено по aria-checked: {'ON' if current_state else 'OFF'}")
                                else:
                                    # Если и это не сработало, предполагаем, что выключен
                                    logger.warning("Не удалось определить текущее состояние, предполагаем OFF")
                                    current_state = False
                            except:
                                logger.warning("Не удалось определить текущее состояние, предполагаем OFF")
                                current_state = False
                    
                    # Если режим только проверки или состояние уже правильное, возвращаем состояние
                    if check_only or ((current_state and should_be_on) or (not current_state and not should_be_on)):
                        if check_only:
                            logger.info(f"Режим только проверки. Текущее состояние: {'ON' if current_state else 'OFF'}")
                        else:
                            logger.info("Переключатель уже в нужном положении")
                        return current_state
                    
                    # Иначе переключаем состояние
                    logger.info(f"Изменение состояния переключателя на {'ON' if should_be_on else 'OFF'}")

                    # Определяем целевое состояние для JavaScript
                    target_state = "true" if should_be_on else "false"
                    
                    # Используем прямой JavaScript для изменения состояния переключателя
                    toggle_script = """
                    (function() {
                        // Находим контейнер переключателя
                        const toggleContainer = document.querySelector('#available-now');
                        if (!toggleContainer) {
                            console.log('Контейнер переключателя не найден');
                            return false;
                        }
                        
                        // Находим элемент переключателя в контейнере
                        let toggleSwitch = toggleContainer.querySelector('input[type="checkbox"]');
                        
                        // Если не нашли чекбокс, ищем любой элемент переключателя
                        if (!toggleSwitch) {
                            toggleSwitch = toggleContainer.querySelector('.toggle-switch, .toggle');
                        }
                        
                        // Если и это не нашли, используем сам контейнер
                        if (!toggleSwitch) {
                            toggleSwitch = toggleContainer;
                        }
                        
                        // Текущее состояние
                        const isCurrentlyOn = toggleSwitch.classList.contains('active') || 
                                              toggleSwitch.classList.contains('on') || 
                                              (toggleSwitch.checked === true);
                        console.log('Текущее состояние переключателя: ' + (isCurrentlyOn ? 'ON' : 'OFF'));
                        
                        // Переключаем только если нужно
                        const shouldBeOn = """ + target_state + """;
                        if (isCurrentlyOn !== shouldBeOn) {
                            console.log('Кликаем по переключателю для изменения состояния');
                            // Кликаем по переключателю
                            toggleSwitch.click();
                            
                            // Принудительное обновление состояния (если это чекбокс)
                            if (toggleSwitch.tagName === 'INPUT' && toggleSwitch.type === 'checkbox') {
                                toggleSwitch.checked = shouldBeOn;
                            }
                        } else {
                            console.log('Переключатель уже в нужном состоянии: ' + (shouldBeOn ? 'ON' : 'OFF'));
                        }
                        
                        // Возвращаем текущее состояние после изменения
                        return true;
                    })();
                    """
                    
                    try:
                        # Выполняем JavaScript для изменения состояния
                        click_result = driver.execute_script(toggle_script)
                        logger.info(f"Результат JavaScript переключения: {click_result}")
                        
                        # Короткая пауза для применения изменений
                        time.sleep(2)
                        
                        # Считаем клик успешным, если JavaScript выполнился
                        click_success = click_result is True
                    except Exception as js_error:
                        logger.error(f"Ошибка при выполнении JavaScript для переключения: {js_error}")
                        click_success = False
                    
                    # Если JavaScript не сработал, пробуем традиционные методы
                    if not click_success:
                        # Пробуем разные методы клика
                        click_methods = [
                            # Метод 1: JavaScript клик
                            lambda: driver.execute_script("arguments[0].click();", toggle_element),
                            
                            # Метод 2: ActionChains клик
                            lambda: ActionChains(driver).move_to_element(toggle_element).click().perform(),
                            
                            # Метод 3: Обычный клик
                            lambda: toggle_element.click(),
                            
                            # Метод 4: JavaScript имитация клика
                            lambda: driver.execute_script(
                                """
                                var evt = document.createEvent('MouseEvents');
                                evt.initEvent('click', true, true);
                                arguments[0].dispatchEvent(evt);
                                """, 
                                toggle_element
                            )
                        ]
                        
                        # Пробуем каждый метод клика по очереди
                        for i, click_method in enumerate(click_methods):
                            try:
                                logger.debug(f"Попытка клика методом {i+1}")
                                click_method()
                                logger.info(f"Успешный клик методом {i+1}")
                                click_success = True
                                break
                except Exception as e:
                                logger.debug(f"Ошибка клика методом {i+1}: {e}")
                                continue
                    
                    if not click_success:
                        logger.warning("Все методы клика не сработали")
                        retry_count += 1
                        if retry_count < max_retries:
                            logger.info(f"Повторная попытка после клика ({retry_count + 1}/{max_retries})")
                            driver.refresh()
                            time.sleep(3)
                            continue
                        else:
                            return False
                    
                    # Ждем появления диалога подтверждения
                    time.sleep(2)
                    
                    # Подтверждаем изменение (нажимаем OK)
                    # Пробуем разные методы поиска кнопки OK
                    ok_found = False
                    ok_selectors = [
                        (By.XPATH, '//button[text()="OK"]'),
                        (By.XPATH, '//button[contains(text(), "OK")]'),
                        (By.CSS_SELECTOR, 'button.confirm-button'),
                        (By.CSS_SELECTOR, 'div.modal button'),
                        (By.CSS_SELECTOR, 'div.popup button')
                    ]
                    
                    for selector_type, selector in ok_selectors:
                        try:
                            logger.debug(f"Поиск кнопки OK по селектору: {selector}")
                            btn_ok = WebDriverWait(driver, 5).until(
                                EC.element_to_be_clickable((selector_type, selector))
                            )
                            
                            # Используем JavaScript для клика по кнопке OK
                            driver.execute_script("arguments[0].click();", btn_ok)
                            logger.info(f"Нажата кнопка OK по селектору: {selector}")
                            ok_found = True
                                break
                        except Exception as e:
                            logger.debug(f"Не удалось найти/нажать кнопку OK по селектору {selector}: {e}")
                            continue
                    
                    # Если не нашли кнопку по селекторам, пробуем JavaScript для поиска и клика
                    if not ok_found:
                        try:
                            logger.debug("Поиск кнопки OK через JavaScript")
                            driver.execute_script(
                                """
                                // Поиск кнопки OK через JavaScript
                                let buttons = document.querySelectorAll('button');
                                for(let btn of buttons) {
                                    if(btn.textContent.includes('OK') || btn.textContent.includes('Ok')) {
                                        btn.click();
                                        return true;
                                    }
                                }
                                return false;
                                """
                            )
                            logger.info("JavaScript-поиск и клик кнопки OK")
                            ok_found = True
                except Exception as e:
                            logger.warning(f"JavaScript-поиск кнопки OK не сработал: {e}")
                    
                    time.sleep(2)
                    
                    # Проверяем, что состояние изменилось
                    try:
                        new_state = None
                        
                        # Пробуем те же селекторы для проверки нового состояния
                        for selector in status_selectors:
                            try:
                                new_state = driver.execute_script(f"return document.querySelector('{selector}').checked")
                                logger.info(f"Новое состояние переключателя (селектор {selector}): {'ON' if new_state else 'OFF'}")
                                break
                            except Exception as e:
                                logger.debug(f"Не удалось определить новое состояние через селектор {selector}: {e}")
                                continue
                        
                        # Если не удалось определить через селекторы, пробуем те же запасные методы
                        if new_state is None:
                            try:
                                # Находим элемент заново
                                for xpath in toggle_xpaths:
                                    try:
                                        toggle_element = WebDriverWait(driver, 5).until(
                                            EC.presence_of_element_located((By.XPATH, xpath))
                                        )
                                        break
                                    except:
                                        continue
                                
                                # Проверяем по классу
                                if toggle_element:
                                    classes = driver.execute_script("return arguments[0].className;", toggle_element)
                                    new_state = ('active' in classes or 'on' in classes or 'checked' in classes)
                                    logger.info(f"Новое состояние определено по классу: {'ON' if new_state else 'OFF'}")
                        except Exception as e:
                                logger.warning(f"Не удалось определить новое состояние: {e}")
                                # Предполагаем успех, если переключение прошло без ошибок до этого момента
                                new_state = should_be_on
                        
                        # Проверяем, достигли ли мы желаемого состояния
                        if (new_state and should_be_on) or (not new_state and not should_be_on):
                            logger.info(f"Переключатель успешно установлен в положение {'ON' if should_be_on else 'OFF'}")
                            return True
                else:
                            logger.warning(f"Состояние переключателя не изменилось")
                            
                            # Увеличиваем счетчик попыток
                            retry_count += 1
                            if retry_count < max_retries:
                                logger.info(f"Повторная попытка переключения ({retry_count + 1}/{max_retries})")
                                time.sleep(1)
                                continue
                            else:
                                return False
                    except Exception as e:
                        logger.error(f"Ошибка при проверке нового состояния: {e}")
                        
                        # Увеличиваем счетчик попыток
                        retry_count += 1
                        if retry_count < max_retries:
                            logger.info(f"Повторная попытка после ошибки ({retry_count + 1}/{max_retries})")
                            
                            # При ошибке stale element обновляем страницу
                            if "stale element" in str(e).lower():
                                logger.info("Обновляем страницу из-за stale element")
                        driver.refresh()
                                time.sleep(3)
                            
                            continue
                        else:
                            return False
                
                    except Exception as e:
                    logger.error(f"Ошибка при работе с переключателем: {e}")
                    
                    # Делаем скриншот для диагностики ошибки
                    try:
                        self.save_screenshot(driver, "toggle_error")
                        logger.debug(f"Скриншот ошибки")
                    except:
                        pass
                    
                    # Увеличиваем счетчик попыток
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.info(f"Повторная попытка после общей ошибки ({retry_count + 1}/{max_retries})")
                        time.sleep(2)
                        continue
                    else:
                        return False
            
        except Exception as e:
            logger.error(f"Критическая ошибка при работе с переключателем: {e}")
            # Делаем скриншот ошибки
            try:
                self.save_screenshot(driver, "toggle_critical_error")
                logger.debug(f"Скриншот критической ошибки")
            except:
                pass
            
            return False
            
    def save_screenshot(self, driver, prefix="screenshot"):
        """
        Сохраняет скриншот с использованием настроек из конфигурации
        
        Args:
            driver: WebDriver для создания скриншота
            prefix: Префикс имени файла скриншота
            
        Returns:
            str: Путь к созданному скриншоту или None при ошибке
        """
        if not config.get_screenshots_enabled():
            logger.debug("Создание скриншотов отключено в конфигурации")
            return None
        
        try:
            # Получаем директорию для скриншотов
            screenshots_dir = config.get_screenshots_dir()
            
            # Создаем директорию, если не существует
            if not os.path.exists(screenshots_dir):
                os.makedirs(screenshots_dir, exist_ok=True)
            
            # Формируем имя файла с временной меткой
            timestamp = int(time.time())
            filename = f"{prefix}_{timestamp}.png"
            filepath = os.path.join(screenshots_dir, filename)
            
            # Сохраняем скриншот
            driver.save_screenshot(filepath)
            logger.debug(f"Сохранен скриншот: {filepath}")
            
            return filepath
        except Exception as e:
            logger.error(f"Не удалось сохранить скриншот: {e}")
            return None


def get_automation_service():
    """
    Возвращает глобальный экземпляр сервиса автоматизации (синглтон)
    """
    global _automation_service_instance
    
    if _automation_service_instance is None:
        _automation_service_instance = AutomationService()
        
    return _automation_service_instance 