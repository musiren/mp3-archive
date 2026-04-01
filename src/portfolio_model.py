"""
portfolio_model.py - Data model for the stock portfolio tracker.

Provides immutable-friendly dataclasses representing the hierarchy:
  Portfolio → StockHolding (per ticker) → AccountHolding (per brokerage account)

All monetary values are in Korean Won (KRW) as plain integers.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AccountHolding:
    """Represents a single brokerage-account position in one stock."""

    account: str
    """Human-readable account name (e.g. '신한증권', 'ISA계좌')."""

    quantity: int
    """Number of shares held."""

    avg_price: int
    """Average purchase price per share (KRW)."""

    @property
    def cost(self) -> int:
        """Return total cost basis: quantity × avg_price (KRW)."""
        return self.quantity * self.avg_price

    def pnl(self, current_price: int) -> int:
        """
        Return unrealised profit/loss at the given current price.

        Args:
            current_price: Current market price per share (KRW).

        Returns:
            Signed integer P&L in KRW.
        """
        return (current_price - self.avg_price) * self.quantity

    def pnl_rate(self, current_price: int) -> float:
        """
        Return unrealised P&L as a percentage of cost basis.

        Args:
            current_price: Current market price per share (KRW).

        Returns:
            P&L percentage (e.g. 5.2 means +5.2%).
        """
        if self.avg_price == 0:
            return 0.0
        return (current_price - self.avg_price) / self.avg_price * 100.0

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON storage."""
        return {
            "account": self.account,
            "quantity": self.quantity,
            "avg_price": self.avg_price,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AccountHolding":
        """
        Deserialise from a plain dict.

        Args:
            data: Dict with keys 'account', 'quantity', 'avg_price'.

        Returns:
            A new AccountHolding instance.
        """
        return cls(
            account=data["account"],
            quantity=int(data["quantity"]),
            avg_price=int(data["avg_price"]),
        )


@dataclass
class StockHolding:
    """Aggregated holding of a single stock ticker across multiple accounts."""

    ticker: str
    """KRX ticker code (e.g. '005930')."""

    name: str
    """Korean stock name (e.g. '삼성전자')."""

    accounts: list = field(default_factory=list)
    """List of AccountHolding objects, one per brokerage account."""

    target_profit: int = 0
    """Desired total profit in KRW (e.g. 30_000_000)."""

    dividend_per_share: int = 0
    """Annual dividend paid per share in KRW (already annualised)."""

    dividend_tax_rate: float = 0.154
    """Withholding tax rate applied to dividends (default 15.4%)."""

    price_history: list = field(default_factory=list)
    """Chronological list of dicts: [{date, price, pnl}]."""

    @property
    def total_quantity(self) -> int:
        """Return the sum of shares held across all accounts."""
        return sum(a.quantity for a in self.accounts)

    @property
    def total_cost(self) -> int:
        """Return the total cost basis across all accounts (KRW)."""
        return sum(a.cost for a in self.accounts)

    @property
    def blended_avg_price(self) -> int:
        """
        Return the quantity-weighted average purchase price.

        Returns:
            0 if no shares are held.
        """
        qty = self.total_quantity
        if qty == 0:
            return 0
        return round(self.total_cost / qty)

    def total_pnl(self, current_price: int) -> int:
        """
        Return the total unrealised P&L across all accounts.

        Args:
            current_price: Current market price per share (KRW).

        Returns:
            Signed integer P&L in KRW.
        """
        return sum(a.pnl(current_price) for a in self.accounts)

    def target_price(self) -> int:
        """
        Return the price at which the target profit is reached.

        Returns:
            0 if no shares are held.
        """
        qty = self.total_quantity
        if qty == 0:
            return 0
        return round(self.blended_avg_price + self.target_profit / qty)

    def annual_dividend_gross(self) -> int:
        """Return gross annual dividend for the entire holding (KRW)."""
        return self.total_quantity * self.dividend_per_share

    def annual_dividend_net(self) -> int:
        """Return after-tax annual dividend (KRW), rounded to nearest won."""
        return round(self.annual_dividend_gross() * (1 - self.dividend_tax_rate))

    def append_price_history(self, date: str, current_price: int) -> None:
        """
        Record a price snapshot with its P&L into the history list.

        Args:
            date: ISO date string (e.g. '2026-04-01').
            current_price: Closing or current market price (KRW).
        """
        self.price_history.append(
            {
                "date": date,
                "price": current_price,
                "pnl": self.total_pnl(current_price),
            }
        )

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON storage."""
        return {
            "ticker": self.ticker,
            "name": self.name,
            "accounts": [a.to_dict() for a in self.accounts],
            "target_profit": self.target_profit,
            "dividend_per_share": self.dividend_per_share,
            "dividend_tax_rate": self.dividend_tax_rate,
            "price_history": list(self.price_history),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StockHolding":
        """
        Deserialise from a plain dict.

        Args:
            data: Dict produced by to_dict().

        Returns:
            A new StockHolding instance.
        """
        return cls(
            ticker=data["ticker"],
            name=data["name"],
            accounts=[AccountHolding.from_dict(a) for a in data.get("accounts", [])],
            target_profit=int(data.get("target_profit", 0)),
            dividend_per_share=int(data.get("dividend_per_share", 0)),
            dividend_tax_rate=float(data.get("dividend_tax_rate", 0.154)),
            price_history=list(data.get("price_history", [])),
        )


@dataclass
class Portfolio:
    """Top-level container for all tracked stock holdings."""

    stocks: list = field(default_factory=list)
    """List of StockHolding objects."""

    last_updated: str = ""
    """ISO date string of the last save (e.g. '2026-04-01')."""

    @property
    def total_cost(self) -> int:
        """Return the combined cost basis across all stocks (KRW)."""
        return sum(s.total_cost for s in self.stocks)

    def total_pnl(self, prices: dict) -> int:
        """
        Return the combined unrealised P&L for all stocks.

        Args:
            prices: Dict mapping ticker → current price (int KRW).

        Returns:
            Total signed P&L in KRW.
        """
        return sum(
            s.total_pnl(prices[s.ticker])
            for s in self.stocks
            if s.ticker in prices
        )

    def find_stock(self, ticker: str) -> Optional[StockHolding]:
        """
        Return the StockHolding for the given ticker, or None.

        Args:
            ticker: KRX ticker code to look up.

        Returns:
            Matching StockHolding or None if not found.
        """
        for s in self.stocks:
            if s.ticker == ticker:
                return s
        return None

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON storage."""
        return {
            "last_updated": self.last_updated,
            "stocks": [s.to_dict() for s in self.stocks],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Portfolio":
        """
        Deserialise from a plain dict.

        Args:
            data: Dict produced by to_dict().

        Returns:
            A new Portfolio instance.
        """
        return cls(
            last_updated=data.get("last_updated", ""),
            stocks=[StockHolding.from_dict(s) for s in data.get("stocks", [])],
        )


def build_default_portfolio() -> Portfolio:
    """
    Build and return the user's pre-configured portfolio with initial holdings.

    Holdings data is hard-coded from the user's 2026-04-01 snapshot.
    Samsung dividend is ₩365/share per quarter (4× per year → ₩1,460 annual).

    Returns:
        A Portfolio populated with Samsung Electronics and SK Hynix positions.
    """
    samsung = StockHolding(
        ticker="005930",
        name="삼성전자",
        accounts=[
            AccountHolding(account="공용계좌", quantity=111, avg_price=163_680),
            AccountHolding(account="신한증권", quantity=180, avg_price=199_400),
            AccountHolding(account="ISA계좌", quantity=7, avg_price=198_128),
            AccountHolding(account="한국투자증권", quantity=30, avg_price=176_800),
        ],
        target_profit=30_000_000,
        dividend_per_share=1_460,  # 365 × 4 quarterly payments
        price_history=[
            {"date": "2026-03-19", "price": 200_500, "pnl": 5_007_195},
            {"date": "2026-03-20", "price": 200_000, "pnl": 0},
            {"date": "2026-03-23", "price": 187_900, "pnl": 0},
            {"date": "2026-03-26", "price": 180_100, "pnl": -1_766_521},
            {"date": "2026-03-27", "price": 179_700, "pnl": -1_893_721},
            {"date": "2026-04-01", "price": 184_400, "pnl": -268_176},
        ],
    )

    sk_hynix = StockHolding(
        ticker="000660",
        name="SK하이닉스",
        accounts=[
            AccountHolding(account="ISA계좌", quantity=18, avg_price=311_702),
            AccountHolding(account="일반주식계좌", quantity=22, avg_price=495_136),
        ],
        target_profit=30_000_000,
        dividend_per_share=0,  # no regular dividend data provided
        price_history=[
            {"date": "2026-03-19", "price": 1_030_000, "pnl": 24_696_370},
            {"date": "2026-03-20", "price": 1_008_000, "pnl": 0},
            {"date": "2026-03-23", "price": 939_000, "pnl": 0},
            {"date": "2026-03-26", "price": 933_000, "pnl": 0},
            {"date": "2026-03-27", "price": 922_000, "pnl": 20_376_370},
            {"date": "2026-04-01", "price": 893_000, "pnl": 19_216_370},
        ],
    )

    return Portfolio(
        stocks=[samsung, sk_hynix],
        last_updated="2026-04-01",
    )
