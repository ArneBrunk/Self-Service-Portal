# Allgemeine Informationen
## 1. Beschreibung
Diese Arbeit befasst sich mit der Entwicklung eines KI-basierten Self-Service-Portals zur automatisierten Verarbeitung von Kundenanfragen.  
Im Fokus steht die Modellierung, prototypische Umsetzung und Evaluation eines intelligenten Supportsystems unter Verwendung eines Retrieval-Augmented-Generation (RAG)-Ansatzes.

## 2. Technischer Stack

- Programmiersprache: Python
- Framework: Django
- Datenbank: PostgreSQL mit pgvector
- Embedding-Modell: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
- LLM: OpenAI API
- Containerisierung: Docker

## 3. Ordnerstruktur
/Programm-Code  
→ Enthält den vollständigen Quellcode des Prototyps  

/Gematik-Dokumente
→ Enthält die im Testrun verwendeten Gematik-Dokumente  

/Evaluation  
→ Rohdaten der Testfragen und Ergebnisse der Evaluationsläufe (CSV / Excel)  

/Quellen
→ Enthält die verwendeten Online-Quellen

# Installationsanleitung für Reproduzierbarkeit
## Voraussetzungen
- Python 3.12
- virtuelles Enviroment (empfohlen)
- Docker-Desktop / alternativ muss manuelle eine SQL-Datenbank mit pgvektor Extension erstellt werden

## Installation
### 1. Projekt holen und viruelle Umgebung
- cd self_service_core

- python -m venv .venv 

- Windows: .venv\Scripts\activate

### 2. Requirements installieren
- pip install -r requirements.txt

### 3. .env erstellen
- cp self_service_core/self_service_core/.env_new self_service_core/self_service_core/.env
- DJANGO_SECRET_KEY=""
- OPENAI_API_KEY=""
- DB_NAME="rag_data_docker"
- DB_USER="postgres"
- DB_PASSWORD="postgres"
- DB_HOST="localhost"
- DB_PORT="5433"

### 4. pgvector-Postgres Container starten

- docker pull ankane/pgvector:v0.5.1
- docker volume create pgvector_data
- docker run -d \
  --name pgvector-db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=rag_data_docker \
  -p 5433:5432 \
  -v pgvector_data:/var/lib/postgresql/data \
  ankane/pgvector:v0.5.1

### 5. Django-Migrationen ausführen
- python manage.py migrate
- python manage.py createsuperuser

### 6. pgvector-Extension und Embedding-Spalten
- docker exec -it pgvector-db psql -U postgres -d rag_data_docker

    CREATE EXTENSION IF NOT EXISTS vector;

    ALTER TABLE knowledge_chunk

    ADD COLUMN IF NOT EXISTS embedding vector(1536);

    CREATE INDEX IF NOT EXISTS idx_chunk_embedding
    ON knowledge_chunk
    USING ivfflat (embedding vector_l2_ops)
    WITH (lists = 100);

    ALTER TABLE knowledge_knowledgegap
    ADD COLUMN IF NOT EXISTS embedding vector(1536);


- \q

### 7. Gematik-PDF importieren
- mit dem superuser anmelden
- PDF-Dateien im Knowledge-Bereich importieren


### 8. Testfragen importieren
- python manage.py loaddata eval_items.json

### 9. Server starten
- python manage.py runserver