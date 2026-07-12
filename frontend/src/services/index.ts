import { API_BASE_URL } from "../config";
import { ApiClient } from "./api-client";
import { AuditLogService } from "./audit-log-service";
import { AuthService } from "./auth-service";
import { InvoiceService } from "./invoice-service";
import { ProcessingJobService } from "./processing-job-service";
import { UserService } from "./user-service";

// Composition root: one ApiClient shared by every service so refresh/auth handling is centralized.
export const apiClient = new ApiClient(API_BASE_URL);
export const authService = new AuthService(apiClient);
export const invoiceService = new InvoiceService(apiClient);
export const processingJobService = new ProcessingJobService(apiClient);
export const auditLogService = new AuditLogService(apiClient);
export const userService = new UserService(apiClient);
