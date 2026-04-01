"""
portfolio_widget.py - PyQt6 widget for the stock portfolio tracker.

Displays per-stock and summary views with:
  - Per-account holdings table (cost, current value, P&L)
  - Blended average price and target price
  - Dividend information (Samsung)
  - Price history table
  - Current-price input to refresh all calculations
  - Save button to persist data via PortfolioStorage
"""

from datetime import date as _date

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from portfolio_model import Portfolio, StockHolding
from portfolio_storage import PortfolioStorage


def _fmt_krw(value: int) -> str:
    """Format an integer KRW value with thousand separators and a ₩ prefix."""
    sign = "-" if value < 0 else ""
    return f"{sign}₩{abs(value):,}"


def _colored_item(text: str, value: int) -> QTableWidgetItem:
    """
    Create a right-aligned QTableWidgetItem coloured by value sign.

    Args:
        text: Display string for the cell.
        value: Numeric value used only to determine colour (positive=green,
               negative=red, zero=default).

    Returns:
        A QTableWidgetItem ready to insert into a QTableWidget.
    """
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if value > 0:
        item.setForeground(QColor("#2ecc71"))
    elif value < 0:
        item.setForeground(QColor("#e74c3c"))
    return item


def _plain_item(text: str, align_right: bool = True) -> QTableWidgetItem:
    """
    Create a non-editable QTableWidgetItem.

    Args:
        text: Display string.
        align_right: If True, right-align; otherwise left-align.

    Returns:
        A read-only QTableWidgetItem.
    """
    item = QTableWidgetItem(text)
    flags = item.flags() & ~Qt.ItemFlag.ItemIsEditable
    item.setFlags(flags)
    if align_right:
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
    else:
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
    return item


