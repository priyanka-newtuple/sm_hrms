/**
 * Upload Service
 *
 * Handles presigned URL uploads with progress tracking.
 * Supports both direct MinIO uploads and fallback to backend for local storage.
 */

import { resumeUpload } from './api';
import type {
  UploadJob,
  PrepareUploadResponse,
  PrepareUploadFileResponse,
} from '../types';

export interface UploadCallbacks {
  onFileProgress: (uploadJobId: string, fileId: string, uploadedBytes: number, totalBytes: number) => void;
  onFileComplete: (uploadJobId: string, fileId: string, storageKey: string) => void;
  onFileFailed: (uploadJobId: string, fileId: string, error: string) => void;
  onAllComplete: (uploadJobId: string, extractionJobId: string) => void;
  onError: (uploadJobId: string, error: string) => void;
}

interface UploadSession {
  sessionId: string;
  storageType: 'minio' | 'local';
  files: Map<string, {
    file: File;
    fileInfo: PrepareUploadFileResponse;
    abortController: AbortController;
  }>;
  callbacks: UploadCallbacks;
}

class UploadService {
  private activeSessions: Map<string, UploadSession> = new Map();

  /**
   * Start uploading files with presigned URLs
   */
  async startUpload(
    files: File[],
    callbacks: UploadCallbacks
  ): Promise<{ uploadJobId: string; uploadJob: UploadJob }> {
    // Prepare upload - get presigned URLs
    const fileInfos = files.map((file) => ({
      filename: file.name,
      size_bytes: file.size,
      content_type: file.type || 'application/pdf',
    }));

    let response: PrepareUploadResponse;
    // Generate a temporary ID for error tracking before we have the real one
    const tempJobId = `upload-temp-${Date.now()}`;

    try {
      response = await resumeUpload.prepareUpload(fileInfos);
    } catch (e) {
      const error = e instanceof Error ? e.message : 'Failed to prepare upload';
      callbacks.onError(tempJobId, error);
      throw e;
    }

    // Create upload job object with real ID
    const uploadJobId = `upload-${response.upload_session_id}`;
    const uploadJob: UploadJob = {
      id: uploadJobId,
      session_id: response.upload_session_id,
      status: 'uploading',
      storage_type: response.storage_type as 'minio' | 'local',
      files: response.files.map((f) => ({
        file_id: f.file_id,
        filename: f.filename,
        size_bytes: files.find((file) => file.name === f.filename)?.size || 0,
        uploaded_bytes: 0,
        status: 'pending' as const,
        storage_key: f.storage_key,
      })),
      created_at: new Date().toISOString(),
    };

    // Create session
    const session: UploadSession = {
      sessionId: response.upload_session_id,
      storageType: response.storage_type as 'minio' | 'local',
      files: new Map(),
      callbacks,
    };

    // Map files to their info
    for (const fileInfo of response.files) {
      const file = files.find((f) => f.name === fileInfo.filename);
      if (file) {
        session.files.set(fileInfo.file_id, {
          file,
          fileInfo,
          abortController: new AbortController(),
        });
      }
    }

    this.activeSessions.set(uploadJobId, session);

    // Start uploading files in parallel
    this.uploadFiles(uploadJobId);

    return { uploadJobId, uploadJob };
  }

  /**
   * Upload all files in a session
   */
  private async uploadFiles(uploadJobId: string): Promise<void> {
    const session = this.activeSessions.get(uploadJobId);
    if (!session) return;

    // Track which files succeed
    const successfulFileIds = new Set<string>();

    const uploadPromises: Promise<void>[] = [];

    for (const [fileId, fileData] of session.files) {
      const promise = this.uploadSingleFile(uploadJobId, fileId, fileData)
        .then(() => {
          // Mark as successful
          successfulFileIds.add(fileId);
        })
        .catch((error) => {
          // Already handled in uploadSingleFile, but ensure we don't mark as successful
          console.error(`Upload failed for ${fileId}:`, error);
        });
      uploadPromises.push(promise);
    }

    // Wait for all uploads to complete
    await Promise.allSettled(uploadPromises);

    // Collect only successfully uploaded files
    const completedFiles: Array<{ file_id: string; filename: string; storage_key: string }> = [];

    for (const [fileId, fileData] of session.files) {
      if (successfulFileIds.has(fileId)) {
        completedFiles.push({
          file_id: fileId,
          filename: fileData.fileInfo.filename,
          storage_key: fileData.fileInfo.storage_key,
        });
      }
    }

    // Complete the upload on the backend
    if (completedFiles.length > 0) {
      try {
        const result = await resumeUpload.completeUpload({
          upload_session_id: session.sessionId,
          uploaded_files: completedFiles,
        });

        session.callbacks.onAllComplete(uploadJobId, result.job_id);
      } catch (e) {
        const error = e instanceof Error ? e.message : 'Failed to complete upload';
        session.callbacks.onError(uploadJobId, error);
      }
    } else {
      session.callbacks.onError(uploadJobId, 'No files were uploaded successfully');
    }

    // Clean up session
    this.activeSessions.delete(uploadJobId);
  }

