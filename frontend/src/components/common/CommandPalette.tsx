import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { Lock, LogOut, MessageSquareText, RefreshCw, SunMoon } from "lucide-react";
import { useAssistant } from "../../app/AssistantContext";
import { tabs } from "../../app/navigation";
import { useSession } from "../../app/useSession";
import { canAccessTab } from "../../domain/authorization";
import { useLogoutMutation } from "../../queries/auth";
import { useTheme } from "./theme-provider";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "../ui/command";

// Cmd/Ctrl+K power-user launcher: navigate to any tab (respecting the same RBAC
// lock icons as the sidebar) or run a few quick cross-cutting actions. Controlled
// (open/onOpenChange) so a header button can also trigger it, not just the shortcut.
export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate();
  const { session } = useSession();
  const { theme, setTheme } = useTheme();
  const { setOpen: setAssistantOpen } = useAssistant();
  const logoutMutation = useLogoutMutation();
  const queryClient = useQueryClient();

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        onOpenChange(!open);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onOpenChange]);

  function runCommand(action: () => void) {
    onOpenChange(false);
    action();
  }

  return (
    <CommandDialog onOpenChange={onOpenChange} open={open}>
      <CommandInput placeholder="Navigate or run a command…" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Navigate">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const locked = !canAccessTab(session, tab.key);
            return (
              <CommandItem
                disabled={locked}
                key={tab.key}
                onSelect={() => runCommand(() => navigate({ to: tab.path }))}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
                {locked ? <Lock className="ml-auto h-3.5 w-3.5 text-muted-foreground" aria-label="Access restricted" /> : null}
              </CommandItem>
            );
          })}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Actions">
          {session ? (
            <CommandItem onSelect={() => runCommand(() => setAssistantOpen(true))}>
              <MessageSquareText className="h-4 w-4" />
              Ask the assistant
            </CommandItem>
          ) : null}
          <CommandItem onSelect={() => runCommand(() => void queryClient.invalidateQueries())}>
            <RefreshCw className="h-4 w-4" />
            Refresh all data
          </CommandItem>
          <CommandItem onSelect={() => runCommand(() => setTheme(theme === "dark" ? "light" : "dark"))}>
            <SunMoon className="h-4 w-4" />
            Toggle theme
          </CommandItem>
          {session ? (
            <CommandItem onSelect={() => runCommand(() => logoutMutation.mutate())}>
              <LogOut className="h-4 w-4" />
              Sign out
            </CommandItem>
          ) : null}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
