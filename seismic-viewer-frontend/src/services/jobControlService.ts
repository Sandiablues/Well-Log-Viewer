// JOB_CONTROL_2_FRONTEND_SERVICE
import axios from 'axios';

export type SystemJobActionState = {
  can_cancel?: boolean;
  can_force_stop?: boolean;
  can_cleanup_temp?: boolean;
  reason?: string;
};

export type SystemJobArtifactInfo = {
  path?: string | null;
  exists?: boolean;
  size_bytes?: number;
  file_count?: number;
  last_write_epoch?: number | null;
  seconds_since_last_write?: number | null;
};

export type SystemJobInventoryItem = {
  schema_version?: string;
  job_id: string;
  job_record_path?: string;
  job_type?: string;
  status?: string;
  normalized_status?: string;
  health?: string;
  health_reason?: string;
  progress?: number | null;
  message?: string | null;
  error?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  updated_at?: string | null;
  finished_at?: string | null;
  ids?: Record<string, string | null | undefined>;
  paths?: {
    input_path?: string | null;
    output_path?: string | null;
    temp_output_path?: string | null;
  };
  artifact_status?: {
    input?: SystemJobArtifactInfo;
    temp?: SystemJobArtifactInfo;
    output?: SystemJobArtifactInfo;
  };
  runtime?: Record<string, unknown>;
  actions?: SystemJobActionState;
};

export type SystemJobsResponse = {
  schema_version: string;
  generated_at?: string;
  runtime_profile?: string;
  control_mode?: string;
  job_count: number;
  total_job_records?: number;
  active_count?: number;
  possibly_stalled_count?: number;
  failed_count?: number;
  jobs: SystemJobInventoryItem[];
};

export async function getSystemJobs(limit = 20): Promise<SystemJobsResponse> {
  const response = await axios.get('/api/system/jobs', {
    params: { limit },
  });
  return response.data;
}
