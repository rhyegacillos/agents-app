from pydantic import BaseModel
import json
import os
from dotenv import load_dotenv
from datetime import datetime
from market import get_share_price, get_share_price_with_source
from database import write_account, read_account, write_log
from runtime_status import read_runtime_status

load_dotenv(override=True)

INITIAL_BALANCE = 10_000.0
SPREAD = 0.002


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# When enabled, report() freezes valuation between trade executions.
STRICT_FLAT_WHEN_NO_TRADE = _env_bool("STRICT_FLAT_WHEN_NO_TRADE", True)


class Transaction(BaseModel):
    symbol: str
    quantity: int
    price: float
    timestamp: str
    rationale: str

    def total(self) -> float:
        return self.quantity * self.price
    
    def __repr__(self):
        return f"{abs(self.quantity)} shares of {self.symbol} at {self.price} each."


class Account(BaseModel):
    name: str
    balance: float
    strategy: str
    holdings: dict[str, int]
    transactions: list[Transaction]
    portfolio_value_time_series: list[tuple[str, float]]

    @classmethod
    def get(cls, name: str):
        fields = read_account(name.lower())
        if not fields:
            fields = {
                "name": name.lower(),
                "balance": INITIAL_BALANCE,
                "strategy": "",
                "holdings": {},
                "transactions": [],
                "portfolio_value_time_series": []
            }
            write_account(name, fields)
        account = cls(**fields)

        # Backward-compatible data migration for older persisted accounts:
        # when strict-flat mode is enabled and no timeline exists yet, seed one
        # baseline snapshot so portfolio reporting is stable without requiring reset.
        if STRICT_FLAT_WHEN_NO_TRADE and not account.portfolio_value_time_series:
            seeded_value = account.calculate_portfolio_value() if account.holdings else float(account.balance)
            account.portfolio_value_time_series.append(
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), float(seeded_value))
            )
            account.save()

        return account
    
    
    def save(self):
        write_account(self.name.lower(), self.model_dump())

    def _append_portfolio_snapshot(self) -> float:
        """Capture one timeline point for portfolio charting."""
        portfolio_value = self.calculate_portfolio_value()
        self.portfolio_value_time_series.append(
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), portfolio_value)
        )
        return portfolio_value

    def _frozen_portfolio_value(self) -> float:
        """Return the last recorded valuation, falling back to current balance."""
        if self.portfolio_value_time_series:
            return float(self.portfolio_value_time_series[-1][1])
        return float(self.balance)

    def reset(self, strategy: str):
        self.balance = INITIAL_BALANCE
        self.strategy = strategy
        self.holdings = {}
        self.transactions = []
        self.portfolio_value_time_series = []
        self.portfolio_value_time_series.append(
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.balance)
        )
        self.save()

    def deposit(self, amount: float):
        """ Deposit funds into the account. """
        if amount <= 0:
            raise ValueError("Deposit amount must be positive.")
        self.balance += amount
        print(f"Deposited ${amount}. New balance: ${self.balance}")
        self.save()

    def withdraw(self, amount: float):
        """ Withdraw funds from the account, ensuring it doesn't go negative. """
        if amount > self.balance:
            raise ValueError("Insufficient funds for withdrawal.")
        self.balance -= amount
        print(f"Withdrew ${amount}. New balance: ${self.balance}")
        self.save()

    def buy_shares(self, symbol: str, quantity: int, rationale: str) -> str:
        """ Buy shares of a stock if sufficient funds are available. """
        if quantity <= 0:
            raise ValueError("Quantity must be greater than 0.")
        price, source = get_share_price_with_source(symbol)
        buy_price = price * (1 + SPREAD)
        total_cost = buy_price * quantity
        
        if total_cost > self.balance:
            raise ValueError("Insufficient funds to buy shares.")
        elif price <= 0:
            raise ValueError(f"Unable to find market price for {symbol}")
        
        # Update holdings
        self.holdings[symbol] = self.holdings.get(symbol, 0) + quantity
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Record transaction
        transaction = Transaction(symbol=symbol, quantity=quantity, price=buy_price, timestamp=timestamp, rationale=rationale)
        self.transactions.append(transaction)
        
        # Update balance
        self.balance -= total_cost
        self._append_portfolio_snapshot()
        self.save()
        write_log(self.name, "account", f"{symbol.upper()} - {price:.2f} - {source}")
        write_log(self.name, "account", f"Bought {quantity} of {symbol}")
        return "Completed. Latest details:\n" + self.report()

    def sell_shares(self, symbol: str, quantity: int, rationale: str) -> str:
        """ Sell shares of a stock if the user has enough shares. """
        if quantity <= 0:
            raise ValueError("Quantity must be greater than 0.")
        if self.holdings.get(symbol, 0) < quantity:
            raise ValueError(f"Cannot sell {quantity} shares of {symbol}. Not enough shares held.")
        
        price, source = get_share_price_with_source(symbol)
        if price <= 0:
            raise ValueError(f"Unable to find market price for {symbol}")
        sell_price = price * (1 - SPREAD)
        total_proceeds = sell_price * quantity
        
        # Update holdings
        self.holdings[symbol] -= quantity
        
        # If shares are completely sold, remove from holdings
        if self.holdings[symbol] == 0:
            del self.holdings[symbol]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Record transaction
        transaction = Transaction(symbol=symbol, quantity=-quantity, price=sell_price, timestamp=timestamp, rationale=rationale)  # negative quantity for sell
        self.transactions.append(transaction)

        # Update balance
        self.balance += total_proceeds
        self._append_portfolio_snapshot()
        self.save()
        write_log(self.name, "account", f"{symbol.upper()} - {price:.2f} - {source}")
        write_log(self.name, "account", f"Sold {quantity} of {symbol}")
        return "Completed. Latest details:\n" + self.report()

    def calculate_portfolio_value(self):
        """ Calculate the total value of the user's portfolio. """
        return float(self.balance) + self.calculate_holdings_market_value()

    def calculate_holdings_market_value(self) -> float:
        """Calculate the market value of current holdings only (excludes cash)."""
        holdings_value = 0.0
        for symbol, quantity in self.holdings.items():
            holdings_value += get_share_price(symbol) * quantity
        return float(holdings_value)

    def calculate_profit_loss(self, portfolio_value: float):
        """ Calculate profit or loss from the initial spend. """
        initial_spend = sum(transaction.total() for transaction in self.transactions)
        return portfolio_value - initial_spend - self.balance

    def get_holdings(self):
        """ Report the current holdings of the user. """
        return self.holdings

    def get_profit_loss(self):
        """ Report the user's profit or loss at any point in time. """
        return self.calculate_profit_loss()

    def list_transactions(self):
        """ List all transactions made by the user. """
        return [transaction.model_dump() for transaction in self.transactions]
    
    def report(self) -> str:
        """ Return a json string representing the account.  """
        cash_balance = float(self.balance)
        if STRICT_FLAT_WHEN_NO_TRADE:
            total_equity = float(self._frozen_portfolio_value())
            holdings_market_value = max(0.0, total_equity - cash_balance)
        else:
            holdings_market_value = self.calculate_holdings_market_value()
            total_equity = cash_balance + holdings_market_value

        pnl = self.calculate_profit_loss(total_equity)
        data = self.model_dump()
        data["cash_balance"] = cash_balance
        data["holdings_market_value"] = holdings_market_value
        data["total_equity"] = total_equity
        # Backward-compatible key used across existing API/UI paths.
        data["total_portfolio_value"] = total_equity
        data["total_profit_loss"] = pnl
        if bool(read_runtime_status().get("run_in_progress", False)):
            write_log(self.name, "account", "Retrieved account details")
        return json.dumps(data)
    
    def get_strategy(self) -> str:
        """ Return the strategy of the account """
        return self.strategy
    
    def change_strategy(self, strategy: str) -> str:
        """ At your discretion, if you choose to, call this to change your investment strategy for the future """
        self.strategy = strategy
        self.save()
        return "Changed strategy"

# Example of usage:
if __name__ == "__main__":
    account = Account("John Doe")
    account.deposit(1000)
    account.buy_shares("AAPL", 5)
    account.sell_shares("AAPL", 2)
    print(f"Current Holdings: {account.get_holdings()}")
    print(f"Total Portfolio Value: {account.calculate_portfolio_value()}")
    print(f"Profit/Loss: {account.get_profit_loss()}")
    print(f"Transactions: {account.list_transactions()}")
