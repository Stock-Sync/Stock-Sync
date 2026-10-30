import { httpClient } from "./http-client";

export interface PullListingsResult {
  run_id: number;
  status: "completed" | "completed_with_errors" | "failed";
  items_found: number;
  items_upserted: number;
  mappings_created: number;
  errors: string[];
}

export interface SyncStatus {
  last_pull: {
    run_id: number;
    status: string;
    items_found: number;
    items_upserted: number;
    mappings_created: number;
    started_at: string;
    finished_at: string | null;
    error_summary: string | null;
  } | null;
  stream: {
    pending_events: number | null;
    pending_quantity_updates: number | null;
    dead_letters: number | null;
  };
}

export const syncClient = {
  /** Full pull of ML listings → local items + platform mappings. */
  async pullListings(): Promise<PullListingsResult> {
    return httpClient.post<PullListingsResult>("/api/v1/sync/listings/pull", {});
  },

  async getStatus(): Promise<SyncStatus> {
    return httpClient.get<SyncStatus>("/api/v1/sync/status");
  },
};
