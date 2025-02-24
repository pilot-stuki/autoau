#!/usr/bin/env python3
import os
import sys
import signal
import logging
from logging.handlers import RotatingFileHandler
import traceback
from itertools import chain
from concurrent.futures import ThreadPoolExecutor
import time  # Import time module directly
from multiprocessing import TimeoutError, Pool
import threading
from random import randint
from datetime import datetime, timedelta
import shutil
import glob
from typing import Set, Dict
import psutil
from selenium.common.exceptions import WebDriverException, TimeoutException
from functools import wraps
from time import sleep  # Add explicit import for sleep
import random  # Add for random batch sizes

# Make paths absolute for systemd
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logging():
    """Setup logging with proper paths and permissions"""
    try:
        # Ensure log directory exists and has proper permissions
        os.makedirs(LOG_DIR, exist_ok=True)
        os.chmod(LOG_DIR, 0o755)
        
        log_file = os.path.join(LOG_DIR, 'service.log')
        
        # Create logger
        logger = logging.getLogger('service')
        logger.setLevel(logging.DEBUG)  # Enable debug for startup
        
        # File handler with absolute path
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,
            backupCount=5
        )
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
        
        # Console handler for systemd
        console_handler = logging.StreamHandler(sys.stdout)  # Use stdout for systemd
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(console_handler)
        
        # Test write access
        logger.info("Logging system initialized")
        return logger
        
    except Exception as e:
        sys.stderr.write(f"Failed to initialize logging: {str(e)}\n")
        sys.exit(1)

# Initialize logging first
try:
    # Clear existing handlers
    root = logging.getLogger()
    if (root.handlers):
        for handler in root.handlers:
            root.removeHandler(handler)
            
    service_logger = setup_logging()
    service_logger.info(f"Starting service from {BASE_DIR}")
    
except Exception as e:
    sys.stderr.write(f"Critical startup error: {str(e)}\n")
    sys.exit(1)

# Safe imports with detailed error logging
try:
    sys.path.append(BASE_DIR)  # Ensure import path is correct
    from main import main, cleanup_chrome, ACCOUNTS
    service_logger.info("Successfully imported main module")
except Exception as e:
    service_logger.critical(f"Failed to import required modules: {str(e)}\n{traceback.format_exc()}")
    sys.exit(1)

def init_worker():
    """Initialize worker process"""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    service_logger.info(f"Worker process started: {os.getpid()}")

def signal_handler(signum, frame):
    """Handle termination signals"""
    service_logger.info(f"Received signal {signum}, initiating shutdown...")
    cleanup_chrome()
    sys.exit(0)

def check_system_resources():
    """Check if system has enough resources"""
    mem = psutil.virtual_memory()
    if (mem.available < 1024 * 1024 * 1024):  # 1GB
        service_logger.error("Not enough memory available")
        return False
    return True

def chunk_accounts(accounts, size=None):
    """Split accounts into random-sized chunks"""
    if size is None:
        size = random.randint(2, 4)
    for i in range(0, len(accounts), size):
        yield accounts[i:i + min(size, len(accounts))]

# Debug mode and timeout configurations
DEBUG_MODE = True

# Update timeout configurations
if DEBUG_MODE:
    TIMEOUTS = {
        'network_check': 30,    # 30s network check
        'page_load': 45,       # 45s page load
        'element_wait': 20,    # 20s element wait
        'process': 120,       # 2min per account process
        'batch': 180,        # 3min batch timeout (increased from 15s)
        'cycle': 1800       # 30min cycle
    }
    
    # Add cycle delay configuration
    CYCLE_DELAYS = {
        'success': 300,    # 5min if all succeeded
        'partial': 600,    # 10min if some failed
        'failure': 900     # 15min if all failed
    }
    
    BATCH_SIZE = 3
    MAX_RETRIES = 2
    RETRY_DELAYS = [5, 10]
else:
    TIMEOUTS = {
        'network_check': 30,    # 30 seconds for network check
        'page_load': 60,       # 60 seconds for page load
        'element_wait': 30,    # 30 seconds for element waits
        'process': 300,       # 5 minutes per process
        'batch': 600,        # 10 minutes per batch
        'account': 300,      # 5 minutes per account
        'cycle': 900,       # 15 minutes per cycle
        'global': 1800      # 30 minutes global timeout
    }
    BATCH_SIZE = random.randint(2, 4)  # Random batch size
    MAX_RETRIES = 3
    RETRY_DELAYS = [30, 60, 120]
    INTER_BATCH_DELAY = random.randint(300, 600)  # 5-10 minutes

MIN_PROCESS_TIMEOUT = 300  # Increase to 5 minutes minimum
DEFAULT_PROCESS_TIMEOUT = 600  # Increase to 10 minutes default
MAX_CYCLES = 0  # 0 means run indefinitely

FAILED_ACCOUNTS: Set[str] = set()
ACCOUNT_LOCKS: Dict[str, threading.Lock] = {}

