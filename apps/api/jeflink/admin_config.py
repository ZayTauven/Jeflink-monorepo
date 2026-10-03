"""Site d'administration Django par défaut de Jeflink : second facteur et limite de débit.

Module volontairement léger (chargé avec ``INSTALLED_APPS``, avant les modèles) : le site
lui-même vit dans ``jeflink.accounts.admin_site``.
"""

from django.contrib.admin.apps import AdminConfig


class JeflinkAdminConfig(AdminConfig):
    default_site = "jeflink.accounts.admin_site.JeflinkAdminSite"
