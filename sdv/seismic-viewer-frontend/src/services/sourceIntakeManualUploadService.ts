// MANUAL_UPLOAD_STAGING_3_FRONTEND

export type ManualUploadMode = "2d" | "3d" | "auto";

export type ManualUploadPackageResult = {
  schema_version?: string;
  package_id?: string;
  repository_id?: string;
  mode?: ManualUploadMode | string;
  package_name?: string;
  staged_for_conversion?: boolean;
  uploaded_files?: Array<Record<string, any>>;
  segy_candidates?: Array<Record<string, any>>;
  supporting_documents?: Array<Record<string, any>>;
  unsupported_files?: Array<Record<string, any>>;
  classification_summary?: Record<string, any>;
  next_actions?: string[];
  conversion_started?: boolean;
  index_started?: boolean;
  msi_registration_started?: boolean;
  warnings?: string[];
  storage?: Record<string, any>;
};

export type ManualUploadWorkbenchStageResult = {
  schema_version?: string;
  mode?: string;
  repository_id?: string;
  row_count?: number;
  rows?: Array<Record<string, any>>;
  summary?: Record<string, any>;
  workbench?: Record<string, any>;
  [key: string]: any;
};

async function assertOk(response: Response, fallback: string): Promise<Response> {
  if (response.ok) return response;
  const text = await response.text();
  throw new Error(text || `${fallback} (${response.status})`);
}

export async function uploadManualSourceIntakePackage(args: {
  files: File[];
  mode: ManualUploadMode;
  packageName?: string;
  intendedUse?: string;
}): Promise<ManualUploadPackageResult> {
  const form = new FormData();
  form.append("mode", args.mode);
  form.append("package_name", args.packageName?.trim() || "Manual Upload Package");
  form.append("intended_use", args.intendedUse || "source_intake");
  args.files.forEach((file) => form.append("files", file, file.name));

  const response = await fetch("/api/source-intake/manual-upload-package", {
    method: "POST",
    body: form,
  });

  await assertOk(response, "Manual upload staging failed");
  return response.json();
}

export async function stageManualUploadRepositoryInWorkbench(args: {
  mode: "2d" | "3d";
  repositoryId: string;
}): Promise<ManualUploadWorkbenchStageResult> {
  const response = await fetch("/api/source-intake/workbench-v2/use-repository", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode: args.mode,
      repository_id: args.repositoryId,
    }),
  });

  await assertOk(response, "Manual upload workbench staging failed");
  return response.json();
}
