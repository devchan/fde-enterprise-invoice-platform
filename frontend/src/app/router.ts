import { createRouter } from "@tanstack/react-router";
import { Route as RootRoute } from "../routes/__root";
import { Route as AuditRoute } from "../routes/audit";
import { Route as FailedRoute } from "../routes/failed";
import { Route as IndexRoute } from "../routes/index";
import { Route as ReviewRoute } from "../routes/review";
import { Route as UploadRoute } from "../routes/upload";
import { Route as UsersRoute } from "../routes/users";

// Code-based route tree (no file-based codegen): this app has 6 fixed routes,
// well within the size where hand-assembling the tree is simpler than running
// the router-plugin's Vite codegen.
const routeTree = RootRoute.addChildren([IndexRoute, UploadRoute, ReviewRoute, FailedRoute, AuditRoute, UsersRoute]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
