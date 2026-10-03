from jeflink.common.gsm7 import is_gsm7, segments


def test_texte_francais_courant_en_gsm7():
    texte = "Votre code Jeflink : 123456. Ne le donnez à personne. Valable 10 minutes."
    assert is_gsm7(texte)
    assert segments(texte) == 1


def test_caracteres_qui_basculent_en_ucs2():
    for texte in ("Jëf", "ŋ", "ç minuscule", "espace" + chr(0xA0) + "insécable", "fête"):
        assert not is_gsm7(texte), texte


def test_decompte_des_segments():
    assert segments("a" * 160) == 1
    assert segments("a" * 161) == 2
    assert segments("€" * 80) == 1  # caractère étendu : 2 septets
    assert segments("ë" * 70) == 1
    assert segments("ë" * 71) == 2
