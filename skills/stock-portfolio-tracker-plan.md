# Stock Portfolio Tracker — Implementation Plan

## Goal

Add a stock portfolio tracker tab to the MP3 Archive Manager desktop application.
The tracker lets the user record their Korean equity holdings, enter current market
prices, and instantly see profit/loss figures per account, per stock, and for the
whole portfolio.

---

## Data Scope (from user's portfolio)

**Samsung Electronics (삼성전자, 005930)**
- Accounts: 공용계좌, 신한증권, ISA계좌, 한국투자증권
- Quarterly dividend: ₩365/share × 4 per year
- Target profit: ₩30,000,000

**SK Hynix (SK하이닉스, 000660)**
- Accounts: ISA계좌, 일반주식계좌
- Target profit: ₩30,000,000

---

## Persistent Storage

- Engine: `QSettings("my-stock", "portfolio")`
- Key: `portfolio` — stores JSON-serialised portfolio snapshot
- Price history appended on every save

---

## Modules to Create

| File | Responsibility |
|------|----------------|
| `src/portfolio_model.py` | Dataclasses: `AccountHolding`, `StockHolding`, `Portfolio` |
| `src/portfolio_storage.py` | Load/save portfolio to QSettings; price-history append |
| `src/portfolio_widget.py` | PyQt6 `QWidget` with tabs for each stock + summary |

## Existing Files to Modify

| File | Change |
|------|--------|
| `src/main_window.ui` | Add "Portfolio" tab to existing `QTabWidget` (or create one) |
| `src/main_window.py` | Instantiate and wire `PortfolioWidget` in the new tab |
| `docs/ui-preview.jpg` | Regenerate after UI change |

---

## Model Design

```python
@dataclass
class AccountHolding:
    account: str      # account name
    quantity: int     # shares held
    avg_price: int    # purchase average price (KRW)

@dataclass
class StockHolding:
    ticker: str                      # e.g. "005930"
    name: str                        # e.g. "삼성전자"
    accounts: list[AccountHolding]
    target_profit: int               # target profit in KRW
    dividend_per_share: int          # annual dividend per share (KRW)
    dividend_periods: int            # number of dividend payments per year
    price_history: list[dict]        # [{date, price, pnl}]

@dataclass
class Portfolio:
    stocks: list[StockHolding]
    last_updated: str                # ISO date string
```

---

## PortfolioWidget UI Layout

```
┌─────────────────────────────────────────────┐
│  Current Price: [_______] KRW  [Update]     │
├─────────────────────────────────────────────┤
│  Stock Tabs: [삼성전자] [SK하이닉스] [Summary] │
│                                             │
│  Holdings Table:                            │
│  Account | Qty | Avg | Cost | Value | P&L   │
│  -------   ---   ---   ----   -----   ---   │
│                                             │
│  Total row                                  │
│  Target progress bar                        │
│  Dividend section                           │
│  Price history table                        │
└─────────────────────────────────────────────┘
```

---

## Tests to Create

| File | Tests |
|------|-------|
| `test/test_portfolio_model.py` | total_cost, total_quantity, pnl, target_price |
| `test/test_portfolio_storage.py` | round-trip save/load, price history append |

---

## Commit Plan

1. `feat: add portfolio model dataclasses`
2. `feat: add portfolio storage with QSettings persistence`
3. `feat: add PortfolioWidget PyQt6 UI`
4. `feat: integrate portfolio tab into main window`

---

## Implementation Notes

- All monetary values stored as integers (KRW, no decimals).
- P&L = (current_price - avg_price) × quantity per account.
- Dividend calculation: quantity × dividend_per_share × dividend_periods × (1 - 0.154).
  ISA account dividends use a separate tax rate (9.9% on excess over non-taxable limit).
  For simplicity, apply 15.4% uniformly in the tracker; user can adjust manually.
- Target price = avg_price + (target_profit / total_quantity).
- Securities transaction tax (0.18%) is shown as informational only.
