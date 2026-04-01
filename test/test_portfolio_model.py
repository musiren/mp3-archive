"""
test_portfolio_model.py - Unit tests for portfolio_model.py.

Verifies AccountHolding, StockHolding, and Portfolio data model
calculations: cost basis, P&L, target price, dividends,
serialisation round-trips, and the factory default.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from portfolio_model import (
    AccountHolding,
    Portfolio,
    StockHolding,
    build_default_portfolio,
)


class TestAccountHolding(unittest.TestCase):
    """Tests for AccountHolding properties and methods."""

    def _make(self, quantity=100, avg_price=50_000):
        """Return an AccountHolding with the given quantity and average price."""
        return AccountHolding(account="테스트계좌", quantity=quantity, avg_price=avg_price)

    def test_cost_is_quantity_times_avg_price(self):
        """Verify that cost equals quantity × avg_price."""
        acc = self._make(quantity=10, avg_price=200_000)
        self.assertEqual(acc.cost, 2_000_000)

    def test_pnl_positive_when_price_above_avg(self):
        """Verify positive P&L when the current price exceeds the average."""
        acc = self._make(quantity=10, avg_price=100_000)
        self.assertEqual(acc.pnl(110_000), 100_000)

    def test_pnl_negative_when_price_below_avg(self):
        """Verify negative P&L when the current price is below the average."""
        acc = self._make(quantity=10, avg_price=100_000)
        self.assertEqual(acc.pnl(90_000), -100_000)

    def test_pnl_zero_at_avg_price(self):
        """Verify zero P&L when the current price equals the average."""
        acc = self._make(quantity=10, avg_price=100_000)
        self.assertEqual(acc.pnl(100_000), 0)

    def test_pnl_rate_positive(self):
        """Verify positive pnl_rate when the current price exceeds the average."""
        acc = self._make(quantity=1, avg_price=100_000)
        self.assertAlmostEqual(acc.pnl_rate(110_000), 10.0)

    def test_pnl_rate_negative(self):
        """Verify negative pnl_rate when the current price is below the average."""
        acc = self._make(quantity=1, avg_price=100_000)
        self.assertAlmostEqual(acc.pnl_rate(90_000), -10.0)

    def test_pnl_rate_zero_avg_price_returns_zero(self):
        """Verify pnl_rate returns 0.0 when avg_price is zero (avoid division)."""
        acc = self._make(quantity=1, avg_price=0)
        self.assertEqual(acc.pnl_rate(100_000), 0.0)

    def test_to_dict_round_trip(self):
        """Verify that to_dict / from_dict produce an equivalent object."""
        acc = AccountHolding(account="ISA계좌", quantity=7, avg_price=198_128)
        restored = AccountHolding.from_dict(acc.to_dict())
        self.assertEqual(restored.account, acc.account)
        self.assertEqual(restored.quantity, acc.quantity)
        self.assertEqual(restored.avg_price, acc.avg_price)


class TestStockHolding(unittest.TestCase):
    """Tests for StockHolding aggregation, target price, and dividends."""

    def _make_samsung(self):
        """Return a StockHolding resembling the user's Samsung position."""
        return StockHolding(
            ticker="005930",
            name="삼성전자",
            accounts=[
                AccountHolding(account="공용계좌", quantity=111, avg_price=163_680),
                AccountHolding(account="신한증권", quantity=180, avg_price=199_400),
                AccountHolding(account="ISA계좌", quantity=7, avg_price=198_128),
                AccountHolding(account="한국투자증권", quantity=30, avg_price=176_800),
            ],
            target_profit=30_000_000,
            dividend_per_share=1_460,
        )

    def test_total_quantity(self):
        """Verify that total_quantity sums shares across all accounts."""
        stock = self._make_samsung()
        self.assertEqual(stock.total_quantity, 328)

    def test_total_cost(self):
        """Verify that total_cost sums cost basis across all accounts."""
        stock = self._make_samsung()
        expected = 111*163_680 + 180*199_400 + 7*198_128 + 30*176_800
        self.assertEqual(stock.total_cost, expected)

    def test_blended_avg_price(self):
        """Verify blended_avg_price is total_cost / total_quantity (rounded)."""
        stock = self._make_samsung()
        expected = round(stock.total_cost / stock.total_quantity)
        self.assertEqual(stock.blended_avg_price, expected)

    def test_blended_avg_price_no_shares(self):
        """Verify blended_avg_price returns 0 when no shares are held."""
        stock = StockHolding(ticker="000000", name="빈종목")
        self.assertEqual(stock.blended_avg_price, 0)

    def test_total_pnl(self):
        """Verify total_pnl sums P&L across all accounts at a given price."""
        stock = self._make_samsung()
        price = 184_400
        expected = sum(a.pnl(price) for a in stock.accounts)
        self.assertEqual(stock.total_pnl(price), expected)

    def test_target_price_above_avg(self):
        """Verify target_price is above blended average when target_profit > 0."""
        stock = self._make_samsung()
        self.assertGreater(stock.target_price(), stock.blended_avg_price)

    def test_target_price_formula(self):
        """Verify target_price = blended_avg + target_profit / total_quantity."""
        stock = self._make_samsung()
        expected = round(stock.blended_avg_price + stock.target_profit / stock.total_quantity)
        self.assertEqual(stock.target_price(), expected)

    def test_target_price_no_shares_returns_zero(self):
        """Verify target_price returns 0 when no shares are held."""
        stock = StockHolding(ticker="000000", name="빈종목", target_profit=1_000_000)
        self.assertEqual(stock.target_price(), 0)

    def test_annual_dividend_gross(self):
        """Verify annual_dividend_gross = total_quantity × dividend_per_share."""
        stock = self._make_samsung()
        self.assertEqual(stock.annual_dividend_gross(), 328 * 1_460)

    def test_annual_dividend_net_less_than_gross(self):
        """Verify after-tax dividend is less than the gross dividend."""
        stock = self._make_samsung()
        self.assertLess(stock.annual_dividend_net(), stock.annual_dividend_gross())

    def test_annual_dividend_net_default_tax_rate(self):
        """Verify net dividend applies the default 15.4% withholding tax."""
        stock = self._make_samsung()
        expected = round(stock.annual_dividend_gross() * (1 - 0.154))
        self.assertEqual(stock.annual_dividend_net(), expected)

    def test_append_price_history(self):
        """Verify that append_price_history adds one record with correct fields."""
        stock = self._make_samsung()
        initial_len = len(stock.price_history)
        stock.append_price_history("2026-04-02", 185_000)
        self.assertEqual(len(stock.price_history), initial_len + 1)
        last = stock.price_history[-1]
        self.assertEqual(last["date"], "2026-04-02")
        self.assertEqual(last["price"], 185_000)
        self.assertIn("pnl", last)

    def test_to_dict_round_trip(self):
        """Verify that to_dict / from_dict produce an equivalent StockHolding."""
        stock = self._make_samsung()
        restored = StockHolding.from_dict(stock.to_dict())
        self.assertEqual(restored.ticker, stock.ticker)
        self.assertEqual(restored.total_quantity, stock.total_quantity)
        self.assertEqual(restored.total_cost, stock.total_cost)
        self.assertEqual(len(restored.accounts), len(stock.accounts))
        self.assertEqual(restored.target_profit, stock.target_profit)
        self.assertEqual(restored.dividend_per_share, stock.dividend_per_share)


