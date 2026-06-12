from __future__ import annotations
import time
from datetime import date, timedelta

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetCalendarRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest
from alpaca.common.exceptions import APIError

from thesis_engine.config import ALPACA_API_KEY, ALPACA_SECRET_KEY


class AlpacaClient:
    def __init__(self):
        self._trading = TradingClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
            paper=True,
        )
        self._data = StockHistoricalDataClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
        )

    def get_account(self) -> dict:
        acct = self._trading.get_account()
        return {
            "equity": float(acct.equity),
            "cash": float(acct.cash),
            "buying_power": float(acct.buying_power),
        }

    def place_market_order(self, symbol: str, qty: int) -> dict:
        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        order = self._trading.submit_order(req)
        return {"order_id": str(order.id), "status": str(order.status)}

    def poll_order_until_filled(self, order_id: str, timeout: float = 10.0, interval: float = 0.5) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            order = self._trading.get_order_by_id(order_id)
            if order.status == OrderStatus.FILLED:
                return {
                    "order_id": str(order.id),
                    "filled_avg_price": float(order.filled_avg_price),
                    "filled_qty": int(float(order.filled_qty)),
                    "filled_at": str(order.filled_at),
                }
            time.sleep(interval)
        raise TimeoutError(f"Order {order_id} did not fill within {timeout}s")

    def close_position(self, symbol: str) -> dict:
        order = self._trading.close_position(symbol)
        return {"order_id": str(order.id), "status": str(order.status)}

    def poll_position_closed(self, symbol: str, timeout: float = 10.0, interval: float = 0.5) -> float:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                pos = self._trading.get_open_position(symbol)
                _ = pos  # still open
            except APIError:
                # position no longer exists — it's closed
                # fetch the most recent order to get exit price
                orders = self._trading.get_orders()
                for o in orders:
                    if str(o.symbol) == symbol and o.status == OrderStatus.FILLED and o.side.value == "sell":
                        return float(o.filled_avg_price)
                return 0.0
            time.sleep(interval)
        raise TimeoutError(f"Position {symbol} did not close within {timeout}s")

    def get_open_positions(self) -> list[dict]:
        positions = self._trading.get_all_positions()
        return [
            {
                "symbol": str(p.symbol),
                "qty": int(float(p.qty)),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
                "avg_entry_price": float(p.avg_entry_price),
            }
            for p in positions
        ]

    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        req = StockLatestTradeRequest(symbol_or_symbols=symbols)
        trades = self._data.get_stock_latest_trade(req)
        return {sym: float(trades[sym].price) for sym in symbols if sym in trades}

    def is_trading_day(self, check_date: date | None = None) -> bool:
        if check_date is None:
            check_date = date.today()
        start = check_date - timedelta(days=1)
        end = check_date + timedelta(days=1)
        calendar = self._trading.get_calendar(
            filters=GetCalendarRequest(start=start, end=end)
        )
        trading_days = {c.date.strftime("%Y-%m-%d") for c in calendar}
        return check_date.strftime("%Y-%m-%d") in trading_days
