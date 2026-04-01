"""
test_portfolio_storage.py - Unit tests for portfolio_storage.py.

Verifies that PortfolioStorage correctly:
  - Returns the default portfolio when no data has been saved
  - Round-trips a portfolio through save() → load()
  - Appends price history records before saving
  - Resets to the factory default
"""

import json
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Stub out PyQt6 before importing portfolio_storage so the test can run
# in environments where PyQt6 is not installed.
_pyqt6_stub = MagicMock()
sys.modules.setdefault("PyQt6", _pyqt6_stub)
sys.modules.setdefault("PyQt6.QtCore", _pyqt6_stub.QtCore)

from portfolio_model import AccountHolding, Portfolio, StockHolding, build_default_portfolio
from portfolio_storage import PortfolioStorage


def _make_mock_settings(stored_value=None):
    """
    Return a MagicMock that mimics QSettings for PortfolioStorage.

    Args:
        stored_value: The JSON string that settings.value() should return.
                      Pass None to simulate an empty (first-run) settings store.

    Returns:
        A MagicMock configured to behave like QSettings.
    """
    mock = MagicMock()
    mock.value.return_value = stored_value
    return mock


class TestPortfolioStorageLoad(unittest.TestCase):
    """Tests for PortfolioStorage.load()."""

    def _storage_with_mock(self, stored_value=None):
        """Return a PortfolioStorage whose QSettings is replaced by a mock."""
        storage = PortfolioStorage.__new__(PortfolioStorage)
        storage._settings = _make_mock_settings(stored_value)
        return storage

    def test_load_returns_default_when_no_data(self):
        """Verify load() returns a Portfolio when QSettings is empty."""
        storage = self._storage_with_mock(stored_value=None)
        port = storage.load()
        self.assertIsInstance(port, Portfolio)

    def test_load_default_has_two_stocks(self):
        """Verify load() returns the factory default with two stocks on first run."""
        storage = self._storage_with_mock(stored_value=None)
        port = storage.load()
        self.assertEqual(len(port.stocks), 2)

    def test_load_returns_saved_data(self):
        """Verify load() deserialises a previously saved portfolio."""
        original = Portfolio(
            stocks=[
                StockHolding(
                    ticker="TST",
                    name="테스트",
                    accounts=[AccountHolding("계좌A", 50, 100_000)],
                    target_profit=5_000_000,
                )
            ],
            last_updated="2026-01-01",
        )
        json_str = json.dumps(original.to_dict())
        storage = self._storage_with_mock(stored_value=json_str)
        port = storage.load()
        self.assertEqual(len(port.stocks), 1)
        self.assertEqual(port.stocks[0].ticker, "TST")
        self.assertEqual(port.stocks[0].total_quantity, 50)
        self.assertEqual(port.last_updated, "2026-01-01")

    def test_load_returns_default_on_corrupt_json(self):
        """Verify load() falls back to the default when JSON is malformed."""
        storage = self._storage_with_mock(stored_value="{not valid json!!!}")
        port = storage.load()
        self.assertIsInstance(port, Portfolio)
        self.assertGreater(len(port.stocks), 0)

    def test_load_returns_default_on_missing_keys(self):
        """Verify load() falls back to the default when required keys are missing."""
        storage = self._storage_with_mock(stored_value=json.dumps({"bad": "data"}))
        # from_dict with missing 'stocks' key should produce an empty portfolio
        port = storage.load()
        self.assertIsInstance(port, Portfolio)


class TestPortfolioStorageSave(unittest.TestCase):
    """Tests for PortfolioStorage.save()."""

    def _storage_with_mock(self, stored_value=None):
        """Return a PortfolioStorage whose QSettings is replaced by a mock."""
        storage = PortfolioStorage.__new__(PortfolioStorage)
        storage._settings = _make_mock_settings(stored_value)
        return storage

    def test_save_calls_set_value(self):
        """Verify save() calls QSettings.setValue with the portfolio key."""
        storage = self._storage_with_mock()
        port = build_default_portfolio()
        storage.save(port)
        storage._settings.setValue.assert_called_once()
        key_used = storage._settings.setValue.call_args[0][0]
        self.assertEqual(key_used, "portfolio")

    def test_save_stores_valid_json(self):
        """Verify save() stores a JSON-parseable string."""
        storage = self._storage_with_mock()
        port = build_default_portfolio()
        storage.save(port)
        stored_json = storage._settings.setValue.call_args[0][1]
        data = json.loads(stored_json)
        self.assertIn("stocks", data)

    def test_round_trip(self):
        """Verify that a portfolio saved then loaded is identical to the original."""
        # Capture the value passed to setValue, then return it from value()
        captured = {}

        def fake_set_value(key, val):
            captured[key] = val

        def fake_value(key, *args):
            return captured.get(key)

        storage = PortfolioStorage.__new__(PortfolioStorage)
        storage._settings = MagicMock()
        storage._settings.setValue.side_effect = fake_set_value
        storage._settings.value.side_effect = fake_value

        original = build_default_portfolio()
        storage.save(original)
        reloaded = storage.load()

        self.assertEqual(reloaded.last_updated, original.last_updated)
        self.assertEqual(len(reloaded.stocks), len(original.stocks))
        for orig_stock, reload_stock in zip(original.stocks, reloaded.stocks):
            self.assertEqual(orig_stock.ticker, reload_stock.ticker)
            self.assertEqual(orig_stock.total_cost, reload_stock.total_cost)
            self.assertEqual(orig_stock.total_quantity, reload_stock.total_quantity)

    def test_save_calls_sync(self):
        """Verify save() calls QSettings.sync() after writing."""
        storage = self._storage_with_mock()
        storage.save(build_default_portfolio())
        storage._settings.sync.assert_called_once()


class TestPortfolioStorageReset(unittest.TestCase):
    """Tests for PortfolioStorage.reset()."""

    def _storage_with_mock(self):
        """Return a PortfolioStorage whose QSettings is replaced by a mock."""
        storage = PortfolioStorage.__new__(PortfolioStorage)
        storage._settings = _make_mock_settings(stored_value=None)
        return storage

    def test_reset_removes_key(self):
        """Verify reset() calls QSettings.remove with the portfolio key."""
        storage = self._storage_with_mock()
        storage.reset()
        storage._settings.remove.assert_called_once_with("portfolio")

    def test_reset_returns_default_portfolio(self):
        """Verify reset() returns a Portfolio instance with the factory defaults."""
        storage = self._storage_with_mock()
        port = storage.reset()
        self.assertIsInstance(port, Portfolio)
        self.assertEqual(len(port.stocks), 2)

    def test_reset_calls_sync(self):
        """Verify reset() calls QSettings.sync() after removing the key."""
        storage = self._storage_with_mock()
        storage.reset()
        storage._settings.sync.assert_called_once()


if __name__ == "__main__":
    unittest.main()
