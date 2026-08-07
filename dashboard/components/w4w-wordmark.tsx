"use client";

import Image from "next/image";
import { DotLottieReact } from "@lottiefiles/dotlottie-react";
import { cn } from "@/lib/utils";

/** Native powered-by-bolt.svg is 89×11; main site renders it ~10% larger. */
const POWERED_BY_W = 97.9;
const POWERED_BY_H = 12.1;

/** Animated Wheels4Wheels wordmark + powered-by — same lockup as w4w.vercel.app. */
export function W4WWordmark({
  className,
  autoplay = true,
  showPoweredBy = true,
}: {
  className?: string;
  autoplay?: boolean;
  showPoweredBy?: boolean;
}) {
  return (
    <span
      className={cn(
        "relative inline-flex w-full max-w-[240px] flex-col items-start",
        className
      )}
    >
      <span
        aria-hidden="true"
        className="relative block w-full max-w-[240px] overflow-hidden"
        style={{ aspectRatio: "4844 / 485" }}
      >
        <DotLottieReact
          src="/W4W-Wordmark.lottie"
          autoplay={autoplay}
          loop
          className="block h-full w-full"
        />
      </span>
      {showPoweredBy ? (
        <span
          aria-hidden="true"
          className="mt-[10px] block"
          style={{ width: POWERED_BY_W, height: POWERED_BY_H }}
        >
          <Image
            src="/powered-by-bolt.svg"
            alt=""
            width={89}
            height={11}
            className="block max-w-none"
            style={{ width: POWERED_BY_W, height: POWERED_BY_H }}
            priority
          />
        </span>
      ) : null}
    </span>
  );
}
