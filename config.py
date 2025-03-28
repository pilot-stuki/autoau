import os
import yaml
from datetime import datetime
from pytz import timezone
from resource_manager import get_resource_manager
import logging

logger = logging.getLogger(__name__)

# Путь к файлу конфигурации
CONFIG_FILE = "config.yaml"

class Config:
    """
    This module describes the config and provides helpers
    """

    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config = self._load_config()
        
        # Создаем директорию для скриншотов, если указана и не существует
        screenshots_dir = self.get_screenshots_dir()
        if screenshots_dir and not os.path.exists(screenshots_dir):
            try:
                os.makedirs(screenshots_dir, exist_ok=True)
                logger.info(f"Создана директория для скриншотов: {screenshots_dir}")
            except Exception as e:
                logger.error(f"Не удалось создать директорию для скриншотов: {e}")

    def _load_config(self):
        """Загружает конфигурацию из YAML файла"""
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logger.info(f"Конфигурация загружена из {CONFIG_FILE}")
                return config
        except Exception as e:
            logger.warning(f"Не удалось загрузить конфигурацию из {CONFIG_FILE}: {e}")
            # Возвращаем значения по умолчанию
            return {
                'target_url': 'https://scarletblue.com.au/auth/login',
                'browser': {
                    'headless': False
                },
                'screenshots': {
                    'enabled': True,
                    'directory': 'screenshots'
                }
            }

    def get_conf(self):
        return self.config

    def get_target_url(self) -> str:
        return self.config['target_url']

    def get_visibility(self):
        """Возвращает настройку режима headless для браузера"""
        browser_config = self.config.get('browser', {})
        return browser_config.get('headless', False)

    def get_screenshots_enabled(self):
        """Возвращает флаг, включены ли скриншоты"""
        screenshots_config = self.config.get('screenshots', {})
        return screenshots_config.get('enabled', True)

    def get_screenshots_dir(self):
        """Возвращает директорию для сохранения скриншотов"""
        screenshots_config = self.config.get('screenshots', {})
        return screenshots_config.get('directory', 'screenshots')

    def get_log_file(self) -> bool:
        return self.config['log_file']

    @staticmethod
    def get_current_sydney_time() -> datetime.time:
        timezone_sydney = timezone('Australia/Sydney')
        return datetime.now(timezone_sydney).time()

    def get_users(self) -> list:
        """Get users from users.txt file using absolute path"""
        list_of_users = []
        users_path = os.path.join(self.base_dir, "users.txt")
        with open(users_path, "r") as file:
            for line in file:
                list_of_users.append(line.split())
        return list_of_users

    def make_log_dir(self):
        """Create log directory using absolute paths"""
        logs_dir = os.path.join(self.base_dir, 'logs')
        
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
            
        now = datetime.now()
        time_format = "%Y-%m-%d"
        dir_name = f'{now:{time_format}}'
        
        new_dir_path = os.path.join(logs_dir, dir_name)
        if not os.path.exists(new_dir_path):
            os.makedirs(new_dir_path)
            
        return dir_name

    def save_config(self):
        """Сохраняет текущую конфигурацию в файл"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False)
                logger.info(f"Конфигурация сохранена в {CONFIG_FILE}")
                return True
        except Exception as e:
            logger.error(f"Не удалось сохранить конфигурацию в {CONFIG_FILE}: {e}")
            return False