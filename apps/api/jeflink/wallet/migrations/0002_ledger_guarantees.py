"""Grand livre garanti jusqu'en base (spec 005, ADR 0012).

- Immuabilité : PostgreSQL refuse toute mise à jour et toute suppression d'une transaction ou
  d'une ligne. Une erreur se corrige par une contre-passation. TRUNCATE (flush des tests) n'est
  pas concerné par un trigger de ligne ; une réécriture à l'identique (rechargement des données
  par ``serialized_rollback``) est permise, puisqu'elle ne change rien.
- Équilibre : un trigger de contrainte différé vérifie au commit que chaque transaction écrite
  compte au moins deux lignes et que ses débits égalent ses crédits, même si l'écriture vient
  d'un script ou de SQL brut. ``post_transaction`` force la vérification avant de rendre la main
  (``SET CONSTRAINTS … IMMEDIATE``).
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION wallet_ledger_immutable() RETURNS trigger AS $$
BEGIN
    -- Une réécriture à l'identique ne change rien (rechargement des données de test).
    IF TG_OP = 'UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION '% est immuable (%)', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER wallet_ledgertransaction_immutable
BEFORE UPDATE OR DELETE ON wallet_ledgertransaction
FOR EACH ROW EXECUTE FUNCTION wallet_ledger_immutable();

CREATE TRIGGER wallet_ledgerentry_immutable
BEFORE UPDATE OR DELETE ON wallet_ledgerentry
FOR EACH ROW EXECUTE FUNCTION wallet_ledger_immutable();

CREATE OR REPLACE FUNCTION wallet_ledger_check_balanced() RETURNS trigger AS $$
DECLARE
    txn_id bigint;
    line_count integer;
    net numeric;
BEGIN
    IF TG_TABLE_NAME = 'wallet_ledgerentry' THEN
        txn_id := NEW.transaction_id;
    ELSE
        txn_id := NEW.id;
    END IF;
    SELECT count(*),
           coalesce(sum(CASE WHEN side = 'debit' THEN amount_xof ELSE -amount_xof END), 0)
      INTO line_count, net
      FROM wallet_ledgerentry
     WHERE transaction_id = txn_id;
    IF line_count < 2 OR net <> 0 THEN
        RAISE EXCEPTION 'transaction % du grand livre invalide (% lignes, écart %)',
            txn_id, line_count, net;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER wallet_ledgerentry_balanced
AFTER INSERT ON wallet_ledgerentry
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION wallet_ledger_check_balanced();

CREATE CONSTRAINT TRIGGER wallet_ledgertransaction_balanced
AFTER INSERT ON wallet_ledgertransaction
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION wallet_ledger_check_balanced();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS wallet_ledgertransaction_balanced ON wallet_ledgertransaction;
DROP TRIGGER IF EXISTS wallet_ledgerentry_balanced ON wallet_ledgerentry;
DROP FUNCTION IF EXISTS wallet_ledger_check_balanced();
DROP TRIGGER IF EXISTS wallet_ledgerentry_immutable ON wallet_ledgerentry;
DROP TRIGGER IF EXISTS wallet_ledgertransaction_immutable ON wallet_ledgertransaction;
DROP FUNCTION IF EXISTS wallet_ledger_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("wallet", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
