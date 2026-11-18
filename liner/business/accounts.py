"""Layer 3, Login and accounts: MOCKED. One hard-coded demo user, returned through the same
``authenticate(credentials)`` interface a real implementation would use. Login is not the feature
being demonstrated (Deliverable 1, section 1.4)."""
from __future__ import annotations

from ..models import User


class DemoAuthenticator:
    def __init__(self, user_id: str, name: str):
        self._user = User(user_id, name)

    def authenticate(self, credentials: dict) -> User | None:
        # A real implementation would check the credentials. The mock accepts any request.
        return self._user
