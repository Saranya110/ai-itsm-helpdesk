# Helio AI IT Service Desk

A local, end-to-end prototype for the Sorim Technologies AI-ITSM assessment. It demonstrates employee self-service, grounded knowledge search, ticket classification, a safe mock self-heal, software provisioning, an audit trail, and an operations dashboard.

## Run locally

Requirements: Node.js 18+ and Python 3.10+.

1. From the repository root, run `py -3 -m venv .venv`, then `\.venv\Scripts\Activate.ps1` in PowerShell (or `source .venv/bin/activate` on macOS/Linux).
2. Install the API dependencies with `python -m pip install -r backend/requirements.txt`. Optional semantic vector retrieval can be added with `python -m pip install -r backend/requirements-ai.txt`; it downloads large model packages on first setup.
3. Copy `backend/.env.example` to `backend/.env` and configure integrations if available.
4. Start the API from the repository root with `python -m uvicorn backend.app.main:app --reload --port 8000`.
5. In another terminal, run `npm install` and `npm run dev` from the repository root. Open the local Vite URL shown in the terminal.

The app is usable without external credentials. It stores demo activity in `backend/data/` and uses a mock ServiceNow workflow. Chroma with the open `all-MiniLM-L6-v2` embedding model is used when its dependencies and model are available; otherwise a lightweight local lexical retriever keeps the demo available. MongoDB Atlas can be enabled by setting `MONGODB_URI` and `MONGODB_DATABASE`.

## Deploy publicly on Render

The included `render.yaml` Blueprint creates a static React site and a FastAPI web service. In Render, create a new Blueprint from this GitHub repository and deploy both services. The frontend gets the API's public hostname from the Blueprint and points its requests to that service automatically. Both services use Render's free plans for a no-cost prototype deployment. The free API may spin down after 15 minutes without traffic and can take about a minute to wake; local JSON data is ephemeral on free services. Set MongoDB Atlas credentials in the Render API service environment to retain app data across restarts. Do not put database credentials in this repository.

## 5-minute demo path

1. **VPN incident:** choose “My VPN is not connecting.” See the classification, P2 priority, Network Support assignment, VPN article attribution, and create an incident.
2. **Password self-heal:** choose “My password has expired.” Run the mock reset, show the validation result, resolved incident, and audit entry on the dashboard.
3. **Grounded answer:** ask “How do I troubleshoot Outlook synchronization?” Show the Outlook knowledge article citation.
4. **Software request:** choose “I need Visual Studio Code installed on my laptop.” Create the catalogue request and show its provisioning status.
5. **Unknown question:** choose the quantum flux capacitor prompt. Show that no approved source can answer it and create a human-reviewed helpdesk ticket.

## Architecture

React/Vite employee portal → FastAPI workflow API → classification and routing → approved knowledge retrieval → answer with cited source or escalation. The backend also provides incident, mock password-reset, software-provisioning, dashboard, and knowledge APIs. Chroma persists vector records under `backend/data/chroma`; MongoDB Atlas stores tickets, requests, and audit events when configured. Mock records use JSON Lines under `backend/data/`.

The current classification and action policy are deterministic for a reliable, explainable hackathon demo. `HF_MODEL` is reserved in configuration to document a free/open model choice; this prototype does not yet invoke a generative LLM. This prevents ungrounded generated advice. Retrieval returns approved article text only, and a low-confidence or no-source answer explicitly offers escalation. The self-heal endpoint supports only password reset/account unlock and records a mock identity check, action, and validation. The provisioning flow queues a mock request and does not install software.

## Integrations and security

- **MongoDB Atlas:** optional `MONGODB_URI` and `MONGODB_DATABASE`. If not configured or unavailable, local JSON Lines storage is used.
- **ServiceNow:** the assessment permits a mock API where a developer instance is unavailable. No live instance credentials were included, so incident and service request references are generated locally. Set `SERVICENOW_INSTANCE_URL`, `SERVICENOW_USERNAME`, and `SERVICENOW_PASSWORD` only after implementing/validating the live adapter for your developer instance.
- **Models:** the documented choices are Hugging Face `google/flan-t5-small` for a future generation layer and `sentence-transformers/all-MiniLM-L6-v2` for embeddings. Model downloads may require network access on first use.
- Never commit real secrets. The example environment file contains no credentials.

## API overview

- `GET /api/health`, `GET /api/dashboard`, `GET /api/knowledge`
- `POST /api/ask` with `{"message":"..."}`
- `POST /api/tickets` with `{"message":"..."}`
- `POST /api/automate` with `{"message":"My password has expired"}`
- `POST /api/requests` with `{"message":"I need Visual Studio Code installed"}`

Interactive API documentation is available at `http://localhost:8000/docs` while the backend is running.

## Known limitations

This is an assessment prototype, not a production service. It uses deterministic intent rules and mock ServiceNow/provisioning actions. The LLM configuration is illustrative and no model inference is wired into the response path yet. The retriever uses persistent Chroma with Sentence Transformers when available and a lexical fallback otherwise. Demo data is local unless MongoDB Atlas is configured. Add authentication, authorization, data retention, approval gates, real identity verification, scoped ServiceNow REST calls, monitoring, and broader test coverage before production use.
