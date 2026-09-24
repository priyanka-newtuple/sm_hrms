/**
 * Types for resume upload and parsing.
 */

export type ExtractionStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface ExperienceEntry {
  title: string;
  company: string;
  start_date?: string;
  end_date?: string;
  description?: string;
}

export interface EducationEntry {
  degree: string;
  institution: string;
  year?: string;
  field_of_study?: string;
}

export interface ResumeExtractionResult {
  file_id: string;
  filename: string;
  status: ExtractionStatus;
  storage_key?: string;

  // Extracted data
  name?: string;
  email?: string;
  phone?: string;
  location?: string;
  linkedin_url?: string;
  skills: string[];
  experience: ExperienceEntry[];
  education: EducationEntry[];
  summary?: string;
  confidence_score: number;

  // Error info
  error_message?: string;

  // Duplicate detection
  is_duplicate: boolean;
  duplicate_candidate_id?: string;
  duplicate_candidate_name?: string;
  duplicate_applications_count?: number;
  duplicate_applications_summary?: Array<{
    application_id: string;
    job_title: string;
    state: string;
    created_at?: string;
  }>;
  duplicate_has_resume?: boolean;
  duplicate_last_updated?: string;
}

export interface ResumeUploadResponse {
  job_id: string;
  status: 'queued' | 'processing';  // Job initial status (queued if another job is running)
  total_files: number;
  accepted_files: number;
  rejected_files: Array<{ filename: string; reason: string }>;
  message: string;
}

export interface ResumeJobStatus {
  job_id: string;
  status: ExtractionStatus;
  total_files: number;
  completed_count: number;
  failed_count: number;
  created_at: string;
  updated_at: string;
}

export interface ResumeJobResults {
  job_id: string;
  status: ExtractionStatus;
  results: ResumeExtractionResult[];
}

export interface CandidateConfirmRequest {
  file_id: string;
  name: string;
  email?: string;
  phone?: string;
  location?: string;
  linkedin_url?: string;
  skills: string[];
  source?: string;
  notes?: string;
  experience_json?: string;
  education_json?: string;
  update_mode?: 'create' | 'update';
  existing_candidate_id?: string;
}

export interface BatchConfirmRequest {
  candidates: CandidateConfirmRequest[];
  /** Optional job ID to automatically create applications for all confirmed candidates */
  job_id?: string;
}

export interface BatchConfirmResponse {
  total: number;
  created: number;
  failed: number;
  /** Count of applications created (when job_id was provided) */
  applications_created: number;
  results: Array<{
    file_id: string;
    success: boolean;
    candidate_id?: string;
    /** Application ID if an application was created */
    application_id?: string;
    /** Initial state of the created application */
    application_state?: string;
    action?: 'created' | 'updated';
    applications_updated?: number;
    /** Error message if application creation failed */
    application_error?: string;
    error?: string;
  }>;
}