class TestPortfolio(unittest.TestCase):
    """Tests for Portfolio-level aggregation and serialisation."""

    def _make_portfolio(self):
        """Return a small two-stock Portfolio for testing."""
        s1 = StockHolding(
            ticker="AAA",
            name="종목A",
            accounts=[AccountHolding(account="계좌1", quantity=10, avg_price=100_000)],
        )
        s2 = StockHolding(
            ticker="BBB",
            name="종목B",
            accounts=[AccountHolding(account="계좌2", quantity=5, avg_price=200_000)],
        )
        return Portfolio(stocks=[s1, s2], last_updated="2026-04-01")

    def test_total_cost(self):
        """Verify Portfolio.total_cost sums across all stocks."""
        port = self._make_portfolio()
        self.assertEqual(port.total_cost, 10*100_000 + 5*200_000)

    def test_total_pnl(self):
        """Verify Portfolio.total_pnl uses the prices dict correctly."""
        port = self._make_portfolio()
        prices = {"AAA": 110_000, "BBB": 190_000}
        expected = 10*(110_000-100_000) + 5*(190_000-200_000)
        self.assertEqual(port.total_pnl(prices), expected)

    def test_total_pnl_missing_ticker_ignored(self):
        """Verify stocks not present in the prices dict are skipped."""
        port = self._make_portfolio()
        self.assertEqual(port.total_pnl({}), 0)

    def test_find_stock_returns_correct_stock(self):
        """Verify find_stock returns the StockHolding with the matching ticker."""
        port = self._make_portfolio()
        result = port.find_stock("BBB")
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "종목B")

    def test_find_stock_returns_none_for_unknown_ticker(self):
        """Verify find_stock returns None for an unrecognised ticker."""
        port = self._make_portfolio()
        self.assertIsNone(port.find_stock("ZZZ"))

    def test_to_dict_round_trip(self):
        """Verify that to_dict / from_dict produce an equivalent Portfolio."""
        port = self._make_portfolio()
        restored = Portfolio.from_dict(port.to_dict())
        self.assertEqual(restored.last_updated, port.last_updated)
        self.assertEqual(len(restored.stocks), len(port.stocks))
        self.assertEqual(restored.total_cost, port.total_cost)


class TestBuildDefaultPortfolio(unittest.TestCase):
    """Tests for the build_default_portfolio factory function."""

    def test_returns_portfolio_instance(self):
        """Verify that build_default_portfolio returns a Portfolio."""
        port = build_default_portfolio()
        self.assertIsInstance(port, Portfolio)

    def test_contains_two_stocks(self):
        """Verify that the default portfolio contains exactly two stocks."""
        port = build_default_portfolio()
        self.assertEqual(len(port.stocks), 2)

    def test_samsung_ticker(self):
        """Verify the first stock is Samsung Electronics (005930)."""
        port = build_default_portfolio()
        self.assertEqual(port.find_stock("005930").name, "삼성전자")

    def test_sk_hynix_ticker(self):
        """Verify the second stock is SK Hynix (000660)."""
        port = build_default_portfolio()
        self.assertEqual(port.find_stock("000660").name, "SK하이닉스")

    def test_samsung_total_quantity(self):
        """Verify Samsung has 328 shares total across four accounts."""
        port = build_default_portfolio()
        self.assertEqual(port.find_stock("005930").total_quantity, 328)

    def test_sk_hynix_total_quantity(self):
        """Verify SK Hynix has 40 shares total across two accounts."""
        port = build_default_portfolio()
        self.assertEqual(port.find_stock("000660").total_quantity, 40)

    def test_samsung_total_cost(self):
        """Verify Samsung total cost matches the user's stated ₩60,751,376."""
        port = build_default_portfolio()
        self.assertEqual(port.find_stock("005930").total_cost, 60_751_376)

    def test_sk_hynix_total_cost(self):
        """Verify SK Hynix total cost equals sum of account cost bases (KRW)."""
        port = build_default_portfolio()
        stock = port.find_stock("000660")
        expected = sum(a.cost for a in stock.accounts)
        self.assertEqual(stock.total_cost, expected)

    def test_samsung_has_price_history(self):
        """Verify Samsung has pre-populated price history entries."""
        port = build_default_portfolio()
        self.assertGreater(len(port.find_stock("005930").price_history), 0)

    def test_portfolio_last_updated_is_set(self):
        """Verify last_updated is non-empty in the default portfolio."""
        port = build_default_portfolio()
        self.assertTrue(port.last_updated)


if __name__ == "__main__":
    unittest.main()
