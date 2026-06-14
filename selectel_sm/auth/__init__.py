"""
Authentication providers for selectel-sm.
"""

from __future__ import annotations

from selectel_sm.auth.base import AuthProvider
from selectel_sm.auth.password import PasswordAuth
from selectel_sm.auth.static import StaticTokenAuth

__all__ = ["AuthProvider", "PasswordAuth", "StaticTokenAuth"]
