"""Compte du grand livre protégé en base (revue sécurité de la spec 005, constat 7) : aucune
suppression, et une mise à jour ne change ni le type, ni le pro, ni le canal (seule la date
de relance évolue ; ``created_at`` est tronqué par le rechargement des données de test). Changer le
type, le pro ou le canal d'un compte déplacerait une dette."""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION wallet_ledgeraccount_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND
       ROW(NEW.id, NEW.kind, NEW.provider_id, NEW.channel_id)
       IS NOT DISTINCT FROM
       ROW(OLD.id, OLD.kind, OLD.provider_id, OLD.channel_id) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'wallet_ledgeraccount : seule la date de relance change (%)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER wallet_ledgeraccount_guard
BEFORE UPDATE OR DELETE ON wallet_ledgeraccount
FOR EACH ROW EXECUTE FUNCTION wallet_ledgeraccount_guard();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS wallet_ledgeraccount_guard ON wallet_ledgeraccount;
DROP FUNCTION IF EXISTS wallet_ledgeraccount_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("wallet", "0010_accounting_adjustments")]

    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
