import os
import json
import time
import pickle
import base64
import logging
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from selenium.common.exceptions import WebDriverException
from browser_service import get_browser_service

# Получение логгера
logger = logging.getLogger(__name__)

# Синглтон и блокировка для потокобезопасности
_session_service_instance = None
_instance_lock = threading.Lock()


class SessionServiceError(Exception):
    """Исключение, связанное с управлением сессиями"""
    pass


class SessionService:
    """
    Сервис для управления сессиями пользователей с оптимизацией повторного использования
    """
    
    def __init__(self):
        """Инициализация сервиса управления сессиями"""
        self.sessions = {}  # словарь сессий: email -> сессия
        self.sessions_lock = threading.Lock()  # блокировка для безопасной работы с сессиями
        
        # Настройки сессий
        self.session_dir = self._ensure_session_dir()
        self.max_session_age = timedelta(hours=12)  # максимальный возраст сессии
        self.check_interval = 30  # интервал проверки работоспособности в секундах
        
        # Загружаем существующие сессии
        self._load_sessions()
        
        # Запускаем периодическую проверку сессий
        self._start_session_monitoring()
        
        logger.info(f"Инициализирован SessionService: путь={self.session_dir}, "
                    f"макс_возраст={self.max_session_age}, "
                    f"интервал_проверки={self.check_interval}с")

    def _ensure_session_dir(self):
        """Создает директорию для хранения сессий"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        session_dir = os.path.join(base_dir, 'sessions')
        os.makedirs(session_dir, exist_ok=True)
        return session_dir

    def _load_sessions(self):
        """Загружает сохраненные сессии из файлов"""
        try:
            session_files = list(Path(self.session_dir).glob("*.session"))
            
            if not session_files:
                logger.info("Сохраненные сессии не найдены")
                return
                
            loaded_count = 0
            # Временный словарь для загрузки сессий
            temp_sessions = {}
            
            for session_path in session_files:
                try:
                    # Получаем email из имени файла
                    filename = session_path.name
                    email = filename.replace('.session', '')
                    
                    # Проверяем актуальность сессии по времени модификации файла
                    mod_time = datetime.fromtimestamp(os.path.getmtime(session_path))
                    age = datetime.now() - mod_time
                    
                    if age > self.max_session_age:
                        logger.info(f"Удаление устаревшей сессии: {email} (возраст: {age})")
                        os.remove(session_path)
                        continue
                        
                    # Загружаем данные сессии
                    with open(session_path, 'r') as f:
                        session_data = json.load(f)
                        
                    if self._validate_session_data(session_data):
                        # Добавляем сессию во временный словарь
                        temp_sessions[email] = session_data
                        loaded_count += 1
                    else:
                        logger.warning(f"Некорректные данные сессии для {email}, удаление")
                        os.remove(session_path)
                        
                except Exception as e:
                    logger.error(f"Ошибка при загрузке сессии {session_path}: {e}")
                    try:
                        os.remove(session_path)  # удаляем поврежденный файл
                    except:
                        pass
                        
            # Обновляем self.sessions атомарно с блокировкой
            with self.sessions_lock:
                self.sessions.update(temp_sessions)
                
            logger.info(f"Загружено {loaded_count} сессий")
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке сессий: {e}")

    def _validate_session_data(self, session_data):
        """
        Проверяет корректность данных сессии
        
        Args:
            session_data: Данные сессии
            
        Returns:
            bool: True если данные корректны
        """
        required_fields = ['cookies', 'created_at', 'last_used']
        
        if not all(field in session_data for field in required_fields):
            return False
            
        # Проверка формата дат
        try:
            created_at = datetime.fromisoformat(session_data['created_at'])
            last_used = datetime.fromisoformat(session_data['last_used'])
            
            # Проверка возраста сессии
            age = datetime.now() - created_at
            if age > self.max_session_age:
                return False
                
        except ValueError:
            return False
            
        # Проверка наличия cookies
        if not isinstance(session_data['cookies'], list) or not session_data['cookies']:
            return False
            
        return True

    def _start_session_monitoring(self):
        """Запускает периодическую проверку и очистку сессий"""
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(
            target=self._session_monitor_loop,
            daemon=True
        )
        self.monitor_thread.start()
        
    def _session_monitor_loop(self):
        """Цикл мониторинга сессий"""
        while self.monitoring_active:
            try:
                self._cleanup_expired_sessions()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Ошибка в мониторинге сессий: {e}")
                time.sleep(self.check_interval * 2)

    def _cleanup_expired_sessions(self):
        """Очищает устаревшие сессии"""
        now = datetime.now()
        expired_emails = []
        
        with self.sessions_lock:
            # Находим устаревшие сессии
            for email, session_data in self.sessions.items():
                try:
                    last_used = datetime.fromisoformat(session_data['last_used'])
                    age = now - last_used
                    
                    if age > self.max_session_age:
                        expired_emails.append(email)
                except Exception as e:
                    logger.error(f"Ошибка при проверке времени сессии для {email}: {e}")
                    expired_emails.append(email)
            
            # Удаляем устаревшие сессии
            for email in expired_emails:
                self.sessions.pop(email, None)
                
                # Удаляем файл сессии, если он существует
                try:
                    session_path = os.path.join(self.session_dir, f"{email}.session")
                    if os.path.exists(session_path):
                        os.remove(session_path)
                except Exception as e:
                    logger.error(f"Ошибка при удалении файла сессии для {email}: {e}")
                
        if expired_emails:
            logger.info(f"Очищено устаревших сессий: {len(expired_emails)}")

    def get_session(self, email):
        """
        Возвращает данные сессии пользователя, если они есть
        
        Args:
            email: Email пользователя
            
        Returns:
            dict: Данные сессии или None, если сессия не найдена
        """
        with self.sessions_lock:
            return self.sessions.get(email)

    def save_session(self, email, driver):
        """
        Сохраняет сессию пользователя из драйвера
        
        Args:
            email: Email пользователя
            driver: Экземпляр WebDriver
            
        Returns:
            dict: Данные сохраненной сессии
        """
        try:
            # Получаем cookies из драйвера
            cookies = driver.get_cookies()
            
            if not cookies:
                logger.warning(f"Нет cookies для сохранения сессии {email}")
                return None
                
            # Формируем данные сессии
            now = datetime.now().isoformat()
            
            session_data = {
                'cookies': cookies,
                'created_at': now,
                'last_used': now,
                'user_agent': driver.execute_script("return navigator.userAgent;")
            }
            
            # Сохраняем в памяти
            with self.sessions_lock:
                self.sessions[email] = session_data
                
            # Сохраняем в файл
            self._save_session_to_file(email, session_data)
            
            logger.info(f"Сохранена сессия для {email}")
            return session_data
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении сессии для {email}: {e}")
            return None

    def _save_session_to_file(self, email, session_data):
        """
        Сохраняет данные сессии в файл
        
        Args:
            email: Email пользователя
            session_data: Данные сессии
        """
        try:
            session_path = os.path.join(self.session_dir, f"{email}.session")
            
            with open(session_path, 'w') as f:
                json.dump(session_data, f)
                
        except Exception as e:
            logger.error(f"Ошибка при сохранении файла сессии для {email}: {e}")

    def apply_session(self, email, driver):
        """
        Применяет сохраненную сессию к драйверу
        
        Args:
            email: Email пользователя
            driver: Экземпляр WebDriver
            
        Returns:
            bool: True если сессия успешно применена
        """
        session_data = self.get_session(email)
        
        if not session_data:
            logger.info(f"Сессия для {email} не найдена")
            return False
            
        try:
            # Проверяем возраст сессии
            created_at = datetime.fromisoformat(session_data['created_at'])
            age = datetime.now() - created_at
            
            if age > self.max_session_age:
                logger.info(f"Сессия для {email} устарела (возраст: {age})")
                with self.sessions_lock:
                    self.sessions.pop(email, None)
                return False
                
            # Загружаем базовую страницу перед установкой cookies
            driver.get("about:blank")
            
            # Применяем cookies
            for cookie in session_data['cookies']:
                try:
                    # Selenium не может установить HttpOnly cookies через JavaScript,
                    # поэтому нужно исключить некоторые атрибуты
                    if 'expiry' in cookie:
                        cookie['expiry'] = int(cookie['expiry'])
                    driver.add_cookie(cookie)
                except Exception as cookie_error:
                    logger.debug(f"Ошибка при установке cookie: {cookie_error}")
                    
            # Обновляем время последнего использования
            session_data['last_used'] = datetime.now().isoformat()
            
            with self.sessions_lock:
                self.sessions[email] = session_data
                
            # Обновляем файл сессии
            self._save_session_to_file(email, session_data)
            
            logger.info(f"Сессия успешно применена для {email}")
            return True
            
        except WebDriverException as e:
            logger.error(f"Ошибка WebDriver при применении сессии для {email}: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка при применении сессии для {email}: {e}")
            return False

    def check_session_validity(self, email, test_url):
        """
        Проверяет работоспособность сессии
        
        Args:
            email: Email пользователя
            test_url: URL для проверки авторизации
            
        Returns:
            bool: True если сессия действительна
        """
        session_data = self.get_session(email)
        
        if not session_data:
            return False
            
        try:
            # Создаем временный драйвер для проверки
            browser_service = get_browser_service()
            driver = browser_service.create_driver(headless=True)
            
            try:
                # Применяем сессию
                if not self.apply_session(email, driver):
                    return False
                    
                # Проверяем доступ к защищенной странице
                driver.get(test_url)
                
                # Ждем загрузки страницы
                time.sleep(2)
                
                # Проверяем наличие признаков успешной авторизации
                # (логика зависит от конкретного сайта)
                page_source = driver.page_source.lower()
                current_url = driver.current_url.lower()
                
                # Если URL содержит 'login', возможно, нас перенаправили на страницу входа
                if 'login' in current_url:
                    return False
                    
                # Дополнительная логика проверки для конкретного сайта
                # ...
                
                # Если мы не были перенаправлены на страницу входа, считаем сессию действительной
                logger.info(f"Сессия для {email} проверена и действительна")
                return True
                
            finally:
                # Всегда закрываем временный драйвер
                browser_service.close_driver(driver)
                
        except Exception as e:
            logger.error(f"Ошибка при проверке сессии для {email}: {e}")
            return False

    def delete_session(self, email):
        """
        Удаляет сессию пользователя
        
        Args:
            email: Email пользователя
            
        Returns:
            bool: True если сессия была удалена
        """
        with self.sessions_lock:
            if email in self.sessions:
                self.sessions.pop(email)
                
                # Удаляем файл сессии
                try:
                    session_path = os.path.join(self.session_dir, f"{email}.session")
                    if os.path.exists(session_path):
                        os.remove(session_path)
                except Exception as e:
                    logger.error(f"Ошибка при удалении файла сессии для {email}: {e}")
                    
                logger.info(f"Сессия для {email} удалена")
                return True
            
            return False

    def cleanup_all_sessions(self):
        """
        Очищает все сессии
        
        Returns:
            int: Количество удаленных сессий
        """
        with self.sessions_lock:
            count = len(self.sessions)
            self.sessions.clear()
            
            # Удаляем файлы сессий
            try:
                for session_file in Path(self.session_dir).glob("*.session"):
                    session_file.unlink()
            except Exception as e:
                logger.error(f"Ошибка при удалении файлов сессий: {e}")
                
            logger.info(f"Очищено всех сессий: {count}")
            return count


def get_session_service():
    """
    Возвращает глобальный экземпляр сервиса сессий (синглтон)
    """
    global _session_service_instance
    
    if _session_service_instance is None:
        with _instance_lock:  # блокировка для потокобезопасности
            if _session_service_instance is None:  # двойная проверка для избежания состояния гонки
                _session_service_instance = SessionService()
                
    return _session_service_instance 