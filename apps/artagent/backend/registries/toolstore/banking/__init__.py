"""
Banking Tools Module

Auto-registers all banking-related tools when this package is imported.
Includes tools for:
- BankingConcierge agent (profiles, accounts, transactions)
- CardRecommendation agent (card search, eligibility, e-signature, FAQs)
- InvestmentAdvisor agent (401k, retirement accounts, rollovers)
"""

# Import tool modules to trigger registration
from . import banking
from . import investments

# email_templates is a helper module (no tool registration)
# constants is a data module (no tool registration)

__all__ = [
    "banking",
    "investments",
]