class StockTab(QWidget):
    """Tab widget displaying detailed information for a single stock."""

    def __init__(self, stock: StockHolding, parent: QWidget | None = None) -> None:
        """
        Initialise the StockTab.

        Args:
            stock: The StockHolding to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._stock = stock
        self._current_price: int = 0
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build and lay out all child widgets."""
        layout = QVBoxLayout(self)

        # ── Price input row ──────────────────────────────────────────────────
        price_row = QHBoxLayout()
        price_row.addWidget(QLabel("현재가 (KRW):"))
        self._price_spin = QSpinBox()
        self._price_spin.setRange(0, 100_000_000)
        self._price_spin.setSingleStep(100)
        self._price_spin.setValue(0)
        self._price_spin.setFixedWidth(140)
        self._price_spin.valueChanged.connect(self._on_price_changed)
        price_row.addWidget(self._price_spin)
        price_row.addStretch()
        layout.addLayout(price_row)

        # ── Key metrics ──────────────────────────────────────────────────────
        metrics_box = QGroupBox("주요 지표")
        metrics_layout = QHBoxLayout(metrics_box)

        self._lbl_avg = QLabel("평균단가: -")
        self._lbl_target = QLabel("목표주가: -")
        self._lbl_pnl = QLabel("평가손익: -")
        self._lbl_pnl_rate = QLabel("수익률: -")
        for lbl in (self._lbl_avg, self._lbl_target, self._lbl_pnl, self._lbl_pnl_rate):
            lbl.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            metrics_layout.addWidget(lbl)
        layout.addWidget(metrics_box)

        # ── Target progress bar ──────────────────────────────────────────────
        prog_box = QGroupBox("목표수익 달성률")
        prog_layout = QVBoxLayout(prog_box)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFormat("%p%  (목표: " + _fmt_krw(self._stock.target_profit) + ")")
        prog_layout.addWidget(self._progress)
        layout.addWidget(prog_box)

        # ── Holdings table ───────────────────────────────────────────────────
        holdings_box = QGroupBox("계좌별 보유 현황")
        holdings_layout = QVBoxLayout(holdings_box)
        headers = ["계좌", "수량", "평균단가", "매입금액", "평가금액", "평가손익", "수익률"]
        self._holdings_table = QTableWidget(0, len(headers))
        self._holdings_table.setHorizontalHeaderLabels(headers)
        self._holdings_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._holdings_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._holdings_table.setAlternatingRowColors(True)
        holdings_layout.addWidget(self._holdings_table)
        layout.addWidget(holdings_box)

        # ── Dividend info (only shown when dividend_per_share > 0) ───────────
        if self._stock.dividend_per_share > 0:
            div_box = QGroupBox("배당 정보")
            div_layout = QHBoxLayout(div_box)
            self._lbl_div_gross = QLabel()
            self._lbl_div_net = QLabel()
            div_layout.addWidget(self._lbl_div_gross)
            div_layout.addWidget(self._lbl_div_net)
            div_layout.addStretch()
            layout.addWidget(div_box)
            self._div_box = div_box
        else:
            self._div_box = None

        # ── Price history table ──────────────────────────────────────────────
        hist_box = QGroupBox("수익률 기록")
        hist_layout = QVBoxLayout(hist_box)
        hist_headers = ["날짜", "종가", "평가손익"]
        self._history_table = QTableWidget(0, len(hist_headers))
        self._history_table.setHorizontalHeaderLabels(hist_headers)
        self._history_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._history_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._history_table.setAlternatingRowColors(True)
        self._history_table.setMaximumHeight(160)
        hist_layout.addWidget(self._history_table)
        layout.addWidget(hist_box)

        layout.addStretch()

        # Initial render with price = 0
        self._refresh_all()

    def _on_price_changed(self, value: int) -> None:
        """
        Slot called when the price spin-box value changes.

        Args:
            value: New price in KRW.
        """
        self._current_price = value
        self._refresh_all()

    def _refresh_all(self) -> None:
        """Recompute and refresh every displayed value using the current price."""
        price = self._current_price
        stock = self._stock

        avg = stock.blended_avg_price
        target = stock.target_price()
        pnl = stock.total_pnl(price) if price else 0
        cost = stock.total_cost
        pnl_rate = (pnl / cost * 100) if cost else 0.0

        self._lbl_avg.setText(f"평균단가: {_fmt_krw(avg)}")
        self._lbl_target.setText(f"목표주가: {_fmt_krw(target)}")

        pnl_color = "#2ecc71" if pnl >= 0 else "#e74c3c"
        self._lbl_pnl.setText(
            f'<span style="color:{pnl_color}">'
            f"평가손익: {_fmt_krw(pnl)}"
            f"</span>"
        )
        self._lbl_pnl.setTextFormat(Qt.TextFormat.RichText)

        rate_color = "#2ecc71" if pnl_rate >= 0 else "#e74c3c"
        self._lbl_pnl_rate.setText(
            f'<span style="color:{rate_color}">'
            f"수익률: {pnl_rate:+.2f}%"
            f"</span>"
        )
        self._lbl_pnl_rate.setTextFormat(Qt.TextFormat.RichText)

        # Progress toward target profit
        if price and stock.target_profit > 0:
            pct = max(0, min(100, int(pnl / stock.target_profit * 100)))
        else:
            pct = 0
        self._progress.setValue(pct)

        self._refresh_holdings_table(price)
        self._refresh_history_table()

        if self._div_box:
            gross = stock.annual_dividend_gross()
            net = stock.annual_dividend_net()
            self._lbl_div_gross.setText(
                f"연간 세전 배당: {_fmt_krw(gross)} "
                f"(주당 {_fmt_krw(stock.dividend_per_share)})"
            )
            self._lbl_div_net.setText(f"연간 세후 배당 (15.4% 차감): {_fmt_krw(net)}")

    def _refresh_holdings_table(self, price: int) -> None:
        """
        Repopulate the holdings table for the given price.

        Args:
            price: Current market price per share (KRW).
        """
        stock = self._stock
        rows = stock.accounts + [None]  # None = totals row
        self._holdings_table.setRowCount(len(rows))

        total_qty = 0
        total_cost = 0
        total_value = 0
        total_pnl = 0

        for r, acc in enumerate(stock.accounts):
            value = acc.quantity * price if price else 0
            pnl = acc.pnl(price) if price else 0
            rate = acc.pnl_rate(price) if price else 0.0
            total_qty += acc.quantity
            total_cost += acc.cost
            total_value += value
            total_pnl += pnl

            self._holdings_table.setItem(r, 0, _plain_item(acc.account, align_right=False))
            self._holdings_table.setItem(r, 1, _plain_item(f"{acc.quantity:,}"))
            self._holdings_table.setItem(r, 2, _plain_item(_fmt_krw(acc.avg_price)))
            self._holdings_table.setItem(r, 3, _plain_item(_fmt_krw(acc.cost)))
            self._holdings_table.setItem(r, 4, _plain_item(_fmt_krw(value) if price else "-"))
            self._holdings_table.setItem(r, 5, _colored_item(_fmt_krw(pnl) if price else "-", pnl))
            self._holdings_table.setItem(
                r, 6, _colored_item(f"{rate:+.2f}%" if price else "-", pnl)
            )

        # Totals row
        tr = len(stock.accounts)
        bold = QFont()
        bold.setBold(True)

        def bold_item(text: str, value: int = 0, colored: bool = False) -> QTableWidgetItem:
            """Create a bold table item, optionally coloured by sign."""
            item = _colored_item(text, value) if colored else _plain_item(text)
            item.setFont(bold)
            return item

        total_rate = (total_pnl / total_cost * 100) if total_cost else 0.0
        self._holdings_table.setItem(tr, 0, bold_item("합산", align_right=False) if False else _plain_item("합산", align_right=False))
        self._holdings_table.item(tr, 0).setFont(bold)
        self._holdings_table.setItem(tr, 1, bold_item(f"{total_qty:,}"))
        self._holdings_table.setItem(tr, 2, bold_item(_fmt_krw(stock.blended_avg_price)))
        self._holdings_table.setItem(tr, 3, bold_item(_fmt_krw(total_cost)))
        self._holdings_table.setItem(
            tr, 4, bold_item(_fmt_krw(total_value) if price else "-")
        )
        self._holdings_table.setItem(
            tr, 5, _colored_item(_fmt_krw(total_pnl) if price else "-", total_pnl)
        )
        self._holdings_table.item(tr, 5).setFont(bold)
        self._holdings_table.setItem(
            tr, 6, _colored_item(f"{total_rate:+.2f}%" if price else "-", total_pnl)
        )
        self._holdings_table.item(tr, 6).setFont(bold)

    def _refresh_history_table(self) -> None:
        """Repopulate the price history table from price_history data."""
        history = self._stock.price_history
        self._history_table.setRowCount(len(history))
        for r, record in enumerate(reversed(history)):
            pnl = record.get("pnl", 0)
            self._history_table.setItem(r, 0, _plain_item(record.get("date", ""), align_right=False))
            self._history_table.setItem(r, 1, _plain_item(_fmt_krw(record.get("price", 0))))
            self._history_table.setItem(
                r, 2, _colored_item(_fmt_krw(pnl) if pnl else "-", pnl)
            )

    def current_price(self) -> int:
        """Return the currently entered price in the spin-box."""
        return self._price_spin.value()

    def set_price(self, price: int) -> None:
        """
        Programmatically set the current price in the spin-box.

        Args:
            price: Price to set (KRW).
        """
        self._price_spin.setValue(price)