def cleanup_zombie_processes():
    """Clean up any zombie Chrome processes"""
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if 'chrome' in proc.info['name'].lower():
                try:
                    proc.kill()
                except:
                    pass
    except Exception as e:
        service_logger.error(f"Error cleaning zombie processes: {str(e)}")

def get_random_timeouts():
    """Get randomized timeouts with increased minimums"""
    return {
        'batch': randint(300, 600),      # 5-10 minutes
        'inter_batch': randint(60, 120),  # 1-2 minutes
        'process': randint(MIN_PROCESS_TIMEOUT, DEFAULT_PROCESS_TIMEOUT),  # 5-10 minutes
        'cycle': randint(600, 900)       # 10-15 minutes
    }

def archive_logs():
    """Archive logs older than 7 days"""
    try:
        archive_dir = os.path.join(BASE_DIR, 'logs', 'archive')
        os.makedirs(archive_dir, exist_ok=True)
        
        # Get current date for comparison
        current_date = datetime.now()
        
        # Check all log files
        log_files = glob.glob(os.path.join(BASE_DIR, 'logs', '*.log*'))
        for log_file in log_files:
            # Get file modification time
            mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
            days_old = (current_date - mtime).days
            
            # Archive files older than 7 days
            if days_old > 7:
                archive_name = f"{os.path.basename(log_file)}.{mtime.strftime('%Y%m%d')}"
                archive_path = os.path.join(archive_dir, archive_name)
                
                # Compress and move to archive
                try:
                    shutil.copy2(log_file, archive_path)
                    os.remove(log_file)
                    service_logger.info(f"Archived log file: {archive_name}")
                except Exception as e:
                    service_logger.error(f"Failed to archive {log_file}: {str(e)}")
                    
    except Exception as e:
        service_logger.error(f"Log archival error: {str(e)}")

def get_system_metrics():
    """Get current system resource usage"""
    try:
        mem = psutil.virtual_memory()
        chrome_count = len([p for p in psutil.process_iter(['name']) 
                          if 'chrome' in p.info['name'].lower()])
        python_count = len([p for p in psutil.process_iter(['name']) 
                          if 'python' in p.info['name'].lower()])
        return {
            'memory_percent': mem.percent,
            'chrome_processes': chrome_count,
            'python_processes': python_count
        }
    except Exception as e:
        service_logger.error(f"Error getting metrics: {str(e)}")
        return {}

def log_diagnostics(phase: str, account_email: str = None):
    """Log diagnostic information at key points"""
    metrics = get_system_metrics()
    msg = (f"DIAGNOSTIC [{phase}] "
           f"Memory: {metrics.get('memory_percent')}%, "
           f"Chrome: {metrics.get('chrome_processes')}, "
           f"Python: {metrics.get('python_processes')}")
    if account_email:
        msg += f", Account: {account_email}"
    service_logger.info(msg)

def is_time_between(check_time, start_time, end_time):
    """Check if current time is between start and end times"""
    if start_time <= end_time:
        return start_time <= check_time <= end_time
    else:  # crosses midnight
        return check_time >= start_time or check_time <= end_time

def get_next_run_time(current_time, interval_minutes=60):
    """Calculate next run time with proper datetime handling"""
    return current_time + timedelta(minutes=interval_minutes)

def timeout_handler(signum, frame):
    raise TimeoutError("Processing timed out")

def process_with_timeout(timeout=30):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Set the timeout handler
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            try:
                result = func(*args, **kwargs)
                signal.alarm(0)  # Disable alarm
                return result
            except TimeoutError:
                user = args[0] if args else "Unknown"
                service_logger.error(f"Timeout: {user[0]}", exc_info=True)
                raise
            finally:
                signal.alarm(0)  # Ensure alarm is disabled
        return wrapper
    return decorator

def run_account(user, max_attempts=3):
    attempt = 1
    while attempt <= max_attempts:
        try:
            service_logger.info(f"Starting {user[0]} (Attempt {attempt})")
            process_with_timeout(timeout=30)(main)(user)
            break
        except TimeoutError:
            service_logger.error(f"Timeout: {user[0]}")
            cleanup_chrome()  # Clean up after timeout
            attempt += 1
        except Exception as e:
            service_logger.error(f"Error processing {user[0]}:", exc_info=True)
            cleanup_chrome()
            attempt += 1
            
    if attempt > max_attempts:
        service_logger.error(f"Max attempts ({max_attempts}) reached for {user[0]}")

