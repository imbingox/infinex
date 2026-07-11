export type StatusTone = "success" | "processing" | "warning" | "error" | "default";

export function statusTone(status: string): StatusTone {
  if (["online", "running", "succeeded", "published"].includes(status)) return "success";
  if (["queued", "claimed", "starting", "preparing", "ready"].includes(status)) {
    return "processing";
  }
  if (["degraded", "stopping", "candidate"].includes(status)) return "warning";
  if (["offline", "failed"].includes(status)) return "error";
  return "default";
}
