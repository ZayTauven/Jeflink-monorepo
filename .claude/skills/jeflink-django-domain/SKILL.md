---
name: jeflink-django-domain
description: Gabarits et conventions pour créer ou modifier un domaine Django de Jeflink (models, services, selectors, API DRF, tâches Celery, tests pytest). Utiliser pour tout ajout de modèle, endpoint, service métier, tâche asynchrone ou test dans apps/api, y compris les petites modifications.
---

# Domaine Django Jeflink

## Modèle de base

```python
# jeflink/common/models.py
import uuid
from django.db import models

class BaseModel(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
```

Argent : `models.PositiveBigIntegerField()` (XOF). Contraintes métier en base via `Meta.constraints`.

## Service (écriture)

```python
# <domaine>/services.py
from django.db import transaction
from jeflink.trust.services import audit

@transaction.atomic
def accept_quote(*, quote: Quote, actor: User) -> Booking:
    if quote.request.client_id != actor.id:
        raise PermissionDenied("not_request_owner")
    booking = Booking.objects.create(request=quote.request, quote=quote, amount_xof=quote.total_xof)
    transition(booking, to=BookingStatus.ACCEPTED, actor=actor, reason="quote_accepted")
    audit(actor=actor, action="quote.accepted", target=booking)
    return booking
```

- Arguments nommés uniquement (`*`), types explicites, `transaction.atomic`.
- Erreurs métier : exceptions du domaine avec code stable (`"not_request_owner"`), traduites en réponses API par un handler commun.

## Sélecteur (lecture)

```python
def bookings_for_pro(*, pro: Provider):
    return (Booking.objects.filter(provider=pro)
            .select_related("request__client", "address")
            .order_by("-scheduled_at"))
```

## API

```python
class AcceptQuoteView(APIView):
    permission_classes = [IsAuthenticated, IsClient]

    @extend_schema(request=None, responses=BookingSerializer)
    def post(self, request, quote_id):
        quote = get_object_or_404(Quote, public_id=quote_id)
        booking = accept_quote(quote=quote, actor=request.user)
        return Response(BookingSerializer(booking).data, status=201)
```

Vue = permissions + désérialisation + appel d'un service + sérialisation. Rien d'autre.

## Tâche Celery

```python
@shared_task(bind=True, autoretry_for=(TransientError,), retry_backoff=True, max_retries=5)
def send_booking_reminder(self, booking_public_id: str):
    booking = Booking.objects.filter(public_id=booking_public_id).first()
    if not booking or booking.reminder_sent_at:
        return  # idempotent
    ...
```

Passer des identifiants, jamais des objets. Toujours idempotent.

## Tests

```python
def test_accept_quote_refused_for_other_client(quote_factory, user_factory):
    quote = quote_factory()
    with pytest.raises(PermissionDenied):
        accept_quote(quote=quote, actor=user_factory())
```

Pour chaque endpoint : autorisé, refusé, invalide. Fakes pour paiements et IA.

## Après modification

1. `make makemigrations` puis relire la migration.
2. `make api-test`.
3. Si l'API a changé : `make openapi`.
