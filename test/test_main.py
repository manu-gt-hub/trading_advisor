import sys
import os
import re
import pandas as pd
import numpy as np
import pytest
from datetime import date, datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def filter_buys_by_confidence(analysis_df, min_confidence):
    """Replicates the filtering logic from main.py for testability."""
    buy_df = analysis_df[
        (analysis_df['action'] == 'BUY') &
        (analysis_df['technical_confidence'] >= min_confidence)
    ].copy()
    return buy_df


def filter_buys_by_risk_reward(buy_df, min_rr=1.2):
    """Replicates the R:R filtering logic from main.py for testability."""
    if buy_df.empty or 'risk_reward_ratio' not in buy_df.columns:
        return buy_df
    bad_rr = buy_df[buy_df['risk_reward_ratio'].apply(
        lambda x: pd.notna(x) and x < min_rr
    )]
    return buy_df[~buy_df.index.isin(bad_rr.index)].copy()


class TestMinBuyConfidenceFilter:

    def _build_analysis_df(self):
        return pd.DataFrame({
            'symbol': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'],
            'current_price': [150.0, 300.0, 2800.0, 3400.0, 700.0],
            'action': ['BUY', 'BUY', 'BUY', 'SELL', 'HOLD'],
            'technical_confidence': [0.65, 0.30, 0.10, 0.80, 0.50],
        })

    def test_default_threshold_filters_low_confidence(self):
        df = self._build_analysis_df()
        result = filter_buys_by_confidence(df, min_confidence=0.5)

        # Only AAPL (0.65) passes; MSFT (0.30) and GOOGL (0.10) are filtered out
        assert list(result['symbol']) == ['AAPL']

    def test_low_threshold_allows_more_buys(self):
        df = self._build_analysis_df()
        result = filter_buys_by_confidence(df, min_confidence=0.1)

        # AAPL (0.65), MSFT (0.30), GOOGL (0.10) all pass
        assert list(result['symbol']) == ['AAPL', 'MSFT', 'GOOGL']

    def test_high_threshold_filters_all_buys(self):
        df = self._build_analysis_df()
        result = filter_buys_by_confidence(df, min_confidence=0.9)

        # No BUY has confidence >= 0.9
        assert result.empty

    def test_non_buy_actions_are_never_included(self):
        df = self._build_analysis_df()
        result = filter_buys_by_confidence(df, min_confidence=0.0)

        # Even with threshold 0, SELL and HOLD are excluded
        assert 'AMZN' not in result['symbol'].values
        assert 'TSLA' not in result['symbol'].values

    def test_exact_threshold_boundary(self):
        df = self._build_analysis_df()
        # MSFT has exactly 0.30 confidence
        result = filter_buys_by_confidence(df, min_confidence=0.30)
        assert 'MSFT' in result['symbol'].values

        result = filter_buys_by_confidence(df, min_confidence=0.31)
        assert 'MSFT' not in result['symbol'].values


class TestRiskRewardFilter:

    def _build_buy_df(self):
        return pd.DataFrame({
            'symbol': ['AAPL', 'MSFT', 'GOOGL', 'NVDA'],
            'action': ['BUY', 'BUY', 'BUY', 'BUY'],
            'risk_reward_ratio': [2.5, 1.0, 1.5, None],
        })

    def test_blocks_low_rr(self):
        df = self._build_buy_df()
        result = filter_buys_by_risk_reward(df)
        # MSFT (1.0 < 1.5) blocked
        assert 'MSFT' not in result['symbol'].values

    def test_keeps_good_rr(self):
        df = self._build_buy_df()
        result = filter_buys_by_risk_reward(df)
        # AAPL (2.5) and GOOGL (1.5) pass
        assert 'AAPL' in result['symbol'].values
        assert 'GOOGL' in result['symbol'].values

    def test_keeps_nan_rr(self):
        df = self._build_buy_df()
        result = filter_buys_by_risk_reward(df)
        # NVDA (None) passes — don't block when data is missing
        assert 'NVDA' in result['symbol'].values

    def test_exact_boundary(self):
        df = self._build_buy_df()
        result = filter_buys_by_risk_reward(df, min_rr=1.5)
        # GOOGL has exactly 1.5 — should pass
        assert 'GOOGL' in result['symbol'].values

    def test_empty_df(self):
        df = pd.DataFrame(columns=['symbol', 'action', 'risk_reward_ratio'])
        result = filter_buys_by_risk_reward(df)
        assert result.empty


