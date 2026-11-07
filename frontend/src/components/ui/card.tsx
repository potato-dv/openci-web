import * as React from "react";
import { cn } from "@/lib/utils";

function Card({ className, ...props }: React.ComponentProps<"section">) {
  return (
    <section
      data-slot="card"
      className={cn("min-w-0 rounded-xl border border-border bg-card text-card-foreground", className)}
      {...props}
    />
  );
}

export { Card };
