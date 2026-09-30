from rest_framework.pagination import CursorPagination


class CreatedCursorPagination(CursorPagination):
    """Pagination par curseur (listes mobiles, réseau instable) sur BaseModel.created_at."""

    ordering = "-created_at"