class SummaryTab(QWidget):
    """Tab showing combined portfolio totals across all stocks."""

    def __init__(self, portfolio: Portfolio, parent: QWidget | None = None) -> None:
        """
        Initialise the SummaryTab.

        Args:
            portfolio: The Portfolio instance to summarise.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._portfolio = portfolio
        self._prices: dict[str, int] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build and lay out all child widgets."""
        layout = QVBoxLayout(self)

        summary_box = QGroupBox("전체 포트폴리오 요약")
        summary_layout = QVBoxLayout(summary_box)

        headers = ["종목", "수량", "총 투자금", "평가금액", "평가손익", "수익률", "투자비중"]
        self._table = QTableWidget(0, len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        summary_layout.addWidget(self._table)
        layout.addWidget(summary_box)

        # Bottom totals
        totals_box = QGroupBox("합산")
        totals_layout = QHBoxLayout(totals_box)
        self._lbl_total_cost = QLabel("총 투자금: -")
        self._lbl_total_value = QLabel("총 평가금액: -")
        self._lbl_total_pnl = QLabel("총 평가손익: -")
        for lbl in (self._lbl_total_cost, self._lbl_total_value, self._lbl_total_pnl):
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            totals_layout.addWidget(lbl)
        layout.addWidget(totals_box)

        layout.addStretch()
        self._refresh()

    def update_prices(self, prices: dict[str, int]) -> None:
        """
        Accept a mapping of ticker → current price and refresh the display.

        Args:
            prices: Dict mapping KRX ticker strings to integer KRW prices.
        """
        self._prices = prices
        self._refresh()

    def _refresh(self) -> None:
        """Recompute all summary values and repopulate the table."""
        portfolio = self._portfolio
        total_cost = portfolio.total_cost

        rows = portfolio.stocks + [None]
        self._table.setRowCount(len(portfolio.stocks) + 1)

        agg_cost = 0
        agg_value = 0
        agg_pnl = 0

        for r, stock in enumerate(portfolio.stocks):
            price = self._prices.get(stock.ticker, 0)
            cost = stock.total_cost
            value = stock.total_quantity * price if price else 0
            pnl = stock.total_pnl(price) if price else 0
            rate = (pnl / cost * 100) if cost else 0.0
            weight = (cost / total_cost * 100) if total_cost else 0.0

            agg_cost += cost
            agg_value += value
            agg_pnl += pnl

            self._table.setItem(r, 0, _plain_item(stock.name, align_right=False))
            self._table.setItem(r, 1, _plain_item(f"{stock.total_quantity:,}"))
            self._table.setItem(r, 2, _plain_item(_fmt_krw(cost)))
            self._table.setItem(r, 3, _plain_item(_fmt_krw(value) if price else "-"))
            self._table.setItem(r, 4, _colored_item(_fmt_krw(pnl) if price else "-", pnl))
            self._table.setItem(r, 5, _colored_item(f"{rate:+.2f}%" if price else "-", pnl))
            self._table.setItem(r, 6, _plain_item(f"{weight:.1f}%"))

        # Totals row
        tr = len(portfolio.stocks)
        bold = QFont()
        bold.setBold(True)
        agg_rate = (agg_pnl / agg_cost * 100) if agg_cost else 0.0

        total_items = [
            ("합계", False),
            (f"{sum(s.total_quantity for s in portfolio.stocks):,}", True),
            (_fmt_krw(agg_cost), True),
            (_fmt_krw(agg_value) if self._prices else "-", True),
            (_fmt_krw(agg_pnl) if self._prices else "-", True),
            (f"{agg_rate:+.2f}%" if self._prices else "-", True),
            ("100%", True),
        ]
        for c, (text, right) in enumerate(total_items):
            if c in (4, 5):
                item = _colored_item(text, agg_pnl)
            else:
                item = _plain_item(text, align_right=right)
            item.setFont(bold)
            self._table.setItem(tr, c, item)

        self._lbl_total_cost.setText(f"총 투자금: {_fmt_krw(agg_cost)}")
        self._lbl_total_value.setText(
            f"총 평가금액: {_fmt_krw(agg_value) if self._prices else '-'}"
        )
        pnl_color = "#2ecc71" if agg_pnl >= 0 else "#e74c3c"
        self._lbl_total_pnl.setText(
            f'<span style="color:{pnl_color}">총 평가손익: {_fmt_krw(agg_pnl) if self._prices else "-"}</span>'
        )
        self._lbl_total_pnl.setTextFormat(Qt.TextFormat.RichText)


class PortfolioWidget(QWidget):
    """
    Top-level portfolio tracker widget.

    Contains a tab per stock plus a summary tab.  A Save button persists
    the portfolio (including any new price-history records) via PortfolioStorage.
    """

    def __init__(
        self,
        storage: PortfolioStorage | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """
        Initialise the PortfolioWidget.

        Args:
            storage: Optional PortfolioStorage instance (creates one if None).
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._storage = storage or PortfolioStorage()
        self._portfolio = self._storage.load()
        self._stock_tabs: dict[str, StockTab] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build and lay out all child widgets."""
        layout = QVBoxLayout(self)

        # Tab widget
        self._tabs = QTabWidget()

        for stock in self._portfolio.stocks:
            tab = StockTab(stock)
            self._stock_tabs[stock.ticker] = tab
            self._tabs.addTab(tab, stock.name)

        self._summary_tab = SummaryTab(self._portfolio)
        self._tabs.addTab(self._summary_tab, "전체 요약")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs)

        # Bottom button row
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_save = QPushButton("저장")
        self._btn_save.setFixedWidth(80)
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_save)

        self._btn_reset = QPushButton("초기화")
        self._btn_reset.setFixedWidth(80)
        self._btn_reset.clicked.connect(self._on_reset)
        btn_row.addWidget(self._btn_reset)

        layout.addLayout(btn_row)

    def _collect_prices(self) -> dict[str, int]:
        """
        Read the current price from each stock tab.

        Returns:
            Dict mapping ticker → price (0 if not entered).
        """
        return {
            ticker: tab.current_price()
            for ticker, tab in self._stock_tabs.items()
        }

    def _on_tab_changed(self, index: int) -> None:
        """
        Slot called when the active tab changes.

        Refreshes the summary tab whenever it becomes visible so that
        current prices from stock tabs are reflected.

        Args:
            index: Zero-based index of the newly selected tab.
        """
        summary_index = self._tabs.count() - 1
        if index == summary_index:
            self._summary_tab.update_prices(self._collect_prices())

    def _on_save(self) -> None:
        """
        Save the current portfolio to storage.

        Appends a price-history record for each stock whose price spin-box
        is non-zero, then persists the portfolio.
        """
        today = str(_date.today())
        for ticker, tab in self._stock_tabs.items():
            price = tab.current_price()
            if price:
                stock = self._portfolio.find_stock(ticker)
                if stock:
                    stock.append_price_history(today, price)
        self._portfolio.last_updated = today
        self._storage.save(self._portfolio)

    def _on_reset(self) -> None:
        """Reset storage to the factory default and reload the widget."""
        self._portfolio = self._storage.reset()
        self._stock_tabs.clear()
        # Remove all tabs except summary
        while self._tabs.count():
            self._tabs.removeTab(0)
        for stock in self._portfolio.stocks:
            tab = StockTab(stock)
            self._stock_tabs[stock.ticker] = tab
            self._tabs.insertTab(self._tabs.count(), tab, stock.name)
        self._summary_tab = SummaryTab(self._portfolio)
        self._tabs.addTab(self._summary_tab, "전체 요약")
