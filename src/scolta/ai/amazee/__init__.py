"""Amazee.ai auto-provisioning subsystem (port of ``AiProvider\\Amazee``).

A managed LiteLLM gateway: provision a free trial (anonymous or by email),
resolve the best Claude models, and upgrade to a private key via an email-OTP
flow. The returned credentials configure the OpenAI-compatible AiClient path.
"""

from .account_upgrader import AmazeeAccountUpgrader
from .auto_provisioner import AutoProvisioner
from .budget_decorator import BudgetAwareProviderDecorator
from .client import AmazeeClient
from .exceptions import AmazeeApiException, AmazeeBudgetExceededException
from .model_resolver import AmazeeModelResolver
from .results import ProvisioningResult, UpgradeResult
from .storage import ConfigStorage
from .trial_provisioner import AmazeeTrialProvisioner

__all__ = [
    "AmazeeAccountUpgrader",
    "AmazeeApiException",
    "AmazeeBudgetExceededException",
    "AmazeeClient",
    "AmazeeModelResolver",
    "AmazeeTrialProvisioner",
    "AutoProvisioner",
    "BudgetAwareProviderDecorator",
    "ConfigStorage",
    "ProvisioningResult",
    "UpgradeResult",
]
