from enum import Enum


class Role(str, Enum):
    """The four v1 roles (AUTH_ARCHITECTURE_4.md - Roles). No others."""

    INVESTIGATING_OFFICER = "investigating_officer"
    SUPERVISOR = "supervisor"
    ANALYST = "analyst"
    ADMIN = "admin"
