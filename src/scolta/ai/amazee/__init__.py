"""Amazee.ai managed-gateway subsystem (port of ``AiProvider\\Amazee``).

A managed LiteLLM gateway, connected only when an operator opts in. Two explicit
paths establish a connection: the free demo (anonymous, no email) and the
email-OTP account flow, which is also how an operator continues once the demo
credit runs out. Nothing here connects a site on its own — ``AutoProvisioner``
only re-resolves model names against credentials that are already stored. The
returned credentials configure the OpenAI-compatible AiClient path.
"""

from .account_upgrader import AmazeeAccountUpgrader
from .auto_provisioner import AutoProvisioner
from .budget_decorator import BudgetAwareProviderDecorator
from .client import AmazeeClient
from .connection_source import AmazeeConnectionSource
from .exceptions import AmazeeApiException, AmazeeBudgetExceededException
from .key_expiry_recovery import KeyExpiryRecovery
from .model_resolver import AmazeeModelResolver
from .results import ProvisioningResult, UpgradeResult
from .storage import ConfigStorage, ProvenanceAwareConfigStorage
from .trial_provisioner import AmazeeTrialProvisioner

__all__ = [
    "AmazeeAccountUpgrader",
    "AmazeeApiException",
    "AmazeeBudgetExceededException",
    "AmazeeClient",
    "AmazeeConnectionSource",
    "AmazeeModelResolver",
    "AmazeeTrialProvisioner",
    "AutoProvisioner",
    "BudgetAwareProviderDecorator",
    "ConfigStorage",
    "KeyExpiryRecovery",
    "ProvenanceAwareConfigStorage",
    "ProvisioningResult",
    "UpgradeResult",
]
