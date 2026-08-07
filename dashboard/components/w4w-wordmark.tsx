"use client";

import { DotLottieReact } from "@lottiefiles/dotlottie-react";
import { cn } from "@/lib/utils";

/** Animated Wheels4Wheels wordmark — same asset as w4w.vercel.app. */
export function W4WWordmark({
  className,
  autoplay = true,
}: {
  className?: string;
  autoplay?: boolean;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "relative block w-full max-w-[240px] overflow-hidden",
        className
      )}
      style={{ aspectRatio: "4844 / 485" }}
    >
      <DotLottieReact
        src="/W4W-Wordmark.lottie"
        autoplay={autoplay}
        loop
        className="block h-full w-full"
      />
    </span>
  );
}