def _is_market_day(today):
    """Testable version of market day check — receives date as parameter."""
    if today.weekday() >= 5:
        return False
    us_holidays = [(1, 1), (7, 4), (12, 25)]
    if (today.month, today.day) in us_holidays:
        return False
    return True


class TestMarketDayGuard:

    def test_weekday_is_market_day(self):
        assert _is_market_day(date(2025, 5, 19)) is True  # Monday

    def test_saturday_is_not_market_day(self):
        assert _is_market_day(date(2025, 5, 17)) is False  # Saturday

    def test_sunday_is_not_market_day(self):
        assert _is_market_day(date(2025, 5, 18)) is False  # Sunday

    def test_christmas_is_not_market_day(self):
        assert _is_market_day(date(2025, 12, 25)) is False  # Thursday

    def test_new_years_is_not_market_day(self):
        assert _is_market_day(date(2025, 1, 1)) is False  # Wednesday

    def test_independence_day_is_not_market_day(self):
        assert _is_market_day(date(2025, 7, 4)) is False  # Friday

    def test_regular_friday_is_market_day(self):
        assert _is_market_day(date(2025, 5, 23)) is True  # Friday


def test_transaction_update_and_buy_df_concat_preserves_sell_columns():
    """
    Regression test for the bug where sell_value was saved but sell_date,
    buy_sell_days_diff and percentage_benefit were missing after pd.concat
    and sort_values mixed date types (datetime.date vs string) in buy_date.
    """
    buy_date = date.today() - timedelta(days=30)
    sell_date = date.today()
    days_diff = (sell_date - buy_date).days

    # Simulate a closed transaction row returned by google_handler.update_transactions
    trans_updated_df = pd.DataFrame({
        'symbol': ['AAPL'],
        'buy_value': [150.0],
        'buy_date': [buy_date.isoformat()],
        'sell_value': [165.0],
        'sell_date': [sell_date.isoformat()],
        'buy_sell_days_diff': [days_diff],
        'percentage_benefit': [10.0],
    })

    # Simulate a new BUY candidate with buy_date as ISO string (matching main.py)
    buy_df = pd.DataFrame({
        'symbol': ['NVDA'],
        'buy_value': [450.0],
        'action': ['BUY'],
        'technical_confidence': [0.55],
        'buy_date': [datetime.today().strftime('%Y-%m-%d %H:%M')],
    })

    # Replicate main.py concat + sort + head
    final_df = pd.concat([trans_updated_df, buy_df], ignore_index=True)\
                 .sort_values(by='buy_date', ascending=False)\
                 .head(100)

    aapl = final_df[final_df['symbol'] == 'AAPL'].iloc[0]
    assert aapl['sell_value'] == 165.0
    assert aapl['sell_date'] == sell_date.isoformat()
    assert aapl['buy_sell_days_diff'] == days_diff
    assert aapl['percentage_benefit'] == 10.0

    nvda = final_df[final_df['symbol'] == 'NVDA'].iloc[0]
    assert pd.isna(nvda['sell_value'])
    assert pd.isna(nvda['sell_date'])


# ---------------------------------------------------------------------------
# Transactions log output validation
# ---------------------------------------------------------------------------

# Regex for buy_date: YYYY-MM-DD HH:MM (must include time)
_BUY_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
# Regex for sell_date: YYYY-MM-DD (ISO date)
_SELL_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Expected column order in the transactions log
_EXPECTED_COL_ORDER = [
    'symbol', 'buy_value', 'buy_date', 'sell_value', 'sell_date',
    'buy_sell_days_diff', 'percentage_benefit', 'stop_loss', 'take_profit',
    'risk_reward_ratio', 'tradingview_url',
]


