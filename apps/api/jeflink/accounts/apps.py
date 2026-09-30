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
        register_audit_schema("accounts.user.created", {"app": str})
        register_audit_schema(
            "accounts.otp.verified",
            {"app": str, "is_new_user": bool, "restricted": bool, "replay": bool},
        )
        register_audit_schema("accounts.otp.login_refused", {"reason": str, "app": str})
        register_audit_schema("accounts.otp.locked", {"phone_hmac": PhoneHmac, "app": str})
        register_audit_schema("accounts.user.deleted", {"reason": str})
        register_audit_schema("accounts.deletion.blocked", {"reasons": list})
        register_audit_schema("accounts.mfa.enrolled", {})
        register_audit_schema("accounts.mfa.verified", {})
        register_audit_schema("accounts.mfa.step_up", {})
        register_audit_schema("accounts.mfa.enrollment_issued", {"operator": str})
        register_audit_schema("accounts.mfa.failed", {"stage": str, "locked": bool})
        register_audit_schema("accounts.mfa.locked", {})
        register_audit_schema(
            "accounts.mfa.reset",
            {"operator": str, "second_operator": str, "reason_code": str},
        )
        invitation_fields: dict[str, type] = {"role": str, "invitation": str, "invited_by": str}
        register_audit_schema("accounts.invitation.accepted", invitation_fields)
        register_audit_schema("accounts.invitation.declined", invitation_fields)
        register_audit_schema(
            "accounts.invitation.created",
            {"role": str, "invitation": str, "phone_hmac": PhoneHmac, "sms_queued": bool},
        )
