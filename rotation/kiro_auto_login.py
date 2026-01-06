"""
Kiro Auto Login via Selenium
Based on droid_new/autoclicker/register.py
"""
import os
import sys
import time
import subprocess
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

CHROME_DEBUG_PORT = 9222


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def get_chrome_driver():
    options = webdriver.ChromeOptions()
    options.add_experimental_option('debuggerAddress', f'127.0.0.1:{CHROME_DEBUG_PORT}')
    return webdriver.Chrome(options=options)


def start_chrome_if_needed():
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', CHROME_DEBUG_PORT))
    sock.close()
    
    if result != 0:
        log(f"Starting Chrome on port {CHROME_DEBUG_PORT}...")
        subprocess.Popen([
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            f"--remote-debugging-port={CHROME_DEBUG_PORT}",
            "--user-data-dir=/tmp/kiro_chrome_profile",
            "--no-first-run", "--no-default-browser-check",
            "--window-size=1440,900", "about:blank"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)


def handle_chrome_popup(driver):
    """Handle Chrome 'Sign in to Chrome?' popup via Shadow DOM."""
    if "chrome://" not in driver.current_url:
        return False
    try:
        log(f"Chrome popup: {driver.current_url}")
        result = driver.execute_script('''
            var app = document.querySelector('managed-user-profile-notice-app');
            if (app && app.shadowRoot) {
                var btns = app.shadowRoot.querySelectorAll('cr-button');
                for (var b of btns) {
                    if (b.textContent.toLowerCase().includes('without')) {
                        b.click();
                        return 'clicked';
                    }
                }
            }
            return 'none';
        ''')
        log(f"Popup result: {result}")
        time.sleep(2)
        return result == 'clicked'
    except Exception as e:
        log(f"Popup error: {e}")
    return False


def switch_to_oauth_window(driver):
    for h in driver.window_handles:
        driver.switch_to.window(h)
        if 'accounts.google' in driver.current_url:
            return True
    return False


def do_google_oauth(driver, email: str, password: str) -> bool:
    wait = WebDriverWait(driver, 15)
    
    try:
        # Click Google button
        if "kiro.dev" in driver.current_url:
            try:
                btn = driver.find_element(By.XPATH, '//*[contains(text(),"Google")]')
                btn.click()
                log("Clicked Google")
                time.sleep(3)
            except:
                pass
        
        # Enter email
        email_input = wait.until(EC.presence_of_element_located((
            By.CSS_SELECTOR, "input[type='email'], input#identifierId"
        )))
        email_input.clear()
        email_input.send_keys(email)
        driver.find_element(By.ID, "identifierNext").click()
        log(f"Email: {email}")
        time.sleep(3)
        
        # Enter password
        pwd_input = wait.until(EC.presence_of_element_located((
            By.CSS_SELECTOR, "input[type='password'], input[name='Passwd']"
        )))
        pwd_input.send_keys(password)
        driver.find_element(By.ID, "passwordNext").click()
        log("Password entered")
        time.sleep(4)
        
        # Handle Chrome popup
        if "chrome://" in driver.current_url:
            handle_chrome_popup(driver)
            switch_to_oauth_window(driver)
        
        # Click Continue on consent
        for _ in range(5):
            time.sleep(2)
            url = driver.current_url
            
            if "localhost" in url or ("kiro.dev" in url and "error" not in url):
                log("SUCCESS")
                return True
            
            try:
                driver.find_element(By.XPATH, '//button[contains(.,"Continue")]').click()
                log("Clicked Continue")
            except:
                pass
        
        return "localhost" in driver.current_url
        
    except Exception as e:
        log(f"OAuth error: {e}")
        return False


def kiro_login(email: str, password: str) -> bool:
    """Login to Kiro via Google OAuth."""
    log(f"Kiro login: {email}")
    
    start_chrome_if_needed()
    driver = get_chrome_driver()
    
    try:
        driver.get("https://app.kiro.dev/signin")
        time.sleep(2)
        return do_google_oauth(driver, email, password)
    except Exception as e:
        log(f"Error: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python kiro_auto_login.py <email> <password>")
        sys.exit(1)
    
    success = kiro_login(sys.argv[1], sys.argv[2])
    sys.exit(0 if success else 1)
