import { cn } from "@/lib/utils";

// pavement palette lives on dark surfaces. backgrounds are a low-% tint,
// text uses the pastel at full (it reads bright on greenscale-800/900).
const STYLES: Record<string, string> = {
  excellent:
    "bg-[color-mix(in_oklab,var(--smooth-excellent)_18%,transparent)] text-[color:var(--smooth-excellent)] ring-[color-mix(in_oklab,var(--smooth-excellent)_35%,transparent)]",
  good:
    "bg-[color-mix(in_oklab,var(--smooth-good)_16%,transparent)] text-[color:var(--smooth-good)] ring-[color-mix(in_oklab,var(--smooth-good)_32%,transparent)]",
  intermediate:
    "bg-[color-mix(in_oklab,var(--smooth-intermediate)_14%,transparent)] text-[color:var(--smooth-intermediate)] ring-[color-mix(in_oklab,var(--smooth-intermediate)_28%,transparent)]",
  bad:
    "bg-[color-mix(in_oklab,var(--smooth-bad)_16%,transparent)] text-[color:var(--smooth-bad)] ring-[color-mix(in_oklab,var(--smooth-bad)_32%,transparent)]",
  very_bad:
    "bg-[color-mix(in_oklab,var(--smooth-very-bad)_16%,transparent)] text-[color:var(--smooth-very-bad)] ring-[color-mix(in_oklab,var(--smooth-very-bad)_32%,transparent)]",
};

export function SmoothnessBadge({
  value,
  variant = "solid",
  className,
}: {
  value: string;
  variant?: "solid" | "ghost";
  className?: string;
}) {
  if (!value) return <span className="text-xs text-muted-foreground">-</span>;
  const base =
    "inline-flex items-center rounded-[4px] px-1.5 py-0.5 font-mono text-[10.5px] font-normal uppercase tracking-[0.04em] ring-1 ring-inset";
  return (
    <span
      className={cn(
        base,
        STYLES[value] ?? "bg-muted text-muted-foreground ring-border",
        variant === "ghost" && "bg-transparent",
        className
      )}
    >
      {value.replace("_", " ")}
    </span>
  );
}

export function SmoothnessDot({ value, className }: { value: string; className?: string }) {
  return (
    <span
      className={cn("inline-block size-2 rounded-full", className)}
      style={{ background: `var(--smooth-${value.replace("_", "-")})` }}
    />
  );
}
