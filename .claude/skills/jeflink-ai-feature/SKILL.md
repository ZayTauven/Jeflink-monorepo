---
name: jeflink-ai-feature
description: Méthode pour ajouter ou modifier une capacité IA de Jeflink (structuration de demande vocale, fourchette de prix, brouillon de devis, résumé de litige, matching, modération). Utiliser dès qu'une tâche implique un LLM, un prompt, de la transcription vocale, une classification ou un score, même pour ajuster un prompt existant.
---

# Capacité IA Jeflink

Tout vit dans `apps/api/jeflink/ai/`. Principe : **l'IA propose, l'humain valide, un repli existe toujours.**

## Étapes

1. **Définir la capacité** dans la spec : entrée, sortie, qui valide, repli sans IA, coût acceptable par appel.
2. **Schéma de sortie** (`ai/schemas.py`) :

```python
class StructuredRequest(BaseModel):
    trade_slug: str  # validé contre catalog au runtime, voir ci-dessous
    summary_fr: str = Field(max_length=280)
    urgency: Literal["immediate", "today", "this_week", "flexible"]
    missing_questions: list[str] = Field(max_length=3)
    confidence: float = Field(ge=0, le=1)
```

Les métiers sont des données (`catalog`), jamais une liste en dur : le service injecte dans le prompt les slugs **actifs** au moment de l'appel, puis rejette tout `trade_slug` inconnu (→ `"autre"` + repli humain). Ajouter un métier ne doit demander aucune modification de prompt ni de schéma. On ajoute seulement quelques cas d'éval pour ce métier.

3. **Prompt versionné** : `ai/prompts/structure_request/v1.md`. Contexte Sénégal explicite (quartiers, mélange français/wolof, vocabulaire local des pannes). Exemples dans le prompt. Sortie JSON uniquement.
4. **Service** (`ai/services.py`) : minimise les données (ni numéro, ni nom complet), appelle le provider, valide le schéma, écrit un `AIRun`, applique le seuil :

```python
def structure_request(*, text: str, transcript: str | None) -> StructuredRequest | None:
    run = AIRun.start(capability="structure_request", prompt_version="v1")
    trades = active_trade_slugs()  # catalog.selectors — lu en base à chaque appel
    try:
        out = provider.complete_json(prompt=load_prompt("structure_request", "v1"),
                                     input={"text": text, "transcript": transcript, "trades": trades},
                                     schema=StructuredRequest)
    except (ProviderError, ValidationError) as exc:
        run.fail(exc)
        return None  # repli : formulaire classique
    if out.trade_slug not in trades:
        out = out.model_copy(update={"trade_slug": "autre", "confidence": 0.0})
    run.succeed(out)
    return out if out.confidence >= settings.AI_MIN_CONFIDENCE["structure_request"] else None
```

5. **Évaluations** : `ai/evals/structure_request/cases.jsonl` (≥ 20 cas : fautes, wolof transcrit, mélange de langues, demandes vagues, hors sujet). Script de score comparant à la sortie attendue. Toute nouvelle version de prompt doit faire au moins aussi bien.
6. **Feature flag** par capacité, activable par zone.
7. **UI** : afficher la proposition comme éditable, jamais comme décidée.

## Voix

Transcription via `ai/speech/` (adaptateur interchangeable). Si la confiance de transcription est faible, transmettre l'audio original au pro avec un résumé partiel, sans prétendre avoir compris.

## Interdits

- Décision automatique sur l'argent, une sanction, un litige ou un KYC.
- Données personnelles superflues dans le prompt.
- Modèle en dur : `settings.AI_MODEL_DEFAULT` / `AI_MODEL_FAST`.
