import { expect, test } from "@playwright/test";

const adminEmail = process.env.E2E_ADMIN_EMAIL || "admin@example.com";
const adminPassword = process.env.E2E_ADMIN_PASSWORD || "production-grade-password-123";
const apiBaseUrl = process.env.E2E_API_BASE_URL || "http://localhost:8010";

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByLabel("Email").fill(adminEmail);
  await page.getByLabel("Password").fill(adminPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.locator(".session-chip")).toContainText(adminEmail);
}

test("admin can sign in and access protected cockpit areas", async ({ page }) => {
  await signIn(page);

  await page.getByRole("link", { name: "Upload" }).click();
  await expect(page.getByRole("heading", { name: "Upload Invoice" })).toBeVisible();

  await page.getByRole("link", { name: "Failed Jobs" }).click();
  await expect(page.getByRole("heading", { name: "Failed Jobs" })).toBeVisible();

  await page.getByRole("link", { name: "Audit Logs" }).click();
  await expect(page.getByRole("heading", { name: "Audit Logs" })).toBeVisible();

  await page.getByRole("link", { name: "Users" }).click();
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible();
});

async function accessToken(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const raw = window.localStorage.getItem("fde.invoice.session");
    return raw ? JSON.parse(raw).access_token as string : "";
  });
}

async function waitForInvoiceStatus(
  request: import("@playwright/test").APIRequestContext,
  token: string,
  invoiceNumber: string,
  status: string,
) {
  await expect
    .poll(
      async () => {
        const response = await request.get(`${apiBaseUrl}/api/v1/invoices`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const payload = await response.json();
        const invoice = payload.invoices.find((item: { invoice_number: string }) => item.invoice_number === invoiceNumber);
        return invoice?.status;
      },
      { timeout: 15_000 },
    )
    .toBe(status);
}

test("admin can upload an invoice, review it, and approve it", async ({ page, request }) => {
  const invoiceNumber = `E2E-${Date.now()}`;

  await signIn(page);
  await page.getByRole("link", { name: "Upload" }).click();
  await page.getByLabel("Invoice number").fill(invoiceNumber);
  await page.getByLabel("Currency").fill("USD");
  await page.getByLabel("Total amount").fill("123.45");
  await page.getByLabel("Invoice file").setInputFiles({
    name: `${invoiceNumber}.pdf`,
    mimeType: "application/pdf",
    buffer: Buffer.from(`%PDF-1.4\n% ${invoiceNumber}\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n`),
  });
  await page.getByRole("button", { name: "Upload and queue" }).click();

  await expect(page.getByText(`Uploaded ${invoiceNumber}.`)).toBeVisible();
  await waitForInvoiceStatus(request, await accessToken(page), invoiceNumber, "review_required");

  await page.getByRole("link", { name: "Review Queue" }).click();
  await page.getByRole("button", { name: "Refresh invoices" }).click();
  await expect(page.getByRole("button", { name: new RegExp(invoiceNumber) })).toBeVisible();
  await page.getByRole("button", { name: new RegExp(invoiceNumber) }).click();
  await expect(page.getByRole("heading", { name: invoiceNumber })).toBeVisible();
  await page.getByLabel("Review notes").fill("Approved by cockpit E2E.");
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Invoice approved.")).toBeVisible();
});

test("admin can filter audit logs and create a user", async ({ page }) => {
  const userEmail = `e2e-user-${Date.now()}@example.com`;

  await signIn(page);
  await page.getByRole("link", { name: "Audit Logs" }).click();
  await page.getByLabel("Action").fill("user");
  await page.getByRole("button", { name: "Filter" }).click();
  await expect(page.getByRole("heading", { name: "Audit Logs" })).toBeVisible();

  await page.getByRole("link", { name: "Users" }).click();
  await page.locator("form").filter({ hasText: "Create user" }).getByLabel("Email").fill(userEmail);
  await page.locator("form").filter({ hasText: "Create user" }).getByLabel("Role").selectOption("reviewer");
  await page.locator("form").filter({ hasText: "Create user" }).getByLabel("Temporary password").fill("reviewer-password-123");
  await page.getByRole("button", { name: "Create user" }).click();

  await expect(page.getByText("User created.")).toBeVisible();
  await expect(page.getByRole("table").getByText(userEmail)).toBeVisible();
});
