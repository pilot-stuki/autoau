import os
import time
import logging
from multiprocessing import Pool
import psutil
import signal
import sys

import undetected_chromedriver as uc_webdriver
from datetime import datetime, timedelta
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

import app_logger
from config import Config
from random import randint
import urllib.request
from concurrent.futures import TimeoutError

config = Config()

# Logging mode
if config.get_log_file():

    if not os.path.exists('logs'):
        os.mkdir('logs')

    logger = app_logger.get_logger(__name__)
else:
    logging.basicConfig(level=logging.INFO,
                        format=f'{app_logger.get_log_format()}')
    logger = logging.getLogger()


ACCOUNTS = config.get_users()
TARGET_URL = config.get_target_url()
PERIOD = timedelta(hours=1, minutes=randint(29, 43), seconds=randint(45, 57))
MIDNIGHT = timedelta(hours=0, minutes=0, seconds=0)
TWO_AM = timedelta(hours=2, minutes=0, seconds=0)
START_DATE = datetime.now().date()
START_TIME = datetime.now().time()
STOP_TIME = datetime.strptime('02:15', '%H:%M').time()

DEFAULT_TIMEOUTS = {
    'network_check': 30,    # 30 seconds for network check
    'page_load': 60,       # 60 seconds for page load
    'element_wait': 30,    # 30 seconds for element waits
    'process': 300,        # 5 minutes for entire process
    'global': 600         # 10 minutes global timeout
}

CHROME_DRIVER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chromedriver')

def cleanup_chrome():
    """Clean up any remaining chrome processes"""
    try:
        # Find and kill chrome processes
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if 'chrome' in proc.info['name'].lower():
                    os.kill(proc.info['pid'], signal.SIGTERM)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        logger.debug("Chrome cleanup completed")
    except Exception as e:
        logger.error(f"Chrome cleanup failed: {str(e)}")