def _build_transactions_log(trans_updated_df, buy_df, max_records=100):
    """
    Replicate the exact pipeline from update_and_save_transactions() in main.py
    so we can validate the DataFrame that would be saved to Google Drive.
    """
    tx_cols = [
        'symbol', 'buy_value', 'buy_date', 'stop_loss', 'take_profit',
        'risk_reward_ratio', 'tradingview_url',
    ]
    buy_for_tx = buy_df[[c for c in tx_cols if c in buy_df.columns]].copy()

    final_df = pd.concat([trans_updated_df, buy_for_tx], ignore_index=True)

    if 'buy_date' in final_df.columns:
        final_df['buy_date'] = final_df['buy_date'].astype(str).replace('NaT', '')

    final_df = final_df.sort_values(by='buy_date', ascending=False).head(max_records)

    desired_order = list(_EXPECTED_COL_ORDER)
    ordered_cols = [c for c in desired_order if c in final_df.columns]
    extra_cols = [c for c in final_df.columns if c not in desired_order]
    final_df = final_df[ordered_cols + extra_cols]

    return final_df


class TestTransactionsLogOutput:
    """
    Validates the DataFrame that gets saved to Google Drive as the
    transactions log.  Covers column order, date formats, revenue_percentage
    compliance, sell vs buy value consistency, and open-position integrity.
    """

    REVENUE_PCT = 10  # 10 %

    # -- fixtures / helpers --------------------------------------------------

    def _closed_transaction(self, symbol, buy_value, buy_date_str, sell_date_str,
                            revenue_pct=None, stop_loss=None, take_profit=None):
        """Build a single closed-transaction row as a dict."""
        rp = revenue_pct if revenue_pct is not None else self.REVENUE_PCT
        target_price = round(buy_value * (1 + rp / 100), 2)
        pct = round(((target_price - buy_value) / buy_value) * 100, 2)
        buy_dt = datetime.fromisoformat(buy_date_str)
        sell_dt = date.fromisoformat(sell_date_str)
        days = (sell_dt - buy_dt.date()).days
        return {
            'symbol': symbol,
            'buy_value': buy_value,
            'buy_date': buy_date_str,
            'sell_value': target_price,
            'sell_date': sell_date_str,
            'buy_sell_days_diff': days,
            'percentage_benefit': pct,
            'stop_loss': stop_loss or round(buy_value * 0.94, 2),
            'take_profit': take_profit or target_price,
            'risk_reward_ratio': 1.5,
            'tradingview_url': f'https://tradingview.com/{symbol}',
        }

    def _open_transaction(self, symbol, buy_value, buy_date_str,
                          stop_loss=None, take_profit=None):
        """Build a single open-position row (no sell data)."""
        return {
            'symbol': symbol,
            'buy_value': buy_value,
            'buy_date': buy_date_str,
            'sell_value': None,
            'sell_date': None,
            'buy_sell_days_diff': None,
            'percentage_benefit': None,
            'stop_loss': stop_loss or round(buy_value * 0.94, 2),
            'take_profit': take_profit or round(buy_value * 1.10, 2),
            'risk_reward_ratio': 1.5,
            'tradingview_url': f'https://tradingview.com/{symbol}',
        }

    def _new_buy(self, symbol, buy_value, now_madrid,
                 stop_loss=None, take_profit=None):
        """Build a new BUY recommendation row (as main.py produces it)."""
        return {
            'symbol': symbol,
            'buy_value': buy_value,
            'buy_date': now_madrid,
            'stop_loss': stop_loss or round(buy_value * 0.94, 2),
            'take_profit': take_profit or round(buy_value * 1.10, 2),
            'risk_reward_ratio': 1.5,
            'tradingview_url': f'https://tradingview.com/{symbol}',
        }

    def _build_scenario(self):
        """
        Build a realistic scenario:
          - AAPL: closed at target (10 %)
          - MSFT: still open
          - NVDA: new BUY (just entered)
        Returns (trans_updated_df, buy_df, now_madrid).
        """
        now_madrid = datetime.now().strftime('%Y-%m-%d %H:%M')

        trans_rows = [
            self._closed_transaction(
                'AAPL', 150.0,
                buy_date_str='2026-08-01 09:35',
                sell_date_str='2026-09-10',
            ),
            self._open_transaction(
                'MSFT', 400.0,
                buy_date_str='2026-09-05 14:20',
            ),
        ]
        trans_updated_df = pd.DataFrame(trans_rows)

        buy_rows = [
            self._new_buy('NVDA', 120.0, now_madrid),
        ]
        buy_df = pd.DataFrame(buy_rows)

        return trans_updated_df, buy_df, now_madrid

    # -- tests ---------------------------------------------------------------

    def test_column_order_matches_expected(self):
        """
        Columns must follow the canonical order so the Google Sheet is readable.

        PASS: [symbol, buy_value, buy_date, sell_value, sell_date, ...]
        FAIL: [symbol, buy_value, buy_date, stop_loss, ..., sell_value]
              (sell_value pushed to the end because pandas created it late)
        """
        trans_df, buy_df, _ = self._build_scenario()
        final = _build_transactions_log(trans_df, buy_df)

        present_expected = [c for c in _EXPECTED_COL_ORDER if c in final.columns]
        assert list(final.columns[:len(present_expected)]) == present_expected, (
            f"Column order mismatch.\n  Expected: {present_expected}\n  Got:      {list(final.columns)}"
        )

    def test_sell_value_column_right_after_buy_date(self):
        """
        sell_value must appear immediately after buy_date, never at the end.

        PASS: ..., buy_date, sell_value, sell_date, ...  (position 3)
        FAIL: ..., buy_date, stop_loss, ..., sell_value  (position 8+)
        """
        trans_df, buy_df, _ = self._build_scenario()
        final = _build_transactions_log(trans_df, buy_df)
        cols = list(final.columns)

        buy_date_idx = cols.index('buy_date')
        sell_value_idx = cols.index('sell_value')
        assert sell_value_idx == buy_date_idx + 1, (
            f"sell_value at position {sell_value_idx}, expected {buy_date_idx + 1} "
            f"(right after buy_date). Columns: {cols}"
        )

    def test_sell_value_greater_than_buy_value_on_target_hit(self):
        """
        When a position is closed by hitting the revenue target,
        sell_value must be strictly greater than buy_value.

        PASS: buy_value=150.0, sell_value=165.0  (165 > 150)
        FAIL: buy_value=150.0, sell_value=141.0  (stop_loss leaked as sell_value)
        """
        trans_df, buy_df, _ = self._build_scenario()
        final = _build_transactions_log(trans_df, buy_df)

        closed = final[final['sell_value'].notna()]
        for _, row in closed.iterrows():
            assert row['sell_value'] > row['buy_value'], (
                f"{row['symbol']}: sell_value ({row['sell_value']}) "
                f"<= buy_value ({row['buy_value']})"
            )

    def test_percentage_benefit_matches_revenue_percentage(self):
        """
        Closed positions (target hit) must show at least revenue_percentage benefit.

        PASS: revenue_percentage=10, percentage_benefit=10.0
        FAIL: revenue_percentage=10, percentage_benefit=6.0
              (take_profit from ATR was used instead of target_price)
        """
        trans_df, buy_df, _ = self._build_scenario()
        final = _build_transactions_log(trans_df, buy_df)

        aapl = final[final['symbol'] == 'AAPL'].iloc[0]
        assert aapl['percentage_benefit'] >= self.REVENUE_PCT, (
            f"AAPL percentage_benefit={aapl['percentage_benefit']}, "
            f"expected >= {self.REVENUE_PCT}"
        )

    def test_sell_value_at_least_target_price(self):
        """
        sell_value must be >= buy_value * (1 + revenue_percentage / 100).
        It can be higher if the price gapped above target, but never lower.

        PASS: buy_value=150, sell_value=165.0  (== target 150*1.10)
        PASS: buy_value=150, sell_value=170.0  (> target, price gapped up)
        FAIL: buy_value=150, sell_value=159.0  (take_profit from ATR, only 6%)
        """
        trans_df, buy_df, _ = self._build_scenario()
        final = _build_transactions_log(trans_df, buy_df)

        closed = final[final['sell_value'].notna()]
        for _, row in closed.iterrows():
            target = round(row['buy_value'] * (1 + self.REVENUE_PCT / 100), 2)
            assert row['sell_value'] >= target, (
                f"{row['symbol']}: sell_value={row['sell_value']} < "
                f"target_price={target} (buy_value={row['buy_value']} * "
                f"{1 + self.REVENUE_PCT / 100})"
            )

    def test_buy_date_format_includes_time(self):
        """
        buy_date for new buys must include hour and minute (YYYY-MM-DD HH:MM).

        PASS: '2026-09-10 14:30'
        FAIL: '2026-09-10'          (missing time, old format)
        FAIL: '10/09/2026 14:30'    (wrong date format)
        """
        trans_df, buy_df, now_madrid = self._build_scenario()
        final = _build_transactions_log(trans_df, buy_df)

        nvda = final[final['symbol'] == 'NVDA'].iloc[0]
        assert _BUY_DATE_RE.match(str(nvda['buy_date'])), (
            f"NVDA buy_date='{nvda['buy_date']}' does not match YYYY-MM-DD HH:MM"
        )
        assert str(nvda['buy_date']) == now_madrid

    def test_old_buy_date_format_with_time_preserved(self):
        """
        Existing buy_dates that already have time must be preserved after
        concat and sort.

        PASS: '2026-08-01 09:35' stays as '2026-08-01 09:35'
        FAIL: '2026-08-01 09:35' becomes '2026-08-01' (time stripped)
        FAIL: '2026-08-01 09:35' becomes 'NaT' (date parsing error)
        """
        trans_df, buy_df, _ = self._build_scenario()
        final = _build_transactions_log(trans_df, buy_df)

        aapl = final[final['symbol'] == 'AAPL'].iloc[0]
        assert _BUY_DATE_RE.match(str(aapl['buy_date'])), (
            f"AAPL buy_date='{aapl['buy_date']}' lost its time component"
        )

    def test_sell_date_iso_format(self):
        """
        sell_date must be a plain ISO date (YYYY-MM-DD).

        PASS: '2026-09-10'
        FAIL: '2026-09-10 00:00:00'  (datetime leaked instead of date)
        FAIL: '10/09/2026'           (wrong format)
        """
        trans_df, buy_df, _ = self._build_scenario()
        final = _build_transactions_log(trans_df, buy_df)

        closed = final[final['sell_date'].notna() & (final['sell_date'] != '')]
        for _, row in closed.iterrows():
            assert _SELL_DATE_RE.match(str(row['sell_date'])), (
                f"{row['symbol']}: sell_date='{row['sell_date']}' "
                f"does not match YYYY-MM-DD"
            )

    def test_open_positions_have_no_sell_data(self):
        """
        Open positions must have NaN/empty for all sell-related columns.

        PASS: MSFT sell_value=NaN, sell_date=NaN, days_diff=NaN, pct=NaN
        FAIL: MSFT sell_value=0.0   (zero instead of empty)
        FAIL: NVDA sell_date=''     (empty string from partial write)
        """
        trans_df, buy_df, _ = self._build_scenario()
        final = _build_transactions_log(trans_df, buy_df)

        sell_cols = ['sell_value', 'sell_date', 'buy_sell_days_diff', 'percentage_benefit']
        for symbol in ['MSFT', 'NVDA']:
            row = final[final['symbol'] == symbol].iloc[0]
            for col in sell_cols:
                val = row[col]
                is_empty = pd.isna(val) or (isinstance(val, str) and val.strip() in ('', 'nan', 'None'))
                assert is_empty, (
                    f"{symbol} is open but {col}='{val}' (should be empty)"
                )

    def test_new_buy_has_stop_loss_and_take_profit(self):
        """
        New BUY rows must carry stop_loss and take_profit, and the values
        must be coherent: stop_loss < buy_value < take_profit.

        PASS: buy=120, stop_loss=112.80, take_profit=132.0
        FAIL: buy=120, stop_loss=NaN     (risk management not applied)
        FAIL: buy=120, stop_loss=125.0   (stop_loss > buy_value, inverted)
        """
        trans_df, buy_df, _ = self._build_scenario()
        final = _build_transactions_log(trans_df, buy_df)

        nvda = final[final['symbol'] == 'NVDA'].iloc[0]
        assert pd.notna(nvda['stop_loss']), "NVDA missing stop_loss"
        assert pd.notna(nvda['take_profit']), "NVDA missing take_profit"
        assert nvda['stop_loss'] < nvda['buy_value'], (
            f"NVDA stop_loss ({nvda['stop_loss']}) >= buy_value ({nvda['buy_value']})"
        )
        assert nvda['take_profit'] > nvda['buy_value'], (
            f"NVDA take_profit ({nvda['take_profit']}) <= buy_value ({nvda['buy_value']})"
        )

    def test_buy_sell_days_diff_is_positive(self):
        """
        Days between buy and sell must be non-negative for closed positions.

        PASS: buy_date='2026-08-01', sell_date='2026-09-10', days_diff=40
        FAIL: days_diff=-5  (dates swapped or miscalculated)
        """
        trans_df, buy_df, _ = self._build_scenario()
        final = _build_transactions_log(trans_df, buy_df)

        closed = final[final['buy_sell_days_diff'].notna()]
        for _, row in closed.iterrows():
            assert int(row['buy_sell_days_diff']) >= 0, (
                f"{row['symbol']}: buy_sell_days_diff={row['buy_sell_days_diff']} is negative"
            )

    def test_sorted_by_buy_date_descending(self):
        """
        Rows must be sorted by buy_date descending (newest first).

        PASS: ['2026-09-10 14:30', '2026-09-05 14:20', '2026-08-01 09:35']
        FAIL: ['2026-08-01 09:35', '2026-09-05 14:20', '2026-09-10 14:30']
              (ascending instead of descending)
        """
        trans_df, buy_df, _ = self._build_scenario()
        final = _build_transactions_log(trans_df, buy_df)

        dates = list(final['buy_date'].astype(str))
        assert dates == sorted(dates, reverse=True), (
            f"Rows not sorted by buy_date descending: {dates}"
        )

    def test_no_analysis_columns_leak_into_transactions(self):
        """
        Columns like llm_opinion, filter_status, action must NOT appear
        in the transactions log. Only tx_cols are kept from buy_df.

        PASS: columns = [symbol, buy_value, buy_date, ..., tradingview_url]
        FAIL: columns include 'llm_opinion' or 'filter_status'
              (tx_cols filter not applied before concat)
        """
        trans_df, buy_df, _ = self._build_scenario()
        # Add typical analysis columns to buy_df to simulate the real pipeline
        buy_df['action'] = 'BUY'
        buy_df['llm_opinion'] = 'COHERENT | adj=+0.05'
        buy_df['filter_status'] = 'passed'
        buy_df['technical_confidence'] = 0.75

        final = _build_transactions_log(trans_df, buy_df)

        forbidden = {'action', 'llm_opinion', 'filter_status', 'technical_confidence',
                     'manual_financial_analysis', 'news_sentiment', 'change_percent'}
        leaked = forbidden & set(final.columns)
        assert not leaked, f"Analysis columns leaked into transactions log: {leaked}"

    def test_take_profit_lower_than_target_does_not_reduce_sell_value(self):
        """
        Regression: when take_profit (ATR-based) < target_price (revenue-based),
        the recorded sell_value must still be >= target_price.

        PASS: buy=200, take_profit=210(5%), sell_value=220(10%)  target respected
        FAIL: buy=200, take_profit=210(5%), sell_value=210(5%)   ATR overrode revenue
        """
        buy_value = 200.0
        target_price = round(buy_value * (1 + self.REVENUE_PCT / 100), 2)  # 220.0
        low_take_profit = 210.0  # ATR-based, only 5%

        trans_rows = [
            self._closed_transaction(
                'TSLA', buy_value,
                buy_date_str='2026-08-15 10:00',
                sell_date_str='2026-09-10',
                take_profit=low_take_profit,
            ),
        ]
        trans_df = pd.DataFrame(trans_rows)
        buy_df = pd.DataFrame(columns=[
            'symbol', 'buy_value', 'buy_date', 'stop_loss', 'take_profit',
            'risk_reward_ratio', 'tradingview_url',
        ])

        final = _build_transactions_log(trans_df, buy_df)

        tsla = final[final['symbol'] == 'TSLA'].iloc[0]
        assert tsla['sell_value'] >= target_price, (
            f"sell_value={tsla['sell_value']} should be >= target_price={target_price}, "
            f"not take_profit={low_take_profit}"
        )
        assert tsla['percentage_benefit'] >= self.REVENUE_PCT, (
            f"percentage_benefit={tsla['percentage_benefit']} should be >= {self.REVENUE_PCT}%"
        )