def process_single_account(user, timeout):
    """Process single account with simplified state tracking"""
    account_email = user[0]
    start_time = time.time()
    attempts = 0
    max_attempts = 3
    
    try:
        while attempts < max_attempts:
            service_logger.info(f"Processing {account_email} (Attempt {attempts + 1}/{max_attempts})")
            
            try:
                result = main(user)
                if result is True:
                    service_logger.info(f"Success: {account_email}")
                    return "SUCCESS"
                    
                attempts += 1
                if attempts < max_attempts:
                    service_logger.warning(f"Retry {attempts}/{max_attempts} for {account_email}")
                    cleanup_chrome()
                    time.sleep(5 * attempts)
                else:
                    service_logger.error(f"Max retries reached for {account_email}")
                    return "FAILED"
                    
            except Exception as e:
                if "Toggle already enabled" in str(e):
                    service_logger.info(f"Already enabled for {account_email}")
                    return "SUCCESS"
                    
                attempts += 1
                if attempts < max_attempts:
                    service_logger.warning(f"Error for {account_email}, retry {attempts}: {str(e)}")
                    cleanup_chrome()
                    time.sleep(5 * attempts)
                else:
                    service_logger.error(f"Failed after {max_attempts} attempts: {account_email}")
                    return "FAILED"
                    
    except Exception as e:
        service_logger.error(f"Critical error for {account_email}: {str(e)}")
        return "FAILED"
    finally:
        cleanup_chrome()

def process_batch(batch, batch_num, total_batches, timeouts):
    """Process batch with simplified tracking"""
    batch_start = time.time()
    completed = []
    failed = []
    
    try:
        service_logger.info(f"=== Starting Batch {batch_num + 1}/{total_batches} ===")
        service_logger.info(f"Batch size: {len(batch)}")
        
        with Pool(min(3, len(batch))) as pool:
            # Start all processes
            results = []
            for user in batch:
                result = pool.apply_async(process_single_account, 
                                       (user, timeouts['process']))
                results.append((user, result))
            
            # Wait for results
            for user, result in results:
                try:
                    status = result.get(timeout=timeouts['process'])
                    if status == "SUCCESS":
                        completed.append(user)
                        service_logger.info(f"Completed: {user[0]}")
                    else:
                        failed.append(user)
                        service_logger.error(f"Failed: {user[0]}")
                except TimeoutError:
                    failed.append(user)
                    service_logger.error(f"Timeout: {user[0]}")
                except Exception as e:
                    failed.append(user)
                    service_logger.error(f"Error processing {user[0]}: {str(e)}")
            
            # Clean final state
            pool.close()
            pool.join()
            
    except Exception as e:
        service_logger.error(f"Batch error: {str(e)}")
        failed.extend([u for u, _ in results if u not in completed])
    finally:
        cleanup_chrome()
        
        elapsed = time.time() - batch_start
        service_logger.info(f"""
        === Batch {batch_num + 1} Summary ===
        Completed: {len(completed)}/{len(batch)}
        Failed: {len(failed)}/{len(batch)}
        Duration: {elapsed:.1f}s
        """)
    
    return completed, failed

def run_service():
    """Main service loop with improved state management"""
    cycle = 0
    
    try:
        while True:
            cycle += 1
            cycle_start = datetime.now()
            
            service_logger.info(f"Starting cycle {cycle} at {cycle_start}")
            cleanup_chrome()
            
            # Process in smaller batches
            batch_size = 3  # Process 3 accounts at a time
            batches = list(chunk_accounts(ACCOUNTS, batch_size))
            
            cycle_completed = []
            cycle_failed = []
            
            for batch_num, batch in enumerate(batches):
                completed, failed = process_batch(batch, batch_num, len(batches), TIMEOUTS)
                cycle_completed.extend(completed)
                cycle_failed.extend(failed)
                
                # Only delay if there were failures
                if failed and batch_num < len(batches) - 1:
                    time.sleep(30)  # 30s delay between batches on failure
            
            # Calculate next cycle delay based on success rate
            success_rate = len(cycle_completed) / len(ACCOUNTS)
            if success_rate == 1.0:
                next_delay = 300  # 5min on full success
            elif success_rate == 0:
                next_delay = 900  # 15min on full failure
            else:
                next_delay = 600  # 10min on partial success
                
            service_logger.info(f"""
            === Cycle {cycle} Complete ===
            Success Rate: {success_rate:.1%}
            Next Delay: {next_delay}s
            """)
            
            time.sleep(next_delay)
            
    except KeyboardInterrupt:
        service_logger.info("Service stopped by user")
    except Exception as e:
        service_logger.critical(f"Service error: {str(e)}")
        return 1

def run_with_timeout(user, timeout):
    start_time = time()
    try:
        service_logger.info(f"Starting {user[0]} (Attempt 1)")
        main(user)
    except Exception as e:
        elapsed_time = time() - start_time
        if elapsed_time >= timeout:
            service_logger.error(f"Timeout: {user[0]}")
        service_logger.error(f"Error processing {user[0]}: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    try:
        run_service()
    except KeyboardInterrupt:
        service_logger.info("Service stopped by user")
        cleanup_chrome()
    except Exception as e:
        service_logger.critical(f"Service crashed: {str(e)}", exc_info=True)
        cleanup_chrome()
