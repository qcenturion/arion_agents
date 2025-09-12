# Epic: Deployment to GCP (Cloud Run / Cloud Functions)

## Summary
Build a portable container image and deploy the API to Google Cloud Run (primary target). Optionally support Cloud Functions 2nd gen using the same image. Configure secure access to Cloud SQL and secrets.

## Plan
- Containerize FastAPI app with Uvicorn worker
- Environment-driven config (12-factor)
- Cloud SQL (Postgres) via SQLAlchemy `DATABASE_URL` and Cloud SQL Auth Proxy
- OpenTelemetry export via Collector URL
- CI/CD from GitHub Actions to GCP

## Tasks
- GCP project setup (IAM, Artifact Registry, Cloud Run, Secret Manager)
- Dockerfile and build/push to Artifact Registry
- Cloud Run service (min instances=0/1, concurrency, CPU/memory)
- Cloud SQL instance provisioning, database and user
- VPC/connector and Cloud SQL Auth Proxy integration
- Secrets: API keys and DB creds in Secret Manager
- CI/CD: OIDC or service account key for deploy

## Acceptance
- Deployment succeeds from CI
- Service responds to `/health`
- `/invoke` runs with Postgres-backed config store
