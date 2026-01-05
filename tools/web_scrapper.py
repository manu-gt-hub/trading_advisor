import os
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import logging
from tools.general import get_mapping_string

logger = logging.getLogger(__name__)

if not os.getenv("GITHUB_ACTIONS"):  # This var is auto-set in GitHub Actions
    load_dotenv()

# Suppress SSL warnings from requests
requests.packages.urllib3.disable_warnings()

# Get HTML content using Selenium (headless Chrome)
def get_html(urls):
    """
    Fetches the HTML content of the given URLs using Selenium (headless mode).
    Returns the HTML of the first successfully loaded URL or None if an error occurs.
    """
    html = None
    driver = None

    try:
        # Configure Chrome options for headless operation
        options = Options()
        options.add_argument("--headless")  # Run Chrome in headless mode
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")  # Disable GPU hardware acceleration in headless mode

        # Use ChromeDriverManager to automatically download and manage ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Set an implicit wait for elements to load
        driver.implicitly_wait(10)

        # Iterate through the list of URLs
        for url in urls:
            try:
                logger.info(f"Fetching HTML from {url}...")

                # Navigate to the URL using Selenium
                driver.get(url)

                # Add a longer wait time to ensure the page fully loads
                logger.info(f"Waiting for page to load...")
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.bg-positive-main"))  # Wait for the opinion div
                )

                # After the page has loaded, retrieve the HTML content
                html = driver.page_source
                logger.info(f"Successfully fetched HTML from {url}.")
                break  # Exit the loop after successfully fetching HTML

            except Exception as e:
                logger.error(f"❌ Error fetching HTML from {url}: {e}")
                continue  # Continue to the next URL if the current one fails

    except Exception as e:
        logger.error(f"❌ Error initializing Selenium WebDriver: {e}")
    finally:
        if driver:
            try:
                driver.quit()  # Make sure to quit the driver even if an error occurs
            except Exception as e:
                logger.error(f"❌ Error closing the Selenium driver: {e}")

    return html
