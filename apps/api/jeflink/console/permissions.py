"""Qui voit quoi dans la console : chaque vue déclare sa rubrique, chaque rôle a ses rubriques.

| Rubrique   | Super admin | Opérations | Marketing | Finance |
| ---------- | :---------: | :--------: | :-------: | :-----: |
| dashboard  |      ✓      |     ✓      |     ✓     |    ✓    |
| operations |      ✓      |     ✓      |           |         |
| catalog    |      ✓      |     ✓      |     ✓     |         |
| marketing  |      ✓      |            |     ✓     |         |
| finance    |      ✓      |            |           |    ✓    |
| admin      |      ✓      |            |           |         |
"""

from rest_framework.permissions import BasePermission

from jeflink.accounts.models import User

R = User.StaffRole
SECTIONS: dict[str, set[str]] = {
    "dashboard": {R.SUPER, R.OPS, R.MARKETING, R.FINANCE},
    "operations": {R.SUPER, R.OPS},
    "catalog": {R.SUPER, R.OPS, R.MARKETING},
    "marketing": {R.SUPER, R.MARKETING},
    "finance": {R.SUPER, R.FINANCE},
    "admin": {R.SUPER},
}


def can(user, section: str) -> bool:
    return bool(
        user and user.is_authenticated and user.is_staff and user.console_role in SECTIONS[section]
    )


def sections_for(user) -> list[str]:
    return [name for name in SECTIONS if can(user, name)]


class ConsoleSection(BasePermission):
    """Accès à la vue si le rôle de l'utilisateur couvre sa rubrique (`console_section`)."""

    message = "Cette rubrique de la console n'est pas ouverte à votre rôle."

    def has_permission(self, request, view):
        return can(request.user, getattr(view, "console_section", "admin"))


def section(name: str):
    """Permission pour une vue fonction : `@permission_classes([section("dashboard")])`."""

    class _Section(ConsoleSection):
        def has_permission(self, request, view):
            return can(request.user, name)

    return _Section