  /**
   * Upload a single file
   */
  private async uploadSingleFile(
    uploadJobId: string,
    fileId: string,
    fileData: {
      file: File;
      fileInfo: PrepareUploadFileResponse;
      abortController: AbortController;
    }
  ): Promise<void> {
    const session = this.activeSessions.get(uploadJobId);
    if (!session) {
      throw new Error('Session not found');
    }

    const { file, fileInfo, abortController } = fileData;
    const { callbacks } = session;

    try {
      if (fileInfo.presigned_url) {
        // Direct upload to MinIO
        await this.uploadToPresignedUrl(
          file,
          fileInfo.presigned_url,
          abortController.signal,
          (uploaded, total) => {
            callbacks.onFileProgress(uploadJobId, fileId, uploaded, total);
          }
        );
      } else {
        // Fallback: upload through backend
        await this.uploadThroughBackend(
          session.sessionId,
          fileId,
          file,
          (uploaded, total) => {
            callbacks.onFileProgress(uploadJobId, fileId, uploaded, total);
          }
        );
      }

      callbacks.onFileComplete(uploadJobId, fileId, fileInfo.storage_key);
      // Success - don't throw, let the promise resolve
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') {
        callbacks.onFileFailed(uploadJobId, fileId, 'Upload cancelled');
      } else {
        const error = e instanceof Error ? e.message : 'Upload failed';
        callbacks.onFileFailed(uploadJobId, fileId, error);
      }
      // Re-throw so the caller knows it failed
      throw e;
    }
  }

  /**
   * Upload directly to MinIO using presigned URL
   */
  private uploadToPresignedUrl(
    file: File,
    presignedUrl: string,
    signal: AbortSignal,
    onProgress: (uploaded: number, total: number) => void
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress(e.loaded, e.total);
        }
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          onProgress(file.size, file.size);
          resolve();
        } else {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      };

      xhr.onerror = () => {
        reject(new Error('Network error during upload'));
      };

      xhr.onabort = () => {
        reject(new DOMException('Upload aborted', 'AbortError'));
      };

      // Handle abort signal
      signal.addEventListener('abort', () => {
        xhr.abort();
      });

      xhr.open('PUT', presignedUrl);
      xhr.setRequestHeader('Content-Type', file.type || 'application/pdf');
      xhr.send(file);
    });
  }

  /**
   * Upload through backend (fallback for local storage)
   */
  private async uploadThroughBackend(
    sessionId: string,
    fileId: string,
    file: File,
    onProgress: (uploaded: number, total: number) => void
  ): Promise<void> {
    // For backend upload, we use fetch which doesn't support progress
    // We'll simulate progress: 0 -> 50% immediately, 100% on complete
    onProgress(0, file.size);
    onProgress(Math.floor(file.size / 2), file.size);

    await resumeUpload.uploadSingleFile(sessionId, fileId, file);

    onProgress(file.size, file.size);
  }

  /**
   * Cancel an upload job
   */
  cancelUpload(uploadJobId: string): void {
    const session = this.activeSessions.get(uploadJobId);
    if (!session) return;

    // Abort all file uploads
    for (const [, fileData] of session.files) {
      fileData.abortController.abort();
    }

    this.activeSessions.delete(uploadJobId);
  }

  /**
   * Cancel a single file upload
   */
  cancelFileUpload(uploadJobId: string, fileId: string): void {
    const session = this.activeSessions.get(uploadJobId);
    if (!session) return;

    const fileData = session.files.get(fileId);
    if (fileData) {
      fileData.abortController.abort();
    }
  }
}

// Singleton instance
export const uploadService = new UploadService();