def check_network(url, max_retries=3, timeout=10):
    """Check network connectivity with exponential backoff"""
    for attempt in range(max_retries):
        try:
            # Use a custom opener to avoid caching
            opener = urllib.request.build_opener(
                urllib.request.HTTPHandler(),
                urllib.request.HTTPSHandler()
            )
            opener.addheaders = [('Cache-Control', 'no-cache')]
            response = opener.open(url, timeout=timeout)
            if response.getcode() == 200:
                logger.debug(f"Network check passed on attempt {attempt + 1}")
                return True
        except Exception as e:
            wait_time = timeout * (2 ** attempt)  # Exponential backoff
            logger.warning(f"Network check failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                logger.info(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            continue
    return False

def check_timeout(start_time, timeout, operation_name=None):
    """Check if operation has exceeded timeout"""
    if timeout is None:
        timeout = DEFAULT_TIMEOUTS['process']  # Fallback to process timeout
    elapsed = time.time() - start_time
    if elapsed > timeout:
        msg = f"Operation timed out after {elapsed:.2f}s"
        if operation_name:
            msg = f"{operation_name} {msg}"
        raise TimeoutError(msg)

def main(user_from_list, timeouts=None):
    """Main process with simplified flow matching main.bak"""
    user = user_from_list
    driver = None
    
    while True:  # Main retry loop from main.bak
        try:
            logger.info(f"User: {user[0]} | Starting process")
            
            # Setup driver with basic options like main.bak
            options = Options()
            options.add_argument('--start-maximized')
            if config.get_visibility() is False:
                options.add_argument("--headless")
            options.add_argument('--incognito')
            driver = uc_webdriver.Chrome(use_subprocess=True, options=options)
            logger.info(f'User: {user[0]} | Create web driver')
            
            # Simple page load with fixed wait like main.bak
            driver.get(TARGET_URL) 
            logger.info(f'User: {user[0]} | Go to login page')
            time.sleep(3)

            # Login with simple waits like main.bak
            btn_login = WebDriverWait(driver, 10).until(
                ec.presence_of_element_located((By.NAME, 'login')))
            time.sleep(2)
            edit_email = WebDriverWait(driver, 10).until(
                ec.presence_of_element_located((By.ID, 'email')))
            time.sleep(1)
            edit_email.send_keys(user[0])
            time.sleep(1)
            edit_pass = WebDriverWait(driver, 10).until(
                ec.presence_of_element_located((By.ID, 'password')))
            time.sleep(1)
            edit_pass.send_keys(user[1])
            time.sleep(1)
            btn_login.click()
            logger.info(f'User: {user[0]} | Logged in')
            
            # Handle admin message - simplified like main.bak
            time.sleep(3)  
            try:
                btn_close = WebDriverWait(driver, 10).until(
                    ec.presence_of_element_located((By.XPATH, '//button[text()="Close"]')))
                btn_close.click()
                logger.info(f'User: {user[0]} | Close first admin message')
            except:
                pass

            # Toggle handling with same selector as main.bak
            time.sleep(3)
            toggle_checkbox = WebDriverWait(driver, 10).until(
                ec.presence_of_element_located((By.XPATH, '//*[@id="available-now"]/div')))
                
            selector = 'div.available-now.smart-form input[name="checkbox-toggle"]'
            available_now_status = driver.execute_script(
                f"return document.querySelector('{selector}').checked"
            )
            
            if available_now_status is True:
                logger.info(f'User: {user[0]} | Toggle is enabled. Nothing to do')
            else:
                toggle_checkbox.click()
                time.sleep(2)
                btn_ok = WebDriverWait(driver, 10).until(
                    ec.presence_of_element_located((By.XPATH, '//button[text()="OK"]')))
                btn_ok.click()
                logger.info(f'User: {user[0]} | First: Change status "Available Now" to "YES"')
                time.sleep(3)

            # Refresh cycle with same timing as main.bak
            timestamp = datetime.now()
            while True:
                try:
                    time.sleep(randint(422, 838))
                    date_now = datetime.now().date()
                    now_sydney_time = config.get_current_sydney_time()
                    timestamp2 = datetime.now()
                    t_delta = timestamp2 - timestamp
                    t_delta = t_delta - timedelta(microseconds=t_delta.microseconds)
                    
                    if t_delta >= PERIOD:
                        # Reactivation logic from main.bak
                        time.sleep(4)
                        toggle_checkbox = WebDriverWait(driver, 10).until(
                            ec.presence_of_element_located((By.XPATH, '//*[@id="available-now"]/div')))
                        toggle_checkbox.click()
                        timestamp = datetime.now()
                        time.sleep(2)
                        btn_ok = WebDriverWait(driver, 10).until(
                            ec.presence_of_element_located((By.XPATH, '//button[text()="OK"]')))
                        btn_ok.click()
                        logger.info(f'User: {user[0]} | Reactivate: Change status "Available Now" to "NO"')
                        time.sleep(4)
                        toggle_checkbox.click()
                        time.sleep(2)
                        btn_ok = WebDriverWait(driver, 10).until(
                            ec.presence_of_element_located((By.XPATH, '//button[text()="OK"]')))
                        btn_ok.click()
                        logger.info(f'User: {user[0]} | Reactivate: Change status "Available Now" to "YES"')
                        time.sleep(4)
                        timestamp = datetime.now()
                        
                    elif START_DATE < date_now and now_sydney_time >= STOP_TIME:
                        # Stop cycle logic from main.bak
                        logger.info(f'User: {user[0]} | Stop cycle by timing.')
                        toggle_checkbox = WebDriverWait(driver, 10).until(
                            ec.presence_of_element_located((By.XPATH, '//*[@id="available-now"]/div')))
                        toggle_checkbox.click()
                        time.sleep(2)
                        btn_ok = WebDriverWait(driver, 10).until(
                            ec.presence_of_element_located((By.XPATH, '//button[text()="OK"]')))
                        btn_ok.click()
                        break
                        
                    else:
                        # Regular refresh with error handling from main.bak
                        driver.refresh()
                        if '<h1>Whoops, looks like something went wrong.</h1>' in driver.page_source:
                            time.sleep(1)
                            driver.get('https://scarletblue.com.au/members-area/')
                            logger.info(f'User: {user[0]} | Bypass "Whoops!" page. It`s OK')
                        
                        time.sleep(8)
                        try:
                            btn_close = WebDriverWait(driver, 10).until(
                                ec.presence_of_element_located((By.XPATH, '//button[text()="Close"]')))
                            time.sleep(1)
                            btn_close.click()
                            logger.info(f'User: {user[0]} | Close admin message')
                        except:
                            pass
                        logger.info(f'User: {user[0]} | Refreshing page done')
                        
                except Exception as e:
                    logger.warning(f'User: {user[0]} | Error in refresh cycle: {str(e)}')
                    continue
            
            # Final cleanup like main.bak
            if driver:
                driver.quit()
            logger.info(f'User: {user[0]} | Process completed successfully')
            break
            
        except Exception as e:
            logger.error(f'User: {user[0]} | Error: {str(e)}')
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            cleanup_chrome()
            time.sleep(5)  # Brief pause before retry
            continue

def setup_driver(user_email, timeout):
    """Setup webdriver with proper path handling"""
    start_time = time.time()
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            options = Options()
            options.add_argument('--start-maximized')
            if config.get_visibility() is False:
                options.add_argument("--headless")
            options.add_argument('--incognito')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            # Use local chromedriver with proper path
            driver = uc_webdriver.Chrome(
                use_subprocess=True,
                options=options,
                driver_executable_path=CHROME_DRIVER_PATH,
                version_main=None,
                browser_executable_path="/usr/bin/google-chrome"  # Explicitly set Chrome path
            )
            
            # Verify driver is responsive
            driver.get('about:blank')
            driver.current_url  # Test connection
            
            if time.time() - start_time > timeout:
                raise TimeoutError("Driver setup timed out")
                
            return driver
            
        except Exception as e:
            logger.error(f"Driver setup attempt {attempt + 1} failed for {user_email}: {str(e)}")
            try:
                if 'driver' in locals():
                    driver.quit()
            except:
                pass
            cleanup_chrome(user_email)
            
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff
    
    raise Exception("Failed to initialize driver after max retries")

def perform_login(driver, user, timeout):
    """Perform login with timeout handling"""
    try:
        btn_login_start = time.time()
        btn_login = WebDriverWait(driver, timeout).until(
            ec.presence_of_element_located((By.NAME, 'login')))
        time.sleep(2)
        edit_email_start = time.time()
        edit_email = WebDriverWait(driver, timeout).until(
            ec.presence_of_element_located((By.ID, 'email')))
        time.sleep(1)
        edit_email.send_keys(user[0])
        time.sleep(1)
        edit_pass_start = time.time()
        edit_pass = WebDriverWait(driver, timeout).until(
            ec.presence_of_element_located((By.ID, 'password')))
        time.sleep(1)
        edit_pass.send_keys(user[1])
        time.sleep(1)
        btn_login.click()
        logger.info(f'User: {user[0]} | Logged in')
        return True
    except Exception as e:
        logger.error(f"User: {user[0]} | Login failed: {str(e)}")
        return False

def handle_toggle(driver, user_email, timeout):
    """Handle toggle operation with clear success signals"""
    try:
        # Initial wait reduced
        time.sleep(2)
        
        # Handle admin message if present
        try:
            btn_close = WebDriverWait(driver, 2).until(
                ec.element_to_be_clickable((By.XPATH, '//button[text()="Close"]'))
            )
            btn_close.click()
            logger.info(f'User: {user_email} | Closed admin message')
            time.sleep(1)
        except:
            pass
        
        # Get toggle state using JavaScript
        selector = 'div.available-now.smart-form input[name="checkbox-toggle"]'
        toggle_element = WebDriverWait(driver, timeout).until(
            ec.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        
        # Check current state
        is_checked = driver.execute_script(
            f"return document.querySelector('{selector}').checked"
        )
        
        if is_checked:
            logger.info(f'User: {user_email} | Toggle already enabled')
            return True  # Immediate success return
        
        # Toggle needs to be enabled
        logger.info(f'User: {user_email} | Enabling toggle')
        
        # Use JavaScript click for more reliability
        driver.execute_script("arguments[0].click();", toggle_element)
        time.sleep(1)
        
        # Handle OK button
        btn_ok = WebDriverWait(driver, timeout).until(
            ec.element_to_be_clickable((By.XPATH, '//button[text()="OK"]'))
        )
        btn_ok.click()
        time.sleep(1)
        
        # Verify final state
        final_state = driver.execute_script(
            f"return document.querySelector('{selector}').checked"
        )
        
        if final_state:
            logger.info(f"User: {user_email} | Toggle successfully enabled")
            return True
        else:
            raise Exception("Toggle state verification failed")
        
    except Exception as e:
        logger.error(f"User: {user_email} | Toggle operation failed: {str(e)}")
        return False

def handle_refresh_cycle(driver, user_email, timeouts):
    """Handle refresh cycle with timeout handling"""
    timestamp = datetime.now()
    try:
        while True:
            time.sleep(randint(422, 838))
            date_now = datetime.now().date()
            now_sydney_time = config.get_current_sydney_time()
            timestamp2 = datetime.now()
            t_delta = timestamp2 - timestamp
            t_delta = t_delta - timedelta(microseconds=t_delta.microseconds)
            
            if t_delta >= PERIOD:
                # Toggle OFF
                toggle_checkbox = WebDriverWait(driver, timeouts['element_wait']).until(
                    ec.element_to_be_clickable((By.XPATH, '//*[@id="available-now"]/div'))
                )
                toggle_checkbox.click()
                timestamp = datetime.now()
                time.sleep(2)
                
                btn_ok = WebDriverWait(driver, timeouts['element_wait']).until(
                    ec.element_to_be_clickable((By.XPATH, '//button[text()="OK"]'))
                )
                btn_ok.click()
                logger.info(f'User: {user_email} | Change status "Available Now" to "NO"')
                time.sleep(4)
                
                # Toggle ON
                toggle_checkbox.click()
                logger.info(f'User: {user_email} | Change status "Available Now" to "YES"')
                time.sleep(2)
                
                btn_ok = WebDriverWait(driver, timeouts['element_wait']).until(
                    ec.element_to_be_clickable((By.XPATH, '//button[text()="OK"]'))
                )
                btn_ok.click()
                time.sleep(4)
                
                timestamp = datetime.now()
                logger.info(f'User: {user_email} | Reactivate - OK')
                
            elif (START_DATE < date_now and now_sydney_time >= STOP_TIME) or \
                 (START_DATE == date_now and START_TIME >= MIDNIGHT and \
                  START_TIME <= TWO_AM and now_sydney_time >= STOP_TIME):
                logger.info(f'User: {user_email} | Stop cycle by timing.')
                
                # Final toggle OFF before stopping
                toggle_checkbox = WebDriverWait(driver, timeouts['element_wait']).until(
                    ec.element_to_be_clickable((By.XPATH, '//*[@id="available-now"]/div'))
                )
                toggle_checkbox.click()
                time.sleep(2)
                
                btn_ok = WebDriverWait(driver, timeouts['element_wait']).until(
                    ec.element_to_be_clickable((By.XPATH, '//button[text()="OK"]'))
                )
                btn_ok.click()
                
                # Logout process
                btn_logout = WebDriverWait(driver, timeouts['element_wait']).until(
                    ec.element_to_be_clickable((By.XPATH, '//*[@id="sb-navigation"]/ul/li/a[text()="Logout"]'))
                )
                btn_logout.click()
                logger.info(f'User: {user_email} | Logged out')
                
                # Handle final admin message
                time.sleep(4)
                msg_agree = WebDriverWait(driver, timeouts['element_wait']).until(
                    ec.element_to_be_clickable((By.XPATH, '//*[@class="terms-and-conditions__enter-link"]'))
                )
                msg_agree.click()
                logger.info(f'User: {user_email} | Agreeing with admin message on home page')
                time.sleep(2)
                
                break
                
            else:
                # Regular page refresh cycle
                driver.refresh()
                page = driver.page_source
                
                # Handle "Whoops" error page
                if '<h1>Whoops, looks like something went wrong.</h1>' in page:
                    time.sleep(1)
                    driver.get('https://scarletblue.com.au/members-area/')
                    logger.info(f'User: {user_email} | Bypass "Whoops!" page. It`s OK')
                
                # Handle regular admin message
                time.sleep(4)
                try:
                    btn_close = WebDriverWait(driver, timeouts['element_wait']).until(
                        ec.element_to_be_clickable((By.XPATH, '//button[text()="Close"]'))
                    )
                    time.sleep(1)
                    btn_close.click()
                    logger.info(f'User: {user_email} | Close admin message')
                except:
                    pass
                    
                logger.info(f'User: {user_email} | Refreshing page done')
                
    except Exception as e:
        logger.warning(f'User: {user_email} | Error in refresh cycle: {str(e)}')
        return False
        
    return True

# Add custom exception
class NetworkError(Exception):
    pass


if __name__ == '__main__':
    processes = len(ACCOUNTS)
    pool = Pool(processes)
    pool.map(main, ACCOUNTS)
