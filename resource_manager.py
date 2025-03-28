"""
Resource Manager for AutoAU application
Provides centralized resource monitoring, allocation, and optimization
"""

import os
import sys
import time
import logging
import threading
import psutil
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List
import platform
from functools import lru_cache
import requests
from urllib.parse import urlparse
import subprocess
import signal
import random

# Configure logger
logger = logging.getLogger(__name__)

# Default resource configuration
DEFAULT_CONFIGURATION = {
    # Memory thresholds (MB)
    'memory_thresholds': {
        'default': 500,      # Standard threshold
        'cloud': 350,        # For cloud/container environments
        'warning': 750,      # Warning level
        'critical': 900      # Critical level
    },
    # Process and thread limits
    'concurrency': {
        'default_processes': 2,   # Default process limit
        'max_processes': 4,       # Maximum processes allowed
        'max_threads': 5,         # Maximum threads per process
        'min_processes': 1        # Minimum processes needed
    },
    # Batch processing settings
    'batch': {
        'default_size': 5,        # Default batch size
        'min_size': 2,            # Minimum batch size
        'max_size': 10,           # Maximum batch size
        'size_factor': 0.5        # How much to adjust based on load
    },
    # Sleep intervals (seconds)
    'sleep': {
        'default_interval': 30,   # Default sleep time
        'min_interval': 5,        # Minimum sleep time
        'max_interval': 300,      # Maximum sleep time
        'jitter_factor': 0.2      # Random jitter percentage
    },
    # Timeout settings (seconds)
    'timeout': {
        'network_check': 30,      # Network connectivity checks
        'page_load': 60,          # Page loading
        'element_wait': 30,       # Element waiting time
        'driver_setup': 60,       # Driver initialization
        'process': 300,           # Individual process execution
        'batch': 600,             # Batch operation execution
        'cycle': 1800             # Complete cycle execution
    },
    # Adjustment factors for timeouts
    'timeout_factors': {
        'low_load': 0.8,          # Low system load factor
        'medium_load': 1.0,       # Medium system load factor
        'high_load': 1.5          # High system load factor
    },
    # Adaptive processing settings
    'adaptive': {
        'defer_threshold': 80,    # Load score to defer processing
        'sequential_threshold': 70, # Load score to switch to sequential
        'success_rate_threshold': 0.5, # Success rate before adjusting
        'error_penalty': 0.1,     # Penalty per error for calculations
        'metrics_window': 100,    # Number of operations to track
        'load_check_interval': 30 # Seconds between load checks
    }
}

