"""
bank_simulator.py

A standalone "quick simulation" of a savings/bank account: a starting
balance plus a fixed deposit every month, with no market exposure. This
is intentionally separate from the investing simulation so it can be run
on its own as a quick sanity check or comparison baseline.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class BankSimulationResult:
    balance_by_month: List[float]  # index 0 = starting balance

    @property
    def starting_balance(self) -> float:
        return self.balance_by_month[0]

    @property
    def ending_balance(self) -> float:
        return self.balance_by_month[-1]

    @property
    def total_deposited(self) -> float:
        return self.ending_balance - self.starting_balance


def run_bank_simulation(months: int, starting_balance: float = 10_000.0,
                         monthly_deposit: float = 300.0,
                         annual_interest_rate: float = 0.0) -> BankSimulationResult:
    """
    Simulate a simple savings account.

    Args:
        months: number of months to simulate.
        starting_balance: opening balance (default 10,000€ per the brief).
        monthly_deposit: fixed amount deposited each month (default 300€).
        annual_interest_rate: optional interest rate, 0 by default. The
            brief only asked for deposits with no growth, but this makes
            the feature useful for comparing against real savings products
            later without a code change.

    Returns:
        A BankSimulationResult with the month-by-month balance.
    """
    monthly_rate = annual_interest_rate / 12
    balance = starting_balance
    balances = [balance]
    for _ in range(months):
        balance = balance * (1 + monthly_rate) + monthly_deposit
        balances.append(balance)
    return BankSimulationResult(balance_by_month=balances)
