"""
Tests unitaires — Scoring & eligibility
"""
import pytest
from unittest.mock import MagicMock
import json


# ── Helpers pour créer des faux runs ──

def make_run(model: str, mention_per_query: list, mentioned_target: bool = None, competitors: list = None):
    run = MagicMock()
    run.model = model
    run.mention_per_query = json.dumps(mention_per_query)
    run.mentioned_target  = mentioned_target if mentioned_target is not None else any(mention_per_query)
    run.competitors_entities = json.dumps(competitors or [])
    return run


def make_prospect(name="Test SARL", website=None, reviews_count=None, google_ads_active=None):
    p = MagicMock()
    p.name = name
    p.website = website
    p.reviews_count = reviews_count
    p.google_ads_active = google_ads_active
    p.competitors_cited = "[]"
    return p


# ── Tests compute_email_ok ──

class TestEmailOK:
    def test_eligible_invisible_on_all_models(self):
        """Prospect invisible sur 3 modèles × 5 requêtes → EMAIL_OK."""
        from src.prospecting.scoring import compute_email_ok
        # 3 modèles, chacun 3 runs (9 total), prospect jamais mentionné
        runs = []
        for model in ["openai", "anthropic", "gemini"]:
            for _ in range(3):
                runs.append(make_run(model, [False, False, False, False, False], False, ["Toiture Martin"]))
        eligible, justif = compute_email_ok(runs)
        assert eligible is True
        assert "3/3" in justif or "3" in justif

    def test_not_eligible_mentioned_on_all_models(self):
        """Prospect toujours mentionné → pas EMAIL_OK."""
        from src.prospecting.scoring import compute_email_ok
        runs = []
        for model in ["openai", "anthropic", "gemini"]:
            for _ in range(3):
                runs.append(make_run(model, [True, True, True, True, True], True))
        eligible, _ = compute_email_ok(runs)
        assert eligible is False

    def test_not_eligible_only_1_model_invisible(self):
        """Invisible sur 1/3 modèles seulement → pas EMAIL_OK (besoin 2/3)."""
        from src.prospecting.scoring import compute_email_ok
        runs = []
        # openai : toujours mentionné
        for _ in range(3):
            runs.append(make_run("openai", [True, True, True, True, True], True))
        # anthropic : mentionné sur Q1
        for _ in range(3):
            runs.append(make_run("anthropic", [True, False, False, False, False], True))
        # gemini : jamais mentionné
        for _ in range(3):
            runs.append(make_run("gemini", [False, False, False, False, False], False, ["Concurrent A"]))
        eligible, _ = compute_email_ok(runs)
        assert eligible is False

    def test_not_eligible_missing_competitor(self):
        """Invisible mais aucun concurrent stable → pas EMAIL_OK."""
        from src.prospecting.scoring import compute_email_ok
        runs = []
        for model in ["openai", "anthropic", "gemini"]:
            for _ in range(3):
                runs.append(make_run(model, [False, False, False, False, False], False, []))  # pas de concurrent
        eligible, _ = compute_email_ok(runs)
        assert eligible is False

    def test_not_eligible_query_threshold(self):
        """Mentionné sur 2/5 requêtes → moins de 4 requêtes invisibles → pas EMAIL_OK."""
        from src.prospecting.scoring import compute_email_ok
        runs = []
        for model in ["openai", "anthropic", "gemini"]:
            for _ in range(3):
                # mentionné sur Q1 et Q2 → seulement 3 requêtes invisibles
                runs.append(make_run(model, [True, True, False, False, False], True, ["Concurrent A"]))
        eligible, _ = compute_email_ok(runs)
        assert eligible is False

    def test_empty_runs_not_eligible(self):
        from src.prospecting.scoring import compute_email_ok
        eligible, justif = compute_email_ok([])
        assert eligible is False
        assert "Aucun run" in justif


# ── Tests compute_score ──

class TestScore:
    def test_max_score(self):
        """Score max : EMAIL_OK + concurrents + ads + reviews + website."""
        from src.prospecting.scoring import compute_score
        runs = []
        for model in ["openai", "anthropic", "gemini"]:
            for _ in range(3):
                runs.append(make_run(model, [False]*5, False, ["concurrent a", "concurrent b"]))
        prospect = make_prospect(website="https://test.fr", reviews_count=25, google_ads_active=True)
        score, justif, comps = compute_score(prospect, runs, email_ok=True)
        assert score == 9.0   # 4+2+1+1+1
        assert "EMAIL_OK" in justif or "OUI" in justif

    def test_min_score_no_email_ok(self):
        """Score 0 si pas EMAIL_OK et aucun autre critère."""
        from src.prospecting.scoring import compute_score
        runs = [make_run("openai", [True]*5, True)]
        prospect = make_prospect()
        score, justif, comps = compute_score(prospect, runs, email_ok=False)
        assert score == 0.0

    def test_partial_score(self):
        """Score partiel : EMAIL_OK + website uniquement."""
        from src.prospecting.scoring import compute_score
        runs = []
        for model in ["openai", "anthropic", "gemini"]:
            runs.append(make_run(model, [False]*5, False, ["concurrent a"]))
        prospect = make_prospect(website="https://example.fr")
        score, justif, comps = compute_score(prospect, runs, email_ok=True)
        assert score == 7.0   # 4+2+0+0+1


# ── Tests transitions statuts ──

class TestStatusTransitions:
    def test_valid_transitions(self):
        from src.prospecting.models import can_transition
        assert can_transition("SCANNED", "SCHEDULED") is True
        assert can_transition("SCHEDULED", "TESTING") is True
        assert can_transition("TESTING", "TESTED") is True
        assert can_transition("TESTED", "SCORED") is True
        assert can_transition("SCORED", "READY_ASSETS") is True
        assert can_transition("READY_ASSETS", "READY_TO_SEND") is True
        assert can_transition("READY_TO_SEND", "SENT_MANUAL") is True

    def test_invalid_transitions(self):
        from src.prospecting.models import can_transition
        assert can_transition("SCANNED", "TESTED") is False
        assert can_transition("READY_TO_SEND", "SCANNED") is False
        assert can_transition("SCORED", "SCANNED") is False
        assert can_transition("SENT_MANUAL", "READY_TO_SEND") is False

    def test_invalid_status_string(self):
        from src.prospecting.models import can_transition
        assert can_transition("INVALID", "SCANNED") is False
        assert can_transition("SCANNED", "INVALID") is False
