import os
import re
import tempfile
import warnings
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

if not os.getenv("GITHUB_ACTIONS"):  # This var is auto-set in GitHub Actions
    load_dotenv()

# Suppress SSL warnings from requests
requests.packages.urllib3.disable_warnings()

# Get HTML content using Selenium (headless Chrome)
def get_html(urls):
    html = None
    driver = None

    try:
        user_data_dir = tempfile.mkdtemp()

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--user-data-dir={user_data_dir}")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.implicitly_wait(10)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115 Safari/537.36"
        }

        for url in urls:
            try:
                response = requests.get(url, headers=headers, verify=False)
                if response.status_code == 200:
                    driver.get(url)
                    html = driver.page_source
                    break
            except Exception as e:
                logger.error(f"❌ Error fetching HTML from {url}: {e}")

    except Exception as e:
        logger.error(f"❌ Error initializing Selenium: {e}")
    finally:
        if driver:
            driver.quit()

    return html


# Get TradingView's technical analysis summary (Buy/Sell/Neutral)
def get_trading_view_opinion(symbol):
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
            msg = f"❌ [{symbol}] No HTML found."
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
                    continue

                top = max(data, key=lambda x: x[1])
                data.remove(top)

                main = f"{top[0].upper()} ({top[1]})"
                others = " - ".join([f"{label} ({value})" for label, value in data])
                result = f"{main} - {others}"

                logger.info(f"✅ [{symbol}] Opinion succesfully fetched: {result}")
                return result

        logger.info(f"⚠️ [{symbol}] No summary found.")

    except Exception as e:
        logger.error(f"❌ Error fetching opinion for {symbol}: {e}")
        return f"error: {e}"
