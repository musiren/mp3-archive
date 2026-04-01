"""
portfolio_storage.py - Persistent storage for the stock portfolio tracker.

Saves and loads the Portfolio object using QSettings under the
organisation/application key pair ("my-stock", "portfolio").
The portfolio data is JSON-serialised and stored as a single string value.

Usage:
    storage = PortfolioStorage()
    portfolio = storage.load()          # returns default if nothing saved yet
    storage.save(portfolio)
"""

import json

from PyQt6.QtCore import QSettings

from portfolio_model import Portfolio, build_default_portfolio

_ORG = "my-stock"
_APP = "portfolio"
_KEY = "portfolio"


class PortfolioStorage:
    """Manages persistence of Portfolio data via QSettings."""

    def __init__(self) -> None:
        """Initialise QSettings with the fixed organisation/app identifiers."""
        self._settings = QSettings(_ORG, _APP)

    def load(self) -> Portfolio:
        """
        Load the portfolio from QSettings.

        Returns the user's default portfolio (pre-populated with initial
        holdings) if no saved data is found.

        Returns:
            A Portfolio instance, either from storage or the factory default.
        """
        raw = self._settings.value(_KEY)
        if not raw:
            return build_default_portfolio()
        try:
            data = json.loads(raw)
            return Portfolio.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError):
            return build_default_portfolio()

    def save(self, portfolio: Portfolio) -> None:
        """
        Serialise and persist the portfolio to QSettings.

        Args:
            portfolio: The Portfolio instance to save.
        """
        self._settings.setValue(_KEY, json.dumps(portfolio.to_dict()))
        self._settings.sync()

    def reset(self) -> Portfolio:
        """
        Delete any saved portfolio data and return the factory default.

        Returns:
            A fresh default Portfolio.
        """
        self._settings.remove(_KEY)
        self._settings.sync()
        return build_default_portfolio()
