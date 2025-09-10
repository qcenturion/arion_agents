# Workstream: DevOps & GitHub

## Goals
- Initialize repo, connect to GitHub, branch protections
- CI: lint/test; CD optional (container build)
- Local dev via Docker Compose

## Decisions
- CI: GitHub Actions
- Container: Python base image, multi-stage build later

## Milestones & Tasks
- M1: Repo + CI
  - [ ] `git init`, first commit, GitHub remote
  - [ ] GitHub Actions: Python 3.12, `pip install -r requirements.txt`, `pytest`
  - [ ] Pre-commit hooks (ruff/black optional)
- M2: Containerization
  - [ ] Dockerfile for API service
  - [ ] Compose with OTel stack
  - [ ] Versioned tags on main branch
- M3: Release hygiene
  - [ ] Semver tagging and changelog
  - [ ] CODEOWNERS, templates, branch protections
