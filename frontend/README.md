# Frontend

This folder owns the React frontend application.

## Stack

The frontend stack is:

- Vite
- React
- TypeScript
- Tailwind CSS
- shadcn/ui (Radix primitives)
- Lucide icons
- TanStack Query
- TanStack Router
- TanStack Table
- React Hook Form
- Zod

Likely production-grade additions after the current cockpit:

- Recharts for dashboard analytics

The current cockpit workflows are:

- email/password login through `POST /api/v1/auth/login`
- browser session token storage and logout
- self-service password change through `POST /api/v1/users/me/password`
- invoice upload through `POST /api/v1/invoices/upload`
- failed processing job dashboard through `GET /api/v1/processing-jobs/failed`
- manual reprocess action through `POST /api/v1/processing-jobs/{processing_job_id}/reprocess`
- tenant-scoped audit log view through `GET /api/v1/audit-logs`
- admin user list, create, update, and password reset through `/api/v1/users`
- review queue loading from `GET /api/v1/invoices`
- invoice detail loading
- correction fields for invoice number, invoice date, total amount, and currency
- approve/reject submission through `POST /api/v1/invoices/{invoice_id}/review`
- stale-review protection through `expected_updated_at`
- signed file URL creation for uploaded invoice files
- "Ask AI" natural-language invoice search through `POST /api/v1/invoices/nl-search`, with interpreted-filter chips and a reset control
- low-confidence highlighting on correction fields (per-field extraction confidences below 0.75)
- validation explanations and suggested fixes under failed rules, with anomaly badges for `amount_anomaly`/`near_duplicate_similarity`
- AI-assigned expense category badges on line items
- "Auto-approved by AI" badge for invoices approved without a human review
- dashboard drill-down beyond the current cockpit panels remains pending

## Source layout

The React code is structured by responsibility instead of keeping UI, API calls, authorization, and form handling in one file:

```text
src/
  app/                  app shell and TanStack Router assembly
  components/common/    reusable presentational UI primitives
  domain/               typed domain models and authorization rules
  features/             feature panels grouped by business workflow
  queries/              TanStack Query hooks, one file per resource
  routes/               route components wired to queries and features
  services/             API client, session persistence, and endpoint services
  lib/                  shared utilities (shadcn/ui helpers)
  test/                 Vitest unit tests
  utils/                small formatting and form helpers
  main.tsx              React bootstrap
```

Feature code should depend on domain types and service contracts, not raw `fetch` calls. Server state belongs in `queries/` (TanStack Query hooks); endpoint-specific behavior belongs under `services/`; reusable visual pieces belong under `components/common/`.

Current frontend production patterns:

- `QueryClientProvider` is configured at the React root for server-state migration.
- Reusable sortable tables use TanStack Table through `components/common/DataTable.tsx`.
- New forms should use React Hook Form and Zod schemas; the sign-in form is the first implemented pattern.
- Host-side Playwright tests live in `e2e/` and run against the Docker-served cockpit.

Run it with the Docker stack:

```bash
docker compose up -d --build
```

Then open:

```text
http://localhost:3000/
```

The app expects a database-backed `reviewer` or `admin` user with a stored password hash.

Run the frontend development server:

```bash
cd frontend
npm install
npm run dev
```

Then open:

```text
http://localhost:3000/
```

Run authenticated browser workflow tests after the Docker stack is running:

```bash
APP_URL=http://localhost:3000/ ../scripts/check-cockpit-e2e.sh
```
