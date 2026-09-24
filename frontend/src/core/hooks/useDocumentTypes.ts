/**
 * Document Types Hook
 *
 * Provides access to document type configurations from the backend.
 * Use this hook to get document type settings for file uploads,
 * including allowed extensions, size limits, and extraction settings.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { documentTypes as documentTypesApi } from '../services/api';
import type { DocumentType } from '../types';

interface UseDocumentTypesResult {
  /** All document types */
  documentTypes: DocumentType[];
  /** Loading state */
  loading: boolean;
  /** Error message if failed to load */
  error: string | null;
  /** Refresh document types from API */
  refetch: () => Promise<void>;
  /** Get document type by type_id */
  getDocumentType: (typeId: string) => DocumentType | undefined;
  /** Get allowed file extensions for a document type */
  getAllowedExtensions: (typeId: string) => string[];
  /** Get max file size in bytes for a document type */
  getMaxSizeBytes: (typeId: string) => number;
  /** Check if a file is valid for a document type */
  isFileValid: (typeId: string, file: File) => { valid: boolean; error?: string };
  /** Document types with extraction enabled */
  extractableTypes: DocumentType[];
}

// Default values if document type not found
const DEFAULT_EXTENSIONS = ['.pdf'];
const DEFAULT_MAX_SIZE_MB = 10;

export function useDocumentTypes(): UseDocumentTypesResult {
  const [documentTypes, setDocumentTypes] = useState<DocumentType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDocumentTypes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await documentTypesApi.list({ active_only: true });
      setDocumentTypes(response.items);
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to load document types';
      setError(message);
      console.error('Failed to fetch document types:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocumentTypes();
  }, [fetchDocumentTypes]);

  const getDocumentType = useCallback(
    (typeId: string): DocumentType | undefined => {
      return documentTypes.find((dt) => dt.type_id === typeId);
    },
    [documentTypes]
  );

  const getAllowedExtensions = useCallback(
    (typeId: string): string[] => {
      const docType = getDocumentType(typeId);
      return docType?.allowed_extensions || DEFAULT_EXTENSIONS;
    },
    [getDocumentType]
  );

  const getMaxSizeBytes = useCallback(
    (typeId: string): number => {
      const docType = getDocumentType(typeId);
      const maxSizeMb = docType?.max_size_mb || DEFAULT_MAX_SIZE_MB;
      return maxSizeMb * 1024 * 1024;
    },
    [getDocumentType]
  );

  const isFileValid = useCallback(
    (typeId: string, file: File): { valid: boolean; error?: string } => {
      const docType = getDocumentType(typeId);
      const allowedExtensions = docType?.allowed_extensions || DEFAULT_EXTENSIONS;
      const maxSizeMb = docType?.max_size_mb || DEFAULT_MAX_SIZE_MB;
      const maxSizeBytes = maxSizeMb * 1024 * 1024;

      // Check file extension
      const fileName = file.name.toLowerCase();
      const hasValidExtension = allowedExtensions.some((ext) =>
        fileName.endsWith(ext.toLowerCase())
      );
      if (!hasValidExtension) {
        const extList = allowedExtensions.join(', ');
        return {
          valid: false,
          error: `Invalid file type. Allowed: ${extList}`,
        };
      }

      // Check file size
      if (file.size > maxSizeBytes) {
        return {
          valid: false,
          error: `File too large. Maximum size: ${maxSizeMb}MB`,
        };
      }

      return { valid: true };
    },
    [getDocumentType]
  );

  // Document types that have extraction enabled
  const extractableTypes = useMemo(() => {
    return documentTypes.filter((dt) => dt.extract_enabled);
  }, [documentTypes]);

  return {
    documentTypes,
    loading,
    error,
    refetch: fetchDocumentTypes,
    getDocumentType,
    getAllowedExtensions,
    getMaxSizeBytes,
    isFileValid,
    extractableTypes,
  };
}
