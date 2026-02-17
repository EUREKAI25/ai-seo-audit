# 🤖 AI SEO Audit — v2

> **Pipeline B2B de prospection IA-visibilité + Outil d'audit client**

Deux modules en un :
1. **B2B Pipeline** — Prospection automatisée : identifier les entreprises locales invisibles dans les réponses IA → générer audits + landing pages personnalisées + email drafts → file READY_TO_SEND manuelle
2. **B2C Audit** — Outil client-facing : formulaire d'audit, score de visibilité, recommandations

---

## 🏗️ Architecture B2B Pipeline

```
city + profession + max_prospects
        │
        ▼
POST /api/prospect-scan          → ProspectRecord[] (SCANNED → SCHEDULED)
        │
        ▼ (scheduler: Mer/Ven/Dim 09:00/13:00/20:30 Rome)
POST /api/ia-test/run            → TestRun × 3 modèles × 5 requêtes (TESTING → TESTED)
        │
        ▼
POST /api/scoring/run            → Score /10 + EMAIL_OK gate (TESTED → SCORED)
        │
        ▼
POST /api/prospect/{id}/assets   → video_url + screenshot_url (SCORED → READY_ASSETS)
        │
        ▼ (lundi 09:00 Rome — scheduler)
POST /api/prospect/{id}/mark-ready → Gate stricte → READY_TO_SEND
        │
        ▼
POST /api/generate/campaign      → audit.html + email.json + video_script.txt + CSV SendQueue
        │
        ▼ [MANUEL] Nathalie envoie depuis SendQueue
```

### Statuts imposés
`SCANNED → SCHEDULED → TESTING → TESTED → SCORED → READY_ASSETS → READY_TO_SEND → SENT_MANUAL`

### Règle EMAIL_OK
- Prospect JAMAIS cité sur **au moins 2/3 modèles** (OpenAI/Anthropic/Gemini)
- Prospect JAMAIS cité sur **au moins 4/5 requêtes**
- **Au moins 1 concurrent stable** cité dans ≥ 2 runs
- Gate : aucun email sans `video_url` + `screenshot_url`

---

---

## 🎯 Fonctionnalités

### MVP (Phase 1) — ✅ COMPLÉTÉ
- ✅ Audit automatisé mono-IA (ChatGPT)
- ✅ Score de visibilité (0-100)
- ✅ Analyse concurrence (top 5 mentions)
- ✅ Identification gaps (4 types)
- ✅ Recommandations personnalisées avec guides d'implémentation
- ✅ 3 plans (freemium 0€, starter 49€, pro 149€)
- ✅ Export PDF + JSON + maquettes HTML (selon plan)
- ✅ Paiement Stripe intégré
- ✅ Interface responsive complète

### Post-MVP (Phase 2)
- 🔄 Multi-IA (ChatGPT, Claude, Gemini, Perplexity)
- 🔄 Support multilingue (détection auto)
- 🔄 Templates sectoriels étendus (20+ secteurs)
- 🔄 Dashboard analytics évolution temporelle
- 🔄 API publique pour intégrations tierces

---

## 🏗️ Architecture

### Stack Technique
- **Backend** : Python 3.11+ / FastAPI / SQLAlchemy
- **Database** : PostgreSQL 15
- **Cache** : Redis 7
- **AI** : OpenAI API (ChatGPT)
- **Payment** : Stripe
- **PDF** : WeasyPrint
- **Deploy** : Docker / Railway.app / Render.com

### Architecture EURKAI Fractale

```
AuditOrchestrator (coordination)
  ├─► AuditAgent (query AI, extract mentions)
  │    └─► Validator ✓
  ├─► AnalyzeAgent (score, gaps, ranking)
  │    └─► Validator ✓
  └─► GenerateAgent (recommendations, guides)
       └─► Validator ✓
```

---

## 🚀 Quick Start

### Prérequis
- Python 3.11+
- Docker & Docker Compose
- Compte OpenAI (API key)
- Compte Stripe (clés test)

### Installation

```bash
# 1. Cloner le repo
cd AI_SEO_AUDIT

# 2. Configuration
cp .env.example .env
# Éditer .env avec vos clés API

# 3. Démarrer avec Docker
make docker-up

# 4. Initialiser la DB
make migrate

# 5. Ouvrir l'app
open http://localhost:8000
```

### Développement local (sans Docker)

```bash
# 1. Créer un environnement virtuel
python -m venv .venv
source .venv/bin/activate

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Migrer la DB
alembic upgrade head

# 4. Lancer l'app
uvicorn src.api.main:app --reload
```

---

## 🧪 Tests

```bash
# Tous les tests
make test

# Tests E2E
pytest tests/test_e2e_flow.py

# Avec coverage
pytest --cov=src --cov-report=html
```

---

## 📊 API Endpoints

### Frontend
- `GET /` - Landing page
- `GET /results/{audit_id}` - Page résultats
- `GET /success` - Confirmation paiement

### Audit
- `POST /api/audit/create` - Créer un audit
- `GET /api/audit/{audit_id}/status` - Polling status
- `GET /api/audit/{audit_id}/results` - Résultats complets

### Payment
- `POST /api/payment/create-checkout` - Session Stripe
- `POST /api/payment/webhook` - Webhook Stripe

### Export
- `GET /api/export/{audit_id}/guide.pdf` - Guide PDF
- `GET /api/export/{audit_id}/recommendations.json` - Export JSON
- `GET /api/export/{audit_id}/mockups.zip` - Maquettes HTML (pro)

---

## 💰 Plans & Pricing

| Feature | Freemium | Starter | Pro |
|---------|----------|---------|-----|
| **Prix** | 0€ | 49€ | 149€ |
| Requêtes IA | 3 | 10 | 20 |
| Score visibilité | ✅ | ✅ | ✅ |
| Recommandations | Basiques | Avancées | Prioritaires |
| Guide PDF | ❌ | ✅ | ✅ |
| Maquettes HTML | ❌ | ❌ | ✅ |

---

## 🚀 Déploiement

Voir **[DEPLOY.md](./DEPLOY.md)** pour les instructions complètes.

Quick deploy Railway :
```bash
railway login
railway init
railway up
```

---

## 📄 Documentation

- [DEPLOY.md](DEPLOY.md) - Guide de déploiement complet
- [_SUIVI.md](_SUIVI.md) - Suivi du projet
- [PIPELINE/01_BRIEF.md](PIPELINE/01_BRIEF.md) - Brief initial
- [PIPELINE/02_CDC.html](PIPELINE/02_CDC.html) - Cahier des Charges
- [PIPELINE/03_SPECS.html](PIPELINE/03_SPECS.html) - Spécifications techniques
- [PIPELINE/BUILD_LOG.md](PIPELINE/BUILD_LOG.md) - Journal de construction

---

**Built with ❤️ using EURKAI Architecture**
