
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))

# DEPRECATED DUE TO CAPTCHAS
# TODO: with investing it has tu run in no-headless mode
# Test for the get_investing_opinion function
# def test_get_investing_opinion():
#     symbol = "MSFT"  # You can change this to test other symbols as well
#     opinion = get_investing_opinion(symbol)

#     # Assert that the opinion is a string
#     assert isinstance(opinion, str), "Expected opinion as string"
    
#     # Check if the opinion contains expected phrases (could be 'Strong Buy', 'Buy', etc.)
#     expected_keywords = ["Strong Buy", "Buy", "Sell", "Strong Sell", "Hold", "Neutral"]
#     assert any(keyword in opinion for keyword in expected_keywords), "Opinion does not contain expected keywords"

# TODO: trading view has implemented captchas

# def test_get_trading_view_opinion():
#     symbol = "MSFT"
#     opinion = get_trading_view_opinion(symbol)

#     assert isinstance(opinion, str), "Expected opinion as string"
#     assert any(word in opinion for word in ["BUY", "SELL", "NEUTRAL"]), "Opinion does not contain expected keywords"
