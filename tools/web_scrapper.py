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

# Get TradingView's technical analysis summary (Buy/Sell/Neutral)
def get_trading_view_opinion(symbol):
    """
    Fetch TradingView technical analysis summary (Buy/Sell/Neutral) for a given symbol.
    Returns a string with the main opinion or an "error: ..." message if unavailable.
    """
    logger.info(f"Fetching TradingView opinion for {symbol}...")

    try:
        urls = [
            f'https://en.tradingview.com/symbols/BME-{symbol}/technicals/',
            f'https://en.tradingview.com/symbols/MARKETSCOM-{symbol}/technicals/',
            f'https://en.tradingview.com/symbols/NASDAQ-{symbol}/technicals/',
            f'https://en.tradingview.com/symbols/NYSE-{symbol}/technicals/'
        ]

        html = get_html(urls)
        if not html:
            msg = f"[{symbol}] No HTML found."
            logger.error(msg)
            return f"error: {msg}"

        soup = BeautifulSoup(html, 'lxml')
        opinion_divs = soup.find_all('div', class_=lambda x: x and 'speedometerWrapper' in x)

        for div in opinion_divs:
            if 'Summary' in div.text:
                text = div.text
                matches = re.findall(r'(Sell|Neutral|Buy)(\d+)', text)
                data = [(label, int(value)) for label, value in matches]

                if not data:
                    continue  # Skip if no matches found

                # Pick the top signal
                top = max(data, key=lambda x: x[1])
                data.remove(top)

                main = f"{top[0].upper()} ({top[1]})"
                others = " - ".join([f"{label} ({value})" for label, value in data])
                result = f"{main} - {others}" if others else main

                logger.info(f"✅ [{symbol}] Opinion successfully fetched: {result}")
                return result

        # No summary found in the HTML
        msg = f"[{symbol}] No summary found on the page."
        logger.warning(msg)
        return f"error: {msg}"

    except Exception as e:
        logger.error(f"❌ Error fetching opinion for {symbol}: {e}")
        return f"error: {e}"

def get_investing_opinion(symbol):
    """
    Fetch Investing.com technical analysis opinion (e.g. Strong Buy, Buy, etc.)
    Returns a string with the main opinion or an "error: ..." message if unavailable.
    """
    mapping_string = get_mapping_string(symbol)
    url = f'https://www.investing.com/equities/{mapping_string}-technical'
    
    try:
        print(f"Fetching Investing.com opinion for {symbol}...")

        # Use get_html to fetch the HTML using Selenium (headless)
        html = get_html([url])
        if not html:
            msg = f"[{symbol}] Failed to fetch HTML."
            print(msg)
            return f"error: {msg}"

        # Parse the HTML content using BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        # Search for the div that contains the opinion (with the specific class)
        opinion_div = soup.find('div', class_='-mt-2.5 mt-1 rounded-full px-4 py-1.5 text-center font-semibold leading-5 text-white bg-positive-main')
        
        # If the div is found, extract and return the opinion text
        if opinion_div:
            opinion = opinion_div.get_text(strip=True)
            print(f"✅ [{symbol}] Opinion successfully fetched: {opinion}")
            return opinion
        else:
            msg = f"[{symbol}] No opinion found on the page."
            print(msg)
            return f"error: {msg}"

    except Exception as e:
        # Handle any exceptions and log the error
        msg = f"❌ Error fetching opinion for {symbol}: {e}"
        print(msg)
        return f"error: {msg}"