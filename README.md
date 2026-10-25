# ChatEIH — Assistant RAG de l'École d'Ingénieurs Hélianthe

Application web qui répond aux questions des étudiants à partir des 7 documents officiels de l'EIH,
en citant ses sources, et qui refuse (« Je ne trouve pas cette information dans les documents de
l'École. ») quand la réponse n'est pas dans le corpus.

## Architecture

```
Ingestion (une fois) : PDF → extraction → découpage → embeddings → Chroma (disque)
Question             : React → API FastAPI → recherche top-k → prompt → Groq → réponse citée → React
```

## Arborescence

```
backend/   API FastAPI (Python 3.11+)
  app/     code de l'application (config, extraction, découpage, index, génération, API)
frontend/  interface React + TypeScript (Vite)
data/
  corpus/  les 7 PDF fournis (non modifiés)
  chroma/  base vectorielle persistée (générée, ignorée par Git)
eval/      questions.jsonl + run_eval.py
tests/     tests pytest
```

## Choix techniques

| Brique        | Choix                                   | Pourquoi |
|---------------|-----------------------------------------|----------|
| LLM           | Groq (`llama-3.3-70b-versatile`)        | API gratuite, rapide, bon en français |
| Embeddings    | `intfloat/multilingual-e5-small` (local) | Multilingue, 512 tokens, léger ; Groq ne fournit pas d'embeddings |
| Base vectorielle | Chroma (persistance disque)          | Simple, filtres par métadonnées intégrés |
| Extraction PDF | pdfplumber                             | Garde la structure des tableaux |
| Backend       | FastAPI + Pydantic                      | Imposé ; documentation `/docs` automatique |
| Frontend      | React + TypeScript (Vite)               | Imposé |

## Installation

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (PowerShell)
pip install -r backend/requirements.txt
copy .env.example .env          # puis renseigner GROQ_API_KEY
```

### Frontend

_(à compléter en séance 4)_

## Variables d'environnement

Voir [.env.example](.env.example). La clé Groq reste dans `.env` (jamais committé) et n'est
jamais envoyée au navigateur.

## Lancement

_(à compléter au fil des séances)_

## Équipe

- Hamid — _rôle_
- _binôme_ — _rôle_