class SystemResourceMonitor:
    """
    Monitors system resources and provides detailed metrics
    
    This class handles low-level resource monitoring, including:
    - CPU usage tracking
    - Memory usage monitoring
    - Disk I/O statistics
    - Network activity monitoring
    - Process tracking
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the system resource monitor
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or DEFAULT_CONFIGURATION
        self._last_check_time = 0
        self._last_load_info = {}
        self._lock = threading.RLock()
        
        # Check if running in container
        self.in_container = self._check_container_environment()
        
        # Get system information
        self.system_info = {
            'platform': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'processor': platform.processor(),
            'cores': psutil.cpu_count(logical=False),
            'threads': psutil.cpu_count(logical=True),
            'memory_total': psutil.virtual_memory().total / (1024 * 1024),  # MB
            'memory_available': psutil.virtual_memory().available / (1024 * 1024),  # MB
            'in_container': self.in_container
        }
        
        logger.debug(f"Initialized SystemResourceMonitor on {self.system_info['platform']} with "
                   f"{self.system_info['cores']} cores / {self.system_info['threads']} threads")
    
    def _check_container_environment(self) -> bool:
        """
        Check if running inside a container
        
        Returns:
            True if running in container, False otherwise
        """
        # Check for container indicators
        return (
            os.path.exists('/.dockerenv') or  # Docker
            os.environ.get('KUBERNETES_SERVICE_HOST') or  # Kubernetes
            os.environ.get('DYNO') or  # Heroku
            os.environ.get('GOOGLE_CLOUD_PROJECT')  # Google Cloud
        )
    
    def get_cpu_usage(self) -> Dict[str, float]:
        """
        Get detailed CPU usage metrics
        
        Returns:
            Dictionary with CPU metrics
        """
        try:
            # Get overall CPU percentage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Get per-CPU percentages
            per_cpu = psutil.cpu_percent(interval=0.1, percpu=True)
            
            # Get load averages (1min, 5min, 15min)
            if platform.system() != "Windows":
                load_avg = psutil.getloadavg()
            else:
                # Windows doesn't have load average, use CPU as approximation
                load_avg = (cpu_percent / 100 * self.system_info['cores'],) * 3
                
            # Calculate normalized load (load average divided by number of cores)
            normalized_load = load_avg[0] / self.system_info['cores'] * 100
                
            return {
                'percent': cpu_percent,
                'per_cpu': per_cpu,
                'load_avg': load_avg,
                'normalized_load': normalized_load,
                'count': len(per_cpu)
            }
        except Exception as e:
            logger.error(f"Error getting CPU metrics: {str(e)}")
            return {
                'percent': 0.0,
                'per_cpu': [],
                'load_avg': (0.0, 0.0, 0.0),
                'normalized_load': 0.0,
                'count': self.system_info['threads']
            }
    
    def get_memory_usage(self) -> Dict[str, float]:
        """
        Get detailed memory usage metrics
        
        Returns:
            Dictionary with memory metrics
        """
        try:
            # Get virtual memory information
            mem = psutil.virtual_memory()
            
            # Get swap information if available
            try:
                swap = psutil.swap_memory()
                swap_info = {
                    'swap_total_mb': swap.total / (1024 * 1024),
                    'swap_used_mb': swap.used / (1024 * 1024),
                    'swap_percent': swap.percent
                }
            except:
                swap_info = {
                    'swap_total_mb': 0,
                    'swap_used_mb': 0,
                    'swap_percent': 0
                }
            
            # Get process memory information
            process = psutil.Process(os.getpid())
            process_mem = process.memory_info()
            
            return {
                'total_mb': mem.total / (1024 * 1024),
                'available_mb': mem.available / (1024 * 1024),
                'used_mb': mem.used / (1024 * 1024),
                'percent': mem.percent,
                'process_mb': process_mem.rss / (1024 * 1024),
                **swap_info
            }
        except Exception as e:
            logger.error(f"Error getting memory metrics: {str(e)}")
            return {
                'total_mb': 0,
                'available_mb': 0,
                'used_mb': 0,
                'percent': 0,
                'process_mb': 0,
                'swap_total_mb': 0,
                'swap_used_mb': 0,
                'swap_percent': 0
            }
    
    def get_disk_usage(self) -> Dict[str, float]:
        """
        Get detailed disk usage metrics
        
        Returns:
            Dictionary with disk metrics
        """
        try:
            # Get disk usage for current directory
            disk_usage = psutil.disk_usage(os.path.abspath('.'))
            
            # Get disk I/O counters if available
            try:
                disk_io = psutil.disk_io_counters()
                io_info = {
                    'read_mb': disk_io.read_bytes / (1024 * 1024),
                    'write_mb': disk_io.write_bytes / (1024 * 1024),
                    'read_count': disk_io.read_count,
                    'write_count': disk_io.write_count
                }
            except:
                io_info = {
                    'read_mb': 0,
                    'write_mb': 0,
                    'read_count': 0,
                    'write_count': 0
                }
            
            return {
                'total_gb': disk_usage.total / (1024**3),
                'used_gb': disk_usage.used / (1024**3),
                'free_gb': disk_usage.free / (1024**3),
                'percent': disk_usage.percent,
                **io_info
            }
        except Exception as e:
            logger.error(f"Error getting disk metrics: {str(e)}")
            return {
                'total_gb': 0,
                'used_gb': 0,
                'free_gb': 0,
                'percent': 0,
                'read_mb': 0,
                'write_mb': 0,
                'read_count': 0,
                'write_count': 0
            }
    
    def get_network_activity(self) -> Dict[str, float]:
        """
        Get network activity metrics
        
        Returns:
            Dictionary with network metrics
        """
        try:
            # Get network I/O counters
            net_io = psutil.net_io_counters()
            
            return {
                'bytes_sent_mb': net_io.bytes_sent / (1024 * 1024),
                'bytes_recv_mb': net_io.bytes_recv / (1024 * 1024),
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv,
                'errin': net_io.errin,
                'errout': net_io.errout,
                'dropin': net_io.dropin,
                'dropout': net_io.dropout
            }
        except Exception as e:
            logger.debug(f"Error getting network metrics: {str(e)}")
            return {
                'bytes_sent_mb': 0,
                'bytes_recv_mb': 0,
                'packets_sent': 0,
                'packets_recv': 0,
                'errin': 0,
                'errout': 0,
                'dropin': 0,
                'dropout': 0
            }
    
    def get_chrome_processes(self) -> Dict[str, Any]:
        """
        Get information about Chrome processes
        
        Returns:
            Dictionary with Chrome process metrics
        """
        try:
            chrome_procs = []
            total_memory_mb = 0
            total_cpu_percent = 0
            
            # Find all Chrome processes
            for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
                try:
                    proc_name = proc.info.get('name', '').lower()
                    if 'chrome' in proc_name or 'chromedriver' in proc_name:
                        # Get process details
                        with proc.oneshot():
                            try:
                                memory_mb = proc.memory_info().rss / (1024 * 1024) if proc.memory_info() else 0
                                cpu_percent = proc.cpu_percent(interval=None)
                                
                                chrome_procs.append({
                                    'pid': proc.pid,
                                    'name': proc.name(),
                                    'memory_mb': memory_mb,
                                    'cpu_percent': cpu_percent,
                                    'create_time': datetime.fromtimestamp(proc.create_time()).isoformat()
                                })
                                
                                total_memory_mb += memory_mb
                                total_cpu_percent += cpu_percent
                            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                                continue
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            return {
                'count': len(chrome_procs),
                'total_memory_mb': total_memory_mb,
                'total_cpu_percent': total_cpu_percent,
                'processes': chrome_procs
            }
        except Exception as e:
            logger.debug(f"Error getting Chrome process metrics: {str(e)}")
            return {
                'count': 0,
                'total_memory_mb': 0,
                'total_cpu_percent': 0,
                'processes': []
            }
    
    def calculate_load_score(self, metrics: Dict[str, Any]) -> float:
        """
        Calculate a composite load score from 0-100
        
        Args:
            metrics: System metrics dictionary
            
        Returns:
            Load score from 0 (idle) to 100 (extremely busy)
        """
        try:
            # Get individual components with appropriate weights
            cpu_weight = 0.4
            memory_weight = 0.3
            disk_weight = 0.1
            process_weight = 0.2
            
            # CPU score (0-100)
            cpu_score = metrics.get('cpu_percent', 0)
            if 'normalized_load' in metrics:
                # Use normalized load if available (better indicator)
                normalized_load = metrics.get('normalized_load', 0)
                # Cap at 100
                cpu_score = min(normalized_load, 100)
            
            # Memory score (0-100)
            memory_score = metrics.get('memory_percent', 0)
            
            # Disk score (0-100)
            disk_score = metrics.get('disk_percent', 0)
            
            # Process score - relative to thresholds
            chrome_memory = metrics.get('chrome_memory_mb', 0)
            memory_threshold = self.config['memory_thresholds']['default']
            
            # Scale relative to threshold, cap at 100
            process_score = min(chrome_memory / memory_threshold * 100, 100)
            
            # Calculate weighted average
            load_score = (
                cpu_score * cpu_weight +
                memory_score * memory_weight +
                disk_score * disk_weight +
                process_score * process_weight
            )
            
            return min(load_score, 100)  # Cap at 100
            
        except Exception as e:
            logger.debug(f"Error calculating load score: {str(e)}")
            # Return medium load score as fallback
            return 50
    
    def get_system_metrics(self, detailed: bool = False) -> Dict[str, Any]:
        """
        Get comprehensive system metrics
        
        Args:
            detailed: Whether to include detailed process information
            
        Returns:
            Dictionary with system metrics
        """
        with self._lock:
            # Get CPU metrics
            cpu_metrics = self.get_cpu_usage()
            
            # Get memory metrics
            memory_metrics = self.get_memory_usage()
            
            # Get disk metrics
            disk_metrics = self.get_disk_usage()
            
            # Get Chrome metrics
            chrome_metrics = self.get_chrome_processes()
            
            # Collect all metrics
            metrics = {
                'timestamp': datetime.now().isoformat(),
                'cpu_percent': cpu_metrics['percent'],
                'normalized_load': cpu_metrics['normalized_load'],
                'memory_percent': memory_metrics['percent'],
                'memory_used_mb': memory_metrics['used_mb'],
                'memory_available_mb': memory_metrics['available_mb'],
                'disk_percent': disk_metrics['percent'],
                'process_memory_mb': memory_metrics['process_mb'],
                'chrome_process_count': chrome_metrics['count'],
                'chrome_memory_mb': chrome_metrics['total_memory_mb']
            }
            
            # Calculate load score
            metrics['load_score'] = self.calculate_load_score(metrics)
            
            # Add detailed metrics if requested
            if detailed:
                metrics['cpu_detailed'] = cpu_metrics
                metrics['memory_detailed'] = memory_metrics
                metrics['disk_detailed'] = disk_metrics
                metrics['network'] = self.get_network_activity()
                metrics['chrome_processes'] = chrome_metrics.get('processes', [])
                metrics['system_info'] = self.system_info
            
            return metrics


class ResourceManager:
    """
    Centralized resource management for the AutoAU application
    
    This class is responsible for:
    - Monitoring system resources
    - Providing adaptive timeouts
    - Determining optimal concurrency
    - Managing resource allocation
    - Tracking application performance
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the resource manager
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or DEFAULT_CONFIGURATION
        self.monitor = SystemResourceMonitor(self.config)
        
        # Lock for thread safety
        self._lock = threading.RLock()
        
        # Performance metrics
        self._success_count = 0
        self._error_count = 0
        self._recent_successes = [True] * 5  # Initialize with some successes
        self._recent_errors = [False] * 5    # Initialize with no errors
        
        # Caching of load info to reduce overhead
        self._last_load_check_time = 0
        self._load_check_interval = self.config['adaptive']['load_check_interval']
        self._last_load_info = {}
        
        logger.info("ResourceManager initialized")

    def get_config(self) -> Dict[str, Any]:
        """
        Get the current configuration
        
        Returns:
            Current configuration dictionary
        """
        return self.config
    
    def set_config(self, config: Dict[str, Any]) -> None:
        """
        Update the configuration
        
        Args:
            config: New configuration dictionary
        """
        with self._lock:
            # Merge with existing config
            for key, value in config.items():
                if key in self.config:
                    if isinstance(value, dict) and isinstance(self.config[key], dict):
                        self.config[key].update(value)
                    else:
                        self.config[key] = value
            
            # Update monitor config as well
            self.monitor.config = self.config
    
    def get_system_load(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get current system load information
        
        Args:
            force_refresh: Force a refresh of metrics even if cached
            
        Returns:
            Dictionary with system load metrics
        """
        with self._lock:
            current_time = time.time()
            
            # Return cached info if recent enough
            if (not force_refresh and 
                self._last_load_info and 
                current_time - self._last_load_check_time < self._load_check_interval):
                return self._last_load_info
            
            # Get fresh metrics
            self._last_load_info = self.monitor.get_system_metrics()
            self._last_load_check_time = current_time
            
            return self._last_load_info
    
    def get_load_category(self) -> str:
        """
        Get current load category (low, medium, high)
        
        Returns:
            Load category as string
        """
        load_info = self.get_system_load()
        load_score = load_info.get('load_score', 50)  # Default to medium if unknown
        
        if load_score < 40:
            return 'low'
        elif load_score < 70:
            return 'medium'
        else:
            return 'high'
    
    def get_time_period(self) -> str:
        """
        Get current time period (morning, afternoon, evening, night)
        
        Returns:
            Time period as string
        """
        current_hour = datetime.now().hour
        
        if 5 <= current_hour < 12:
            return 'morning'
        elif 12 <= current_hour < 17:
            return 'afternoon'
        elif 17 <= current_hour < 22:
            return 'evening'
        else:
            return 'night'
    
    def report_success(self) -> None:
        """Report a successful operation"""
        with self._lock:
            self._success_count += 1
            self._recent_successes.append(True)
            if len(self._recent_successes) > 100:
                self._recent_successes.pop(0)
    
    def report_error(self) -> None:
        """Report an operation error"""
        with self._lock:
            self._error_count += 1
            self._recent_errors.append(True)
            if len(self._recent_errors) > 100:
                self._recent_errors.pop(0)
            self._recent_successes.append(False)
            if len(self._recent_successes) > 100:
                self._recent_successes.pop(0)
    
    def get_success_rate(self) -> float:
        """
        Calculate recent success rate
        
        Returns:
            Success rate as a float between 0 and 1
        """
        with self._lock:
            if not self._recent_successes:
                return 1.0  # Default to 1.0 if no data
                
            return sum(1 for s in self._recent_successes if s) / len(self._recent_successes)
    
    def get_error_rate(self) -> float:
        """
        Calculate recent error rate
        
        Returns:
            Error rate as a float between 0 and 1
        """
        with self._lock:
            total_operations = self._success_count + self._error_count
            if total_operations == 0:
                return 0.0
            
            return self._error_count / total_operations
    
    def should_defer_processing(self) -> bool:
        """
        Determine if processing should be deferred due to system load
        
        Returns:
            True if processing should be deferred, False otherwise
        """
        load_info = self.get_system_load()
        load_score = load_info.get('load_score', 0)
        
        # Use configurable threshold
        defer_threshold = self.config['adaptive']['defer_threshold']
        
        # Higher score = higher load = more likely to defer
        return load_score > defer_threshold
    
    def get_optimal_processes(self) -> int:
        """
        Calculate optimal number of processes based on system resources
        
        Returns:
            Optimal process count
        """
        load_info = self.get_system_load()
        load_category = self.get_load_category()
        
        # Get config values
        default_processes = self.config['concurrency']['default_processes']
        max_processes = self.config['concurrency']['max_processes']
        min_processes = self.config['concurrency']['min_processes']
        
        # Adjust based on load category
        if load_category == 'low':
            optimal = max_processes
        elif load_category == 'medium':
            optimal = default_processes
        else:  # high
            optimal = min_processes
        
        # Further adjust based on CPU cores
        available_cores = max(1, self.monitor.system_info.get('cores', 1))
        
        # Don't use more processes than we have cores
        optimal = min(optimal, available_cores)
        
        # Always respect min/max bounds
        return max(min_processes, min(optimal, max_processes))
    
    def get_optimal_batch_size(self, total_accounts: int) -> int:
        """
        Calculate optimal batch size based on system resources and account count
        
        Args:
            total_accounts: Total number of accounts to process
            
        Returns:
            Optimal batch size
        """
        # Get config values
        default_size = self.config['batch']['default_size']
        min_size = self.config['batch']['min_size']
        max_size = self.config['batch']['max_size']
        
        # Adjust based on load category
        load_category = self.get_load_category()
        if load_category == 'low':
            # Can use larger batches when load is low
            size_factor = 1.5
        elif load_category == 'medium':
            # Use default batch size for medium load
            size_factor = 1.0
        else:  # high
            # Use smaller batches for high load
            size_factor = 0.6
        
        # Start with the default size and adjust
        optimal_size = int(default_size * size_factor)
        
        # Don't create batches larger than the total account count
        optimal_size = min(optimal_size, total_accounts)
        
        # Ensure we're within min/max bounds
        return max(min_size, min(optimal_size, max_size))
    
    def get_optimal_sleep_interval(self, base_interval: float) -> float:
        """
        Calculate optimal sleep interval based on system load
        
        Args:
            base_interval: Base sleep interval in seconds
            
        Returns:
            Adjusted sleep interval in seconds
        """
        # Get load category
        load_category = self.get_load_category()
        
        # Get time period
        time_period = self.get_time_period()
        
        # Base adjustment factors
        load_factors = {
            'low': 0.8,       # Shorter sleeps when load is low
            'medium': 1.0,    # Normal sleep times for medium load
            'high': 1.5       # Longer sleeps when load is high
        }
        
        time_factors = {
            'morning': 0.9,   # Shorter sleeps in the morning
            'afternoon': 1.0, # Normal sleep times in the afternoon
            'evening': 1.1,   # Slightly longer in the evening
            'night': 1.2      # Longest sleeps at night
        }
        
        # Apply both factors
        load_factor = load_factors.get(load_category, 1.0)
        time_factor = time_factors.get(time_period, 1.0)
        
        # Calculate adjusted interval
        interval = base_interval * load_factor * time_factor
        
        # Add small random jitter to avoid thundering herd
        jitter_factor = self.config['sleep']['jitter_factor']
        jitter = interval * jitter_factor * (2 * random.random() - 1)  # Random value between -jitter_factor and +jitter_factor
        
        # Apply jitter
        interval += jitter
        
        # Ensure within min/max bounds
        min_interval = self.config['sleep']['min_interval']
        max_interval = self.config['sleep']['max_interval']
        
        return max(min_interval, min(interval, max_interval))
    
    def get_adjusted_timeout(self, base_timeout: float, operation_type: str = None) -> float:
        """
        Calculate an adjusted timeout based on system load and operation type
        
        Args:
            base_timeout: Base timeout in seconds
            operation_type: Type of operation (network_check, page_load, etc.)
            
        Returns:
            Adjusted timeout in seconds
        """
        # Get load category
        load_category = self.get_load_category()
        
        # Get adjustment factor based on load
        load_factors = self.config['timeout_factors']
        factor = load_factors.get(f'{load_category}_load', 1.0)
        
        # Apply additional adjustment for operation type if needed
        operation_factors = {
            'network_check': 1.0,
            'page_load': 1.1,    # Give page loads a bit more time
            'element_wait': 0.9, # Element waits can be a bit shorter
            'driver_setup': 1.2, # Driver setup needs more time
            'process': 1.0,
            'batch': 1.0,
            'cycle': 1.0
        }
        
        if operation_type in operation_factors:
            factor *= operation_factors[operation_type]
        
        # Calculate adjusted timeout
        timeout = base_timeout * factor
        
        # Ensure minimum reasonable timeout (at least 1 second)
        return max(1.0, timeout)
    
    def get_backoff_delay(self, attempt: int, error_type: str = None) -> float:
        """
        Calculate backoff delay for retries
        
        Args:
            attempt: Current attempt number (0-indexed)
            error_type: Type of error for contextual adjustment
            
        Returns:
            Backoff delay in seconds
        """
        # Base delay and factor
        base_delay = 2.0
        factor = 2.0
        
        # Adjust based on error type if needed
        error_factors = {
            'network': 1.5,  # Network errors get a bit more time
            'timeout': 1.2,  # Timeout errors get a bit more time
            'default': 1.0
        }
        
        if error_type in error_factors:
            factor *= error_factors[error_type]
        
        # Calculate exponential backoff
        delay = base_delay * (factor ** attempt)
        
        # Add small random jitter to avoid thundering herd
        jitter_factor = 0.1
        jitter = delay * jitter_factor * (2 * random.random() - 1)  # Random value between -jitter_factor and +jitter_factor
        
        # Apply jitter
        delay += jitter
        
        # Ensure minimum reasonable delay (at least 1 second)
        return max(1.0, delay)
    
    def initialize_worker(self):
        """
        Initialize a worker process with optimal resource settings
        
        This method should be called at the start of each worker process
        to ensure proper resource configuration.
        """
        try:
            # Set process name for better monitoring
            try:
                import setproctitle
                setproctitle.setproctitle(f"autoau_worker_{os.getpid()}")
            except ImportError:
                pass
                
            # Set resource limits if possible
            try:
                import resource
                # Set soft limit for file descriptors
                soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
                resource.setrlimit(resource.RLIMIT_NOFILE, (min(hard, 2048), hard))
                logger.debug(f"Set file descriptor limit to {min(hard, 2048)}")
                
                # Set CPU time limit if configured (seconds)
                if 'cpu_time_limit' in self.config:
                    limit = self.config.get('cpu_time_limit')
                    resource.setrlimit(resource.RLIMIT_CPU, (limit, limit))
                    logger.debug(f"Set CPU time limit to {limit} seconds")
                    
                # Set memory limit if configured (bytes)
                if 'memory_limit_mb' in self.config:
                    memory_mb = self.config.get('memory_limit_mb')
                    bytes_limit = memory_mb * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_AS, (bytes_limit, bytes_limit))
                    logger.debug(f"Set memory limit to {memory_mb} MB")
            except (ImportError, AttributeError):
                logger.debug("Resource limiting not available on this platform")
                
            # Initialize random seed for this process
            import random
            random.seed()
            
            # Register signal handlers if needed
            import signal
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            
            logger.debug(f"Worker process {os.getpid()} initialized")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing worker process: {str(e)}")
            return False
            
    def monitor_memory_usage(self, threshold_mb=None, include_browser=True):
        """
        Monitor memory usage and determine if it exceeds threshold
        
        Args:
            threshold_mb: Memory threshold in MB (if None, use configuration)
            include_browser: Whether to include browser processes in calculation
            
        Returns:
            Tuple of (exceeds_threshold, memory_info_dict)
        """
        try:
            # Get threshold from config if not specified
            if threshold_mb is None:
                thresholds = self.config['memory_thresholds']
                threshold_mb = thresholds['cloud'] if self.monitor.in_container else thresholds['default']
            
            # Get memory metrics
            memory_metrics = self.monitor.get_memory_usage()
            process_memory_mb = memory_metrics['process_mb']
            
            # Include browser memory if requested
            browser_memory_mb = 0
            if include_browser:
                chrome_metrics = self.monitor.get_chrome_processes()
                browser_memory_mb = chrome_metrics['total_memory_mb']
            
            total_monitored_mb = process_memory_mb + browser_memory_mb
            
            # Determine threshold levels
            warning_threshold = self.config['memory_thresholds']['warning']
            critical_threshold = self.config['memory_thresholds']['critical']
            
            # Create result dictionary
            result = {
                'total_mb': total_monitored_mb,
                'process_mb': process_memory_mb,
                'browser_mb': browser_memory_mb,
                'threshold_mb': threshold_mb,
                'exceeds_threshold': total_monitored_mb > threshold_mb,
                'exceeds_warning': total_monitored_mb > warning_threshold,
                'exceeds_critical': total_monitored_mb > critical_threshold,
                'memory_percent': memory_metrics['percent']
            }
            
            # Log appropriately based on threshold
            if total_monitored_mb > critical_threshold:
                logger.critical(f"Critical memory usage: {total_monitored_mb:.1f} MB (threshold: {critical_threshold} MB)")
            elif total_monitored_mb > warning_threshold:
                logger.warning(f"High memory usage: {total_monitored_mb:.1f} MB (threshold: {warning_threshold} MB)")
            elif total_monitored_mb > threshold_mb:
                logger.warning(f"Memory usage above threshold: {total_monitored_mb:.1f} MB (threshold: {threshold_mb} MB)")
                
            return result['exceeds_threshold'], result
            
        except Exception as e:
            logger.error(f"Error monitoring memory: {str(e)}")
            return False, {'error': str(e)}
    
    def check_network_connectivity(self, url, timeout=5, retries=3):
        """
        Проверяет стабильность сетевого подключения к указанному URL
        
        Args:
            url: URL для проверки
            timeout: Таймаут ожидания ответа в секундах
            retries: Количество попыток
            
        Returns:
            bool: True если соединение стабильно, False если есть проблемы
        """
        # Определяем базовый домен для проверки
        parsed_url = urlparse(url)
        base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Сайты для проверки общего доступа к интернету
        test_urls = [
            "https://www.google.com",
            "https://www.cloudflare.com",
            base_domain
        ]
        
        success_count = 0
        total_response_time = 0
        
        for test_url in test_urls:
            for attempt in range(retries):
                try:
                    start_time = time.time()
                    response = requests.get(test_url, timeout=timeout, 
                                            headers={'User-Agent': 'Mozilla/5.0'})
                    response_time = time.time() - start_time
                    
                    if response.status_code == 200:
                        success_count += 1
                        total_response_time += response_time
                        logger.debug(f"Успешное соединение с {test_url} (время: {response_time:.2f}s)")
                        break
                    else:
                        logger.warning(f"Код ответа {response.status_code} от {test_url}")
                except requests.RequestException as e:
                    logger.warning(f"Ошибка соединения с {test_url} (попытка {attempt+1}/{retries}): {e}")
                    time.sleep(1)
        
        # Вычисляем среднее время ответа
        avg_response_time = total_response_time / success_count if success_count > 0 else 0
        
        # Проверяем стабильность соединения
        if success_count == 0:
            logger.error("Сетевое соединение отсутствует или крайне нестабильно")
            return False
        elif success_count < len(test_urls):
            logger.warning(f"Нестабильное сетевое соединение (успешно {success_count}/{len(test_urls)*retries})")
            return False
        elif avg_response_time > 2.0:  # Если среднее время ответа больше 2 секунд
            logger.warning(f"Медленное сетевое соединение (среднее время ответа: {avg_response_time:.2f}s)")
            return False
        else:
            logger.debug(f"Сетевое соединение стабильно (среднее время ответа: {avg_response_time:.2f}s)")
            return True

    def check_network_availability(self, url=None, timeout=5):
        """
        Check if network is available by testing a URL
        
        Args:
            url: URL to test (if None, use a default URL)
            timeout: Timeout in seconds
            
        Returns:
            True if network is available, False otherwise
        """
        if url is None:
            url = "https://www.google.com"
            
        try:
            import urllib.request
            
            # Use a custom opener with browser-like headers
            opener = urllib.request.build_opener(
                urllib.request.HTTPHandler(),
                urllib.request.HTTPSHandler()
            )
            
            # Add browser-like headers to avoid detection
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'no-cache'
            }
            
            opener.addheaders = [(key, value) for key, value in headers.items()]
            
            # Attempt to open the URL
            response = opener.open(url, timeout=timeout)
            
            # Check if response is successful (200 OK)
            return response.getcode() == 200
            
        except Exception as e:
            logger.debug(f"Network check failed: {str(e)}")
            return False
    
    def get_service_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status of the resource manager service
        
        Returns:
            Dictionary with resource manager status information
        """
        with self._lock:
            load_info = self.get_system_load(force_refresh=True)
            
            return {
                'timestamp': datetime.now().isoformat(),
                'load_category': self.get_load_category(),
                'time_period': self.get_time_period(),
                'load_score': load_info.get('load_score', 0),
                'cpu_percent': load_info.get('cpu_percent', 0),
                'memory_percent': load_info.get('memory_percent', 0),
                'disk_percent': load_info.get('disk_percent', 0),
                'chrome_processes': load_info.get('chrome_process_count', 0),
                'chrome_memory': load_info.get('chrome_memory_mb', 0),
                'success_rate': self.get_success_rate(),
                'error_rate': self.get_error_rate(),
                'optimal_processes': self.get_optimal_processes(),
                'system_info': self.monitor.system_info,
                'uptime_hours': (time.time() - os.path.getctime(sys.argv[0])) / 3600
            }

    def is_running_in_container(self) -> bool:
        """
        Check if the application is running in a container environment
        
        Returns:
            bool: True if running in a container
        """
        # Check for container-specific indicators
        if os.path.exists('/.dockerenv'):
            return True
            
        # Check cgroup for Docker
        try:
            with open('/proc/1/cgroup', 'rt') as f:
                return 'docker' in f.read() or 'lxc' in f.read()
        except:
            pass
            
        # Additional check for containerized environments
        try:
            return os.environ.get('CONTAINER', '').lower() in ('true', '1', 'yes')
        except:
            pass
            
        return False

    def is_running_in_github_codespace(self) -> bool:
        """
        Check if the application is running in GitHub Codespace
        
        Returns:
            bool: True if running in GitHub Codespace
        """
        # Check for GitHub Codespace environment variables
        codespace_indicators = [
            'CODESPACE_NAME',
            'GITHUB_CODESPACE_PORT_FORWARDING_DOMAIN',
            'CODESPACES'
        ]
        
        for indicator in codespace_indicators:
            if indicator in os.environ:
                return True
                
        return False

    def should_optimize_for_low_resources(self) -> bool:
        """
        Determine if the application should run in optimized mode for low resources
        
        Returns:
            bool: True if optimization is needed
        """
        # Check if explicitly set by environment
        if os.environ.get('AUTOAU_OPTIMIZE_RESOURCES', '').lower() in ('true', '1', 'yes'):
            return True
            
        # Check if running in container or Codespace
        if self.is_running_in_container() or self.is_running_in_github_codespace():
            return True
            
        # Check for low memory situation
        system_memory = psutil.virtual_memory()
        if system_memory.total < 4 * 1024 * 1024 * 1024:  # Less than 4GB total memory
            return True
            
        # Check for high memory usage
        if system_memory.percent > 80:  # More than 80% used
            return True
            
        return False

    def is_running_in_development_mode(self) -> bool:
        """
        Check if the application is running in development mode
        
        Returns:
            bool: True if in development mode
        """
        return os.environ.get('AUTOAU_DEV_MODE', '').lower() in ('true', '1', 'yes')

    def system_under_high_load(self) -> bool:
        """
        Check if the system is under high load
        
        Returns:
            bool: True if system is under high load
        """
        # Check CPU usage
        cpu_usage = psutil.cpu_percent(interval=0.1)
        if cpu_usage > 80:  # CPU usage over 80%
            return True
            
        # Check memory usage
        memory = psutil.virtual_memory()
        if memory.percent > 80:  # Memory usage over 80%
            return True
            
        return False

    def memory_usage_high(self) -> bool:
        """
        Check if memory usage is high
        
        Returns:
            bool: True if memory usage is high
        """
        memory = psutil.virtual_memory()
        return memory.percent > 70  # Memory usage over 70%

    def memory_usage_critical(self) -> bool:
        """
        Check if memory usage is at critical levels
        
        Returns:
            bool: True if memory usage is critical
        """
        memory = psutil.virtual_memory()
        return memory.percent > 85  # Memory usage over 85%

    def get_optimal_process_count(self) -> int:
        """
        Get optimal number of processes to use based on system resources
        
        Returns:
            int: Optimal process count
        """
        if self.should_optimize_for_low_resources():
            return 1  # Single process for low resources
            
        # Base on available CPU cores
        available_cores = psutil.cpu_count(logical=True)
        
        # Check memory constraints
        memory = psutil.virtual_memory()
        if memory.percent > 70:
            # Reduce process count under memory pressure
            return max(1, min(2, available_cores // 2))
            
        # Normal condition - use half available cores but at least 2
        return max(2, min(available_cores // 2, 4))

    def force_garbage_collection(self) -> None:
        """
        Force garbage collection to free memory
        """
        import gc
        gc.collect()
        
        # Additional memory optimizations
        if hasattr(sys, 'getsizeof'):
            logger.info(f"Forced garbage collection completed")

    def kill_process_by_name(self, process_name):
        """
        Завершает все процессы с указанным именем
        
        Args:
            process_name: Имя процесса для завершения
            
        Returns:
            int: Количество завершенных процессов
        """
        killed_count = 0
        
        try:
            logger.info(f"Поиск и завершение процессов '{process_name}'")
            
            # Для разных операционных систем используем разные методы
            if platform.system() == 'Windows':
                # Windows: используем taskkill
                try:
                    subprocess.run(
                        f"taskkill /F /IM {process_name}.exe", 
                        shell=True, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE
                    )
                    # Поскольку taskkill не возвращает количество завершенных процессов,
                    # придется проверить вручную
                    killed_count = 1  # считаем, что хотя бы один процесс был завершен
                except Exception as e:
                    logger.debug(f"Ошибка при завершении процессов через taskkill: {e}")
                    
            elif platform.system() == 'Darwin' or platform.system() == 'Linux':
                # macOS/Linux: используем psutil и сигналы
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        # Проверяем, соответствует ли имя процесса
                        if process_name.lower() in proc.info['name'].lower():
                            logger.debug(f"Найден процесс {process_name}: PID={proc.info['pid']}")
                            os.kill(proc.info['pid'], signal.SIGTERM)
                            killed_count += 1
                            
                            # Проверка, завершился ли процесс
                            try:
                                # Ждем короткое время и проверяем
                                time.sleep(0.5)
                                if psutil.pid_exists(proc.info['pid']):
                                    # Если не завершился, используем SIGKILL
                                    logger.debug(f"Процесс {proc.info['pid']} не ответил на SIGTERM, отправляем SIGKILL")
                                    os.kill(proc.info['pid'], signal.SIGKILL)
                            except:
                                pass  # Игнорируем ошибки при повторном завершении
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
            
            logger.info(f"Завершено {killed_count} процессов '{process_name}'")
        except Exception as e:
            logger.error(f"Ошибка при завершении процессов {process_name}: {e}")
        
        return killed_count

# Global resource manager instance
_resource_manager = None

def get_resource_manager(config: Dict[str, Any] = None) -> ResourceManager:
    """
    Get or create the global resource manager instance
    
    Args:
        config: Configuration dictionary (optional)
        
    Returns:
        ResourceManager instance
    """
    global _resource_manager
    if (_resource_manager is None):
        _resource_manager = ResourceManager(config)
    return _resource_manager
