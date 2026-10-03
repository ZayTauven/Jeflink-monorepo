"""AuditEvent en ajout seul jusqu'en base (I10).

Toute mise à jour ou suppression est refusée par PostgreSQL. La future purge à 5 ans
(tâche purge_auth_data) positionnera, dans sa transaction : SET LOCAL jeflink.audit_purge = 'on'.
TRUNCATE (flush des tests) n'est pas concerné par un trigger de ligne.
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION trust_auditevent_append_only() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('jeflink.audit_purge', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'trust_auditevent est en ajout seul (%)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trust_auditevent_append_only
BEFORE UPDATE OR DELETE ON trust_auditevent
FOR EACH ROW EXECUTE FUNCTION trust_auditevent_append_only();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS trust_auditevent_append_only ON trust_auditevent;
DROP FUNCTION IF EXISTS trust_auditevent_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("trust", "0003_actor_public_id")]

    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
