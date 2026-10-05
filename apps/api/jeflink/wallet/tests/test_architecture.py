"""Tests d'architecture du grand livre (spec 005, ADR 0012) : un seul écrivain, aucun solde
stocké, aucun calcul d'argent hors des entiers."""

import ast
from pathlib import Path

from django.apps import apps

import jeflink

LEDGER_MODELS = ("LedgerEntry", "LedgerTransaction")
WRITES = {
    "create", "get_or_create", "update_or_create", "bulk_create", "bulk_update", "update",
    "delete", "save", "raw",
}  # fmt: skip
# Domaines où l'argent se calcule : entiers seulement.
MONEY_PACKAGES = ("wallet/", "payments/")


def _source_files():
    root = Path(jeflink.__file__).parent
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).parts
        if "tests" in parts or "migrations" in parts:
            continue
        yield path, "/".join(parts)


def ledger_writes(source: str) -> list[int]:
    """Lignes qui écrivent une transaction ou une ligne du grand livre : ``Model(…)`` ou
    ``Model.objects…<écriture>``."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Name) and func.id in LEDGER_MODELS) or (
            isinstance(func, ast.Attribute)
            and func.attr in WRITES
            and any(isinstance(n, ast.Name) and n.id in LEDGER_MODELS for n in ast.walk(func))
        ):
            lines.append(node.lineno)
    return lines


def ledger_imports(source: str) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
        and any(alias.name in LEDGER_MODELS for alias in node.names)
    ]


def real_arithmetic(source: str) -> list[int]:
    """Division réelle, ``float`` et ``Decimal`` : interdits là où l'argent se calcule."""

    def forbidden(node: ast.AST) -> bool:
        if isinstance(node, ast.BinOp | ast.AugAssign):
            return isinstance(node.op, ast.Div)
        if isinstance(node, ast.Constant):
            return type(node.value) is float
        return isinstance(node, ast.Name) and node.id in {"float", "Decimal"}

    return [node.lineno for node in ast.walk(ast.parse(source)) if forbidden(node)]


def test_les_detecteurs_voient_ce_qu_ils_doivent_voir():
    assert ledger_writes("LedgerEntry.objects.create(amount_xof=1)") == [1]
    assert ledger_writes("LedgerEntry.objects.filter(pk=1).update(side='x')") == [1]
    assert ledger_writes("LedgerTransaction(kind='x')") == [1]
    assert ledger_writes("LedgerEntry.objects.filter(pk=1).delete()") == [1]
    assert not ledger_writes("LedgerEntry.objects.filter(account=a).aggregate(t=Sum('x'))")
    assert ledger_imports("from jeflink.wallet.models import LedgerEntry") == [1]
    assert real_arithmetic("a = b / 100") == [1]
    assert real_arithmetic("a /= 2") == [1]
    assert real_arithmetic("rate = 0.1") == [1]
    assert real_arithmetic("x = float(y)") == [1]
    assert real_arithmetic("from decimal import Decimal") == []  # l'usage seul compte
    assert real_arithmetic("x = Decimal('1')") == [1]
    assert not real_arithmetic("a = b * 1000 // 10_000")


def test_aucune_ecriture_du_grand_livre_hors_de_wallet_services():
    offenders = [
        f"{name}:{line}"
        for path, name in _source_files()
        if name != "wallet/services.py"
        for line in ledger_writes(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_les_modeles_du_grand_livre_ne_sont_importes_que_dans_wallet():
    offenders = [
        f"{name}:{line}"
        for path, name in _source_files()
        if not name.startswith("wallet/")
        for line in ledger_imports(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_aucun_champ_de_solde_stocke():
    offenders = [
        f"{model._meta.label}.{field.name}"
        for model in apps.get_models()
        for field in model._meta.get_fields()
        if "balance" in field.name.lower()
    ]
    assert offenders == []


def test_aucune_division_reelle_ni_float_la_ou_l_argent_se_calcule():
    offenders = [
        f"{name}:{line}"
        for path, name in _source_files()
        if name.startswith(MONEY_PACKAGES)
        for line in real_arithmetic(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
