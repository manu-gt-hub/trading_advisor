
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from web_scrapper import *

def test_get_trading_view_opinion():
    symbol = "AAPL"
    opinion = get_trading_view_opinion(symbol)

    assert isinstance(opinion, str), "Expected opinion as string"
    assert any(word in opinion for word in ["BUY", "SELL", "NEUTRAL"]), "Opinion does not contain expected keywords"
