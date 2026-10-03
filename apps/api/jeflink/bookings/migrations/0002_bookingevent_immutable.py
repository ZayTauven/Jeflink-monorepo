"""BookingEvent immuable jusqu'en base (spec 003).

PostgreSQL refuse toute suppression et toute mise à jour, sauf l'effacement de la note libre
(``note`` vide, tout le reste identique) : c'est ce que fait l'anonymiseur à la suppression d'un
compte. TRUNCATE (flush des tests) n'est pas concerné par un trigger de ligne.
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION bookings_bookingevent_immutable() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.note = '' AND
       ROW(NEW.id, NEW.booking_id, NEW.from_status, NEW.to_status, NEW.actor_id, NEW.actor_kind,
           NEW.reason, NEW.metadata, NEW.created_at)
       IS NOT DISTINCT FROM
       ROW(OLD.id, OLD.booking_id, OLD.from_status, OLD.to_status, OLD.actor_id, OLD.actor_kind,
           OLD.reason, OLD.metadata, OLD.created_at) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'bookings_bookingevent est immuable (%)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER bookings_bookingevent_immutable
BEFORE UPDATE OR DELETE ON bookings_bookingevent
FOR EACH ROW EXECUTE FUNCTION bookings_bookingevent_immutable();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS bookings_bookingevent_immutable ON bookings_bookingevent;
DROP FUNCTION IF EXISTS bookings_bookingevent_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("bookings", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
