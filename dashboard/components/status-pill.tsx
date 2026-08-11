import { cn } from "@/lib/cn";

type State = "pending" | "active" | "revoked";

const COLOR: Record<State, string> = {
  active: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  pending: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  revoked: "bg-rose-500/15 text-rose-700 dark:text-rose-300",
};

export function StatusPill({
  state,
  lastSeen,
}: {
  state: State;
  lastSeen?: string | null;
}) {
  // "active" but stale > 30 min → amber pill, label still "active".
  const isStale =
    state === "active" && !!lastSeen &&
    Date.now() - new Date(lastSeen).getTime() > 30 * 60_000;
  const label = state;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
        isStale ? COLOR.pending : COLOR[state],
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}

