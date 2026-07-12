# Frontend

This folder owns the React frontend application.

## Stack

The frontend stack is:

- Vite
- React
- TypeScript
- Tailwind CSS
- Lucide icons
- TanStack Query
- TanStack Table
- React Hook Form
- Zod

Likely production-grade additions after the current cockpit:

- shadcn-compatible utility dependencies
- Recharts

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
- dashboard drill-down beyond the current cockpit panels remains pending

## Source layout

The React code is structured by responsibility instead of keeping UI, API calls, authorization, and form handling in one file:

```text
src/
  app/                  app-level navigation and cockpit controller hook
  components/common/    reusable presentational UI primitives
  domain/               typed domain models and authorization rules
  features/             feature panels grouped by business workflow
  services/             API client, session persistence, and endpoint services
  utils/                small formatting and form helpers
  App.tsx               composition shell only
  main.tsx              React bootstrap
```

Feature code should depend on domain types and service contracts, not raw `fetch` calls. Cross-feature behavior belongs in `app/useCockpitController.ts`; endpoint-specific behavior belongs under `services/`; reusable visual pieces belong under `components/common/`.

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
