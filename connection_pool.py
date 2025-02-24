import threading
from queue import Queue, Empty
from selenium.webdriver.chrome.service import Service
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class ServicePool:
    def __init__(self, max_size=5):
        self.max_size = max_size
        self.pool = Queue(maxsize=max_size)
        self.lock = threading.Lock()
        self._fill_pool()
    
    def _fill_pool(self):
        """Initialize pool with services"""
        for _ in range(self.max_size):
            service = Service('chromedriver')
            self.pool.put(service)
    
    @contextmanager
    def get_service(self):
        """Get a service from the pool"""
        service = None
        try:
            service = self.pool.get(timeout=30)
            yield service
        except Empty:
            logger.error("Service pool exhausted")
            raise
        finally:
            if service:
                try:
                    self.pool.put(service)
                except:
                    service.stop()

service_pool = ServicePool()
