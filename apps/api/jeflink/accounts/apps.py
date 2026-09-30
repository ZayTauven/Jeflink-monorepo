from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "jeflink.accounts"
    label = "accounts"
    verbose_name = "Comptes"

    def ready(self) -> None:
        from jeflink.trust.services import MaskedPhone, PhoneHmac, register_audit_schema

        role_fields: dict[str, type] = {
            "role": str,
            "reason_code": str,
            "operator": str,
            "second_operator": str,
        }
        register_audit_schema("accounts.role.granted", role_fields)
        register_audit_schema("accounts.role.revoked", role_fields)
        register_audit_schema(
            "accounts.ops_groups.changed",
            {
                "groups_added": list,
                "groups_removed": list,
                "operator": str,
                "second_operator": str,
                "reason_code": str,
                "bootstrap": bool,
            },
        )
        register_audit_schema(
            "accounts.otp.phone_blocked",
            {"phone_masked": MaskedPhone, "phone_hmac": PhoneHmac, "level": int, "hours": int},
        )
        register_audit_schema(
            "ops.accounts.otp_unblocked", {"phone_hmac": PhoneHmac, "reason_code": str}
        )
        register_audit_schema("system.sms_cap.reached", {"cap": str, "region": str})
        register_audit_schema("accounts.session.revoked", {"reason": str, "app": str})
        register_audit_schema("accounts.session.refresh_reuse_detected", {"app": str})
        register_audit_schema("accounts.session.evicted_limit", {"app": str})
        register_audit_schema("accounts.dormant.cleared", {"reason_code": str})
