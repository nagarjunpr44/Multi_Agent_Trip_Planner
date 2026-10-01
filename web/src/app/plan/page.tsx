import { Suspense } from "react";
import { Workspace } from "@/components/plan/Workspace";

// The trip id is a query param (?id=) so this stays a single static page in the export.
export default function PlanPage() {
  return (
    <Suspense fallback={<div className="h-dvh bg-night" />}>
      <Workspace />
    </Suspense>
  );
}
