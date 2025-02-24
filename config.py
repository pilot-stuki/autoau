import os
import yaml
from datetime import datetime
from pytz import timezone


class Config:
    """
    This module describes the config and provides helpers
    """

    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(self.base_dir, "config.yaml")
        with open(config_path) as file:
            self._config = yaml.safe_load(file)

    def get_conf(self):
        return self._config

    def get_target_url(self) -> str:
        return self._config['target_url']

    def get_visibility(self) -> bool:
        return self._config['visibility']

    def get_log_file(self) -> bool:
        return self._config['log_file']

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