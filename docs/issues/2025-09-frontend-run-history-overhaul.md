# Frontend Run History Overhaul

**Status:** Proposed
**Date:** 2025-09-25
**Author:** Gemini

## 1. Overview

The current "Run History" feature in the main Run Console is limited to a simple dropdown showing the most recent runs. This makes it difficult to find, analyze, and compare historical runs.

This document outlines a plan to overhaul this feature, replacing the dropdown with a more robust, paginated, and filterable interface.

## 2. Functional Requirements

- **Date Range Filtering:** Users should be able to filter the run history by a start and end date.
- **Network Name Filtering:** Users should be able to filter runs that were executed on a specific network.
- **Pagination:** The results should be displayed in a paginated list (e.g., 20 runs per page) with controls to navigate between pages.
- **Clear UI:** The simple dropdown will be replaced with a dedicated area that includes filter controls and a clear, table-like list of the resulting runs.

## 3. Implementation Plan

### Phase 1: Backend API Enhancement

The backend API must be updated to support the new filtering and pagination requirements.

- **File to Modify:** `src/arion_agents/api.py`
- **Endpoint to Modify:** `GET /runs` (the `list_runs` function)
- **Plan:**
    1.  **Modify Function Signature:** Update the `list_runs` function to accept the following new optional query parameters:
        - `start_date: str | None = None`
        - `end_date: str | None = None`
        - `network_name: str | None = None`
        - `page: int = 1`
        - `page_size: int = 20`
    2.  **Enhance SQLAlchemy Query:** The SQLAlchemy query within `list_runs` will be modified to:
        - Add `WHERE` clauses to filter by `created_at` if `start_date` and/or `end_date` are provided.
        - Add a `JOIN` to the `cfg_networks` table and a `WHERE` clause to filter by `Network.name` if `network_name` is provided.
        - Use `.offset()` and `.limit()` to implement pagination based on the `page` and `page_size` parameters.
    3.  **Update Response:** The endpoint's response will be changed from a simple list to an object that includes pagination details:
        ```json
        {
          "total_items": 123,
          "total_pages": 7,
          "current_page": 1,
          "items": [ ...run records... ]
        }
        ```

### Phase 2: Frontend Data Fetching

The frontend client that calls the API needs to be updated to pass the new parameters.

- **File to Modify:** `frontend/lib/api/runs.ts` (or a similar file where `fetchRecentRuns` is defined).
- **Plan:**
    1.  **Modify `fetchRecentRuns`:** Update the function to accept an object with the new filter and pagination parameters (`startDate`, `endDate`, `networkName`, `page`, `pageSize`).
    2.  **Construct Query String:** The function will construct the appropriate query string to append to the `/runs` API call.
    3.  **Update Return Type:** The function's return type will be updated to match the new paginated response object from the API.

### Phase 3: Frontend UI Component

The `RunConsole` component will be significantly refactored.

- **File to Modify:** `frontend/components/RunControls/RunConsole.tsx`
- **Plan:**
    1.  **State Management:** Add new React state variables to manage the filter values (start date, end date, selected network) and the current page number.
    2.  **UI Controls:**
        - Replace the existing `<select>` dropdown for run history.
        - Add date input fields (e.g., using `react-datepicker` or native date inputs) for the date range filter.
        - Add a `<select>` dropdown populated with the list of available networks for the network filter.
        - Add "Previous" and "Next" buttons for pagination.
    3.  **Data Fetching Logic:**
        - The `useQuery` hook that calls `fetchRecentRuns` will be updated.
        - Its `queryKey` will now include the filter and page state variables, so that the data is automatically refetched whenever a filter changes.
    4.  **Display Results:**
        - A new component will be created to render the list of runs in a clear, table-like format, displaying the run ID, creation date, and network name.
        - A summary (e.g., "Showing 21-40 of 123 runs") will be displayed.
