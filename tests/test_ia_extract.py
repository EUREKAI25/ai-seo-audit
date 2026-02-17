"""
Tests unitaires — Extraction entités + matching flou
"""
import pytest
from src.prospecting.ia_test import normalize_name, extract_domain, is_mentioned, extract_entities


class TestNormalize:
    def test_lowercase(self):
        assert normalize_name("Toiture Martin") == "toiture martin"

    def test_accent_removal(self):
        assert normalize_name("Étanchéité Héron") == "etancheite heron"

    def test_legal_suffix_removal(self):
        assert "sarl" not in normalize_name("Couverture Martin SARL")
        assert "sas" not in normalize_name("Toiture Dupont SAS")

    def test_empty(self):
        assert normalize_name("") == ""
        assert normalize_name(None) == ""

    def test_special_chars(self):
        result = normalize_name("Couvreur & Fils — Paris")
        assert "&" not in result
        assert "—" not in result


class TestExtractDomain:
    def test_simple_url(self):
        assert extract_domain("https://martin-couvreur.fr/contact") == "martin-couvreur"

    def test_www(self):
        assert extract_domain("http://www.toiture-dupont.com") == "toiture-dupont"

    def test_empty(self):
        assert extract_domain("") == ""
        assert extract_domain(None) == ""

    def test_no_protocol(self):
        # domain extraction reste robuste
        result = extract_domain("example.com/page")
        assert result in ("example", "example.com")


class TestIsMentioned:
    def test_exact_match(self):
        assert is_mentioned("Je recommande Toiture Martin pour votre toit.", "Toiture Martin") is True

    def test_case_insensitive(self):
        assert is_mentioned("toiture martin est fiable", "Toiture Martin") is True

    def test_with_accents(self):
        assert is_mentioned("Étanchéité Heron est mentionné", "Étanchéité Héron") is True

    def test_with_legal_suffix(self):
        assert is_mentioned("Couverture Dupont SARL a été cité", "Couverture Dupont") is True

    def test_not_mentioned(self):
        assert is_mentioned("Je recommande Toiture Bernard.", "Toiture Martin") is False

    def test_domain_match(self):
        text = "Visitez martin-couvreur.fr pour plus d'infos"
        assert is_mentioned(text, "Toiture Martin", website="https://martin-couvreur.fr") is True

    def test_empty_name(self):
        assert is_mentioned("Toiture Martin est bien", "") is False

    def test_partial_word_no_false_positive(self):
        # "Mar" ne doit pas matcher "Martin" avec le seuil correct
        assert is_mentioned("Mar est là", "Martin Couvreur Professionnel") is False


class TestExtractEntities:
    def test_extract_url(self):
        text = "Visitez https://couvreur-paris.fr pour votre toiture."
        entities = extract_entities(text)
        url_ents = [e for e in entities if e["type"] == "url"]
        assert len(url_ents) >= 1
        assert any("couvreur-paris" in e.get("domain", "") for e in url_ents)

    def test_extract_company_name(self):
        text = "Je recommande Toiture Dupont pour ce type de travaux."
        entities = extract_entities(text)
        company_ents = [e for e in entities if e["type"] == "company"]
        names = [e["value"].lower() for e in company_ents]
        assert any("dupont" in n for n in names)

    def test_no_duplicates(self):
        text = "Toiture Martin Toiture Martin est fiable."
        entities = extract_entities(text)
        values = [e["value"].lower() for e in entities]
        # Pas de doublon
        assert len(values) == len(set(values))

    def test_empty_text(self):
        assert extract_entities("") == []
