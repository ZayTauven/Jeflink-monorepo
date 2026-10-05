"""Portefeuille du pro (spec 005, tâche 8) : montants entiers XOF et codes courts. La référence
de transaction ne sort qu'en 4 derniers caractères ; les chiffres du payeur jamais."""

from rest_framework import serializers

from jeflink.payments.models import PaymentIntent, SettlementChannel
from jeflink.wallet.models import Side


class NextRateSerializer(serializers.Serializer):
    rate_bps = serializers.IntegerField()
    cap_xof = serializers.IntegerField(allow_null=True)
    valid_from = serializers.DateTimeField()


class TradeRateSerializer(serializers.Serializer):
    trade_slug = serializers.CharField()
    rate_bps = serializers.IntegerField()
    cap_xof = serializers.IntegerField(allow_null=True)
    next = NextRateSerializer(allow_null=True)


class ChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = SettlementChannel
        fields = (
            "slug", "label_fr", "label_wo", "account_display", "instructions_fr",
            "instructions_wo",
        )  # fmt: skip


class WalletSummarySerializer(serializers.Serializer):
    due_xof = serializers.IntegerField(help_text="Part de Jeflink encore due par le pro")
    credit_xof = serializers.IntegerField(help_text="Avoir du pro (trop-perçu, geste)")
    pending_xof = serializers.IntegerField(help_text="Déclarations qui comptent comme payées")
    effective_due_xof = serializers.IntegerField()
    state = serializers.ChoiceField(choices=["ok", "alert", "blocked"])
    alert_threshold_xof = serializers.IntegerField()
    block_threshold_xof = serializers.IntegerField()
    rates = TradeRateSerializer(many=True)
    channels = ChannelSerializer(many=True)


class EntryBookingSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="public_id")
    trade_slug = serializers.CharField(source="request.trade.slug")
    closed_at = serializers.DateTimeField(allow_null=True)


class WalletEntrySerializer(serializers.Serializer):
    """Une ligne du compte du pro : ``increase`` fait monter ce qu'il doit, ``decrease`` le
    fait baisser."""

    id = serializers.UUIDField(source="transaction.public_id")
    kind = serializers.CharField(source="transaction.kind")
    amount_xof = serializers.IntegerField()
    effect = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    booking = EntryBookingSerializer(source="transaction.booking", allow_null=True)
    reason_code = serializers.CharField(source="transaction.reason_code")

    def get_effect(self, entry) -> str:
        return "increase" if entry.side == Side.DEBIT else "decrease"


class CommissionDetailSerializer(serializers.Serializer):
    base_xof = serializers.IntegerField()
    rate_bps = serializers.IntegerField(allow_null=True)
    cap_xof = serializers.IntegerField(allow_null=True)
    amount_xof = serializers.IntegerField()
    completion_method = serializers.CharField()


class ReversalSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="public_id")
    amount_xof = serializers.IntegerField()
    reason_code = serializers.CharField()
    created_at = serializers.DateTimeField()


class WalletEntryDetailSerializer(WalletEntrySerializer):
    commission = CommissionDetailSerializer(allow_null=True)
    reversals = ReversalSerializer(many=True)


class SettlementSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id")
    channel = serializers.CharField(source="channel.slug")
    reference_hint = serializers.SerializerMethodField(
        help_text="4 derniers caractères de la référence (la référence entière reste à l'Ops)"
    )
    can_cancel = serializers.SerializerMethodField()
    can_correct = serializers.SerializerMethodField()

    class Meta:
        model = PaymentIntent
        fields = (
            "id", "channel", "origin", "status", "declared_xof", "received_xof",
            "reference_hint", "paid_at", "correction_reason", "reject_reason", "created_at",
            "corrected_at", "decided_at", "can_cancel", "can_correct",
        )  # fmt: skip

    def get_reference_hint(self, intent) -> str:
        return intent.reference[-4:]

    def get_can_cancel(self, intent) -> bool:
        return intent.status in PaymentIntent.PENDING_STATUSES

    def get_can_correct(self, intent) -> bool:
        return intent.status == PaymentIntent.Status.NEEDS_CORRECTION


class SettlementCorrectSerializer(serializers.Serializer):
    amount_xof = serializers.IntegerField()
    reference = serializers.CharField(max_length=60)
    paid_at = serializers.DateTimeField()
    payer_last4 = serializers.CharField(max_length=4, required=False, allow_blank=True, default="")


class SettlementCreateSerializer(SettlementCorrectSerializer):
    channel = serializers.SlugField(max_length=40)
