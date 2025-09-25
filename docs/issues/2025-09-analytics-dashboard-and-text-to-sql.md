# Analytics Dashboard & Text-to-SQL Feature

**Status:** Proposed
**Date:** 2025-09-25
**Author:** Gemini

## 1. Overview

This document outlines the plan to implement a new Analytics feature within the application. The goal is to provide business intelligence (BI) and data visualization capabilities on top of the existing run and experiment history data.

The feature will consist of a new "Analytics" tab in the frontend, which will provide both pre-defined dashboards for at-a-glance insights and an ad-hoc, natural language querying interface using a Text-to-SQL agent.

## 2. Guiding Principles & Technology Choices

- **Integrated Architecture:** The solution should slot into the existing technical stack with minimal new dependencies.
- **Lightweight:** Avoid heavy, external BI frameworks.
- **Performance:** Utilize pre-aggregated data for standard dashboards to ensure fast load times.

### Technology Stack:
- **Frontend Framework:** Continue using the existing **Next.js** application.
- **Visualization Library:** **Tremor** (`@tremor/react`). It is a lightweight, modern React library for building dashboards that integrates seamlessly with Next.js.
- **Backend Framework:** Continue using **FastAPI**.
- **Database:** Continue using **PostgreSQL**.
- **Text-to-SQL Engine:** Leverage the internal **Arion Agent** framework.

## 3. Implementation Plan

### Phase 1: Database & Backend

#### 1.1. Analytics Schema & Aggregation

A dedicated analytics schema will be created to house pre-aggregated data, separating it from the raw transactional data.

- **Alembic Migration:** A new migration will be created to:
    - `CREATE SCHEMA analytics;`
    - `CREATE TABLE analytics.daily_run_summary (...)`
- **Table Schema (`analytics.daily_run_summary`):**
    - `date`: DATE (Primary Key)
    - `total_runs`: INTEGER
    - `successful_runs`: INTEGER
    - `failed_runs`: INTEGER
    - `total_tokens`: INTEGER
    - `avg_duration_ms`: FLOAT
- **Aggregation Script:**
    - A new script, `tools/run_analytics_aggregation.py`, will be created.
    - This script will contain the logic to read from `public.run_history`, perform daily aggregations, and `INSERT`/`UPDATE` the `analytics.daily_run_summary` table.

#### 1.2. API Endpoints

New endpoints will be created in a dedicated `src/arion_agents/api_analytics.py` module.

- **`GET /analytics/daily-summary`**:
    - **Purpose:** Serves the pre-aggregated data for the standard frontend dashboards.
    - **Action:** Performs a simple `SELECT * FROM analytics.daily_run_summary ORDER BY date;`.
- **`POST /analytics/text-to-sql`**:
    - **Purpose:** Handles ad-hoc natural language queries.
    - **Request Body:** `{ "question": "natural language question" }`
    - **Response Body:** `{ "sql": "...", "columns": [...], "rows": [...] }`

#### 1.3. Text-to-SQL Agent

The Text-to-SQL capability will be implemented as a specialized Arion Agent.

- **Network Configuration:** A new `text_to_sql` agent network will be defined.
- **Agent Prompt:** The agent's prompt will be carefully engineered to include:
    - The schema definitions for both the raw tables (`public.run_history`, `public.experiment_history`) and the new aggregate table (`analytics.daily_run_summary`).
    - Clear instructions to only generate read-only `SELECT` statements.
    - Safety constraints forbidding any data-mutating keywords.
- **Backend Logic & Security:**
    - The `/analytics/text-to-sql` endpoint will invoke this agent.
    - **Security:** Before execution, the backend will strictly validate the LLM-generated SQL to ensure it is a `SELECT` query and does not contain forbidden keywords (`UPDATE`, `DELETE`, etc.). This is a critical safety measure.

### Phase 2: Frontend

#### 2.1. Setup

- **Dependency:** The Tremor library will be added to `frontend/package.json`: `npm install @tremor/react @tremor/core`.
- **Navigation:** The main navigation in `LayoutShell.tsx` will be updated to include a link to the new "Analytics" tab.
- **Page:** A new page will be created at `frontend/app/analytics/page.tsx`.

#### 2.2. UI Components

The analytics page will be divided into two main sections:

- **Standard Dashboards:**
    - This section will fetch data from the `/analytics/daily-summary` endpoint.
    - It will use Tremor components (`Card`, `BarChart`, `LineChart`) to display key metrics like:
        - Runs Over Time
        - Success vs. Failure Rate
        - Token Consumption Trends
- **Ad-hoc Analytics ("Ask a Question"):**
    - This section will provide a text input for users to ask questions in natural language.
    - It will call the `/analytics/text-to-sql` endpoint.
    - The results (both the generated SQL and the data) will be displayed in a clean, formatted table.
