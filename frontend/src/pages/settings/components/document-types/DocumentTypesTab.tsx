/**
 * DocumentTypesTab
 *
 * Settings tab for managing document type configurations.
 * Allows users to enable/disable document types, configure allowed extensions,
 * set max file sizes, and configure AI extraction settings.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Loader2,
  AlertCircle,
  RefreshCw,
  FileText,
  Image,
  X,
  Trash2,
  Plus,
  Edit2,
  Brain,
  ChevronDown,
  ChevronUp,
  HelpCircle,
  Info,
} from 'lucide-react';
import { documentTypes, unifiedIntegrations, agent as agentApi, mcp as mcpApi, entityTypes as entityTypesApi } from '../../../../core/services/api';
import { useOrgSelector } from '../../../../core/contexts/OrgSelectorContext';
import type {
  DocumentType,
  EntityType,
  DocumentTypeCreateRequest,
  DocumentTypeUpdateRequest,
  AgentDefinitionListItem,
  McpCapability,
  UploadContextConfig,
  ValidationRule,
  PostAction,
} from '../../../../core/types';
import Modal from '../../../../core/components/Modal';
import Badge from '../../../../core/components/Badge';
import { Button } from '@/components/ui/button';

type StorageProviderOption = {
  value: string;
  label: string;
};

function formatStorageProviderLabel(provider: string): string {
  if (provider === 'amazon_s3') return 'Amazon S3';
  if (provider === 'azure_blob_storage') return 'Azure Blob Storage';
  if (provider === 'local') return 'Local Storage';
  return provider
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

const IMAGE_EXTENSIONS = new Set([
  '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg',
  '.tiff', '.tif', '.avif', '.heic', '.heif',
]);

const hasImageExtensions = (docType: { allowed_extensions: string[] }) =>
  docType.allowed_extensions.some(ext => IMAGE_EXTENSIONS.has(ext.toLowerCase()));

export default function DocumentTypesTab() {
  const { selectedOrgId } = useOrgSelector();
  const [docTypes, setDocTypes] = useState<DocumentType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingType, setEditingType] = useState<DocumentType | null>(null);
  const [saving, setSaving] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  // Delete confirmation state
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Expanded extraction config
  const [expandedConfig, setExpandedConfig] = useState<string | null>(null);

  const [agentEnabled, setAgentEnabled] = useState(false);
  const [availableAgents, setAvailableAgents] = useState<AgentDefinitionListItem[]>([]);
  // Org MCP capabilities (id -> capability_key + enabled) used to validate that the
  // selected agent has the tools this document type's processing needs.
  const [capabilities, setCapabilities] = useState<McpCapability[]>([]);
  // Enabled capability_keys the currently-selected agent has (null until resolved).
  const [selectedAgentToolKeys, setSelectedAgentToolKeys] = useState<string[] | null>(null);
  const [availableEntityTypes, setAvailableEntityTypes] = useState<EntityType[]>([]);
  const entityTypeOptions = useMemo(
    () => availableEntityTypes.map((et) => (
      <option key={et.name} value={et.name}>{et.display_name || et.name}</option>
    )),
    [availableEntityTypes]
  );
  const [selectedAgentDefinitionId, setSelectedAgentDefinitionId] = useState('');
  const [storageProviderOptions, setStorageProviderOptions] = useState<StorageProviderOption[]>([
    { value: 'local', label: 'Local Storage' },
  ]);
  const [selectedStorageProvider, setSelectedStorageProvider] = useState<string>('local');

  // Form state
  const [formData, setFormData] = useState<DocumentTypeCreateRequest>({
    type_id: '',
    display_name: '',
    description: '',
    folder: '',
    allowed_extensions: ['.pdf'],
    max_size_mb: 10,
    is_entity: false,
    entity_type_name: '',
    state_machine_name: '',
    upload_contexts: [],
    agent_config: undefined,
    is_active: true,
  });

  // Validation rules for agent config
  const [validationRules, setValidationRules] = useState<ValidationRule[]>([]);
  const [postActions, setPostActions] = useState<PostAction[]>([]);
  const [uploadContexts, setUploadContexts] = useState<UploadContextConfig[]>([]);

  const fetchDocTypes = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await documentTypes.list();
      setDocTypes(result.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load document types');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAgents = useCallback(async () => {
    try {
      const agents = await agentApi.listDefinitions(true);
      setAvailableAgents(agents.filter((item) => item.is_active));
    } catch (e) {
      console.error('Failed to load agents:', e);
      setAvailableAgents([]);
    }
  }, []);

  const fetchCapabilities = useCallback(async () => {
    try {
      const overview = await mcpApi.getTooling();
      setCapabilities(overview.capabilities || []);
    } catch (e) {
      console.error('Failed to load MCP tooling:', e);
      setCapabilities([]);
    }
  }, []);

  // Resolve the selected agent's enabled tool capability_keys (for tool validation).
  useEffect(() => {
    let cancelled = false;
    if (!agentEnabled || !selectedAgentDefinitionId) {
      setSelectedAgentToolKeys(null);
      return;
    }
    (async () => {
      try {
        const def = await agentApi.getDefinition(selectedAgentDefinitionId);
        const allowed = new Set(def.allowed_tools || []);
        const keys = capabilities
          .filter((cap) => allowed.has(cap.id) && cap.is_enabled)
          .map((cap) => cap.capability_key);
        if (!cancelled) setSelectedAgentToolKeys(keys);
      } catch (e) {
        console.error('Failed to resolve agent tools:', e);
        if (!cancelled) setSelectedAgentToolKeys([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [agentEnabled, selectedAgentDefinitionId, capabilities]);

  // Tools this document type's agent must have: read_document always, plus the
  // tool matching each configured post-action.
  const requiredToolKeys = useMemo(() => {
    const req = new Set<string>(['read_document']);
    for (const action of postActions) {
      if (action.type === 'create_entity' || action.type === 'find_or_create') req.add('create_entity');
      if (action.type === 'update_entity') req.add('update_entity');
    }
    return req;
  }, [postActions]);

  const missingTools = useMemo(() => {
    if (!agentEnabled || !selectedAgentDefinitionId || selectedAgentToolKeys === null) return [];
    return [...requiredToolKeys].filter((key) => !selectedAgentToolKeys.includes(key));
  }, [agentEnabled, selectedAgentDefinitionId, selectedAgentToolKeys, requiredToolKeys]);

  const fetchEntityTypes = useCallback(async () => {
    try {
      const response = await entityTypesApi.list();
      setAvailableEntityTypes(response.items);
    } catch (e) {
      console.error('Failed to load entity types:', e);
    }
  }, []);

  const fetchStorageProviders = useCallback(async () => {
    if (!selectedOrgId) {
      setStorageProviderOptions([{ value: 'local', label: 'Local Storage' }]);
      setSelectedStorageProvider('local');
      return;
    }
    try {
      const response = await unifiedIntegrations.list(selectedOrgId) as { items?: Array<Record<string, unknown>> };
      const configuredStorageProviders = (response.items ?? [])
        .filter((item) => {
          const capabilities = Array.isArray(item.capabilities) ? item.capabilities.map(String) : [];
          return capabilities.includes('storage') && item.configured !== false && String(item.status || '').toLowerCase() !== 'error';
        })
        .map((item) => {
          const provider = String(item.provider || '').trim();
          const label = String(item.label || '').trim();
          return {
            value: provider,
            label: label || formatStorageProviderLabel(provider),
          };
        })
        .filter((item) => item.value.length > 0);

      if (configuredStorageProviders.length === 0) {
        setStorageProviderOptions([{ value: 'local', label: 'Local Storage' }]);
        setSelectedStorageProvider('local');
      } else {
        setStorageProviderOptions(configuredStorageProviders);
        setSelectedStorageProvider((previous) =>
          configuredStorageProviders.some((option) => option.value === previous)
            ? previous
            : configuredStorageProviders[0].value
        );
      }
    } catch {
      setStorageProviderOptions([{ value: 'local', label: 'Local Storage' }]);
      setSelectedStorageProvider('local');
    }
  }, [selectedOrgId]);

  useEffect(() => {
    fetchDocTypes();
    fetchAgents();
    fetchStorageProviders();
    fetchEntityTypes();
    fetchCapabilities();
  }, [fetchDocTypes, fetchAgents, fetchStorageProviders, fetchEntityTypes, fetchCapabilities]);

  const openCreateModal = () => {
    setEditingType(null);
    const fallbackStorageProvider = storageProviderOptions[0]?.value || 'local';
    setSelectedStorageProvider(fallbackStorageProvider);
    setFormData({
      type_id: '',
      display_name: '',
      description: '',
      folder: fallbackStorageProvider === 'local' ? '' : 'files',
      allowed_extensions: ['.pdf'],
      max_size_mb: 10,
      is_entity: false,
      entity_type_name: '',
      state_machine_name: '',
      upload_contexts: [],
      agent_config: undefined,
      is_active: true,
    });
    setExtensionsInput('.pdf');
    setValidationRules([]);
    setPostActions([]);
    setUploadContexts([]);
    setAgentEnabled(false);
    setSelectedAgentDefinitionId('');
    setIsModalOpen(true);
  };

  const openEditModal = (docType: DocumentType) => {
    setEditingType(docType);
    const metadata = docType.metadata ?? {};
    const configuredProvider = typeof metadata.storage_provider === 'string' && metadata.storage_provider.trim()
      ? metadata.storage_provider.trim()
      : 'local';
    setSelectedStorageProvider(configuredProvider);
    setFormData({
      type_id: docType.type_id,
      display_name: docType.display_name,
      description: docType.description || '',
      folder: docType.folder,
      allowed_extensions: docType.allowed_extensions,
      max_size_mb: docType.max_size_mb,
      is_entity: docType.is_entity || false,
      entity_type_name: docType.entity_type_name || '',
      state_machine_name: docType.state_machine_name || '',
      upload_contexts: docType.upload_contexts || [],
      agent_config: docType.agent_config || undefined,
      is_active: docType.is_active,
      metadata: metadata ?? undefined,
    });
    setExtensionsInput(docType.allowed_extensions.join(', '));
    setValidationRules(docType.agent_config?.validation_rules || []);
    setPostActions(docType.agent_config?.post_actions || []);
    setUploadContexts(docType.upload_contexts || []);
    setAgentEnabled(Boolean(metadata.agent_processing_enabled));
    setSelectedAgentDefinitionId(String(metadata.agent_definition_id || ''));
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingType(null);
    const fallbackStorageProvider = storageProviderOptions[0]?.value || 'local';
    setSelectedStorageProvider(fallbackStorageProvider);
    setFormData({
      type_id: '',
      display_name: '',
      description: '',
      folder: fallbackStorageProvider === 'local' ? '' : 'files',
      allowed_extensions: ['.pdf'],
      max_size_mb: 10,
      is_entity: false,
      entity_type_name: '',
      state_machine_name: '',
      upload_contexts: [],
      agent_config: undefined,
      is_active: true,
    });
    setExtensionsInput('');
    setValidationRules([]);
    setPostActions([]);
    setUploadContexts([]);
    setAgentEnabled(false);
    setSelectedAgentDefinitionId('');
    setModalError(null);
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      if (agentEnabled && !selectedAgentDefinitionId) {
        throw new Error('Select an agent when Agent Processing is enabled');
      }
      if (agentEnabled && missingTools.length > 0) {
        throw new Error(
          `The selected agent is missing required tool(s): ${missingTools.join(', ')}. ` +
            'Enable them in Settings → Agents (and Settings → MCP Tools).'
        );
      }
      const normalizedFolder = (
        selectedStorageProvider === 'local'
          ? formData.folder
          : formData.folder || formData.type_id || editingType?.type_id || 'files'
      )
        .toLowerCase()
        .replace(/[^a-z0-9_]/g, '_');
      const metadata = {
        ...(formData.metadata || {}),
        storage_provider: selectedStorageProvider,
        agent_processing_enabled: agentEnabled,
        agent_definition_id: agentEnabled ? selectedAgentDefinitionId || undefined : undefined,
        agent_name: agentEnabled
          ? (availableAgents.find((item) => item.definition_id === selectedAgentDefinitionId)?.name || undefined)
          : undefined,
      };

      const agentConfig = {
        ...(editingType?.agent_config || {}),
        stages: editingType?.agent_config?.stages || [],
        validation_rules: validationRules,
        post_actions: postActions,
      };

      if (editingType) {
        // Update existing
        const updateData: DocumentTypeUpdateRequest = {
          display_name: formData.display_name,
          description: formData.description || undefined,
          folder: normalizedFolder,
          allowed_extensions: formData.allowed_extensions,
          max_size_mb: formData.max_size_mb,
          is_active: formData.is_active,
          upload_contexts: uploadContexts,
          agent_config: agentConfig,
          metadata,
        };
        await documentTypes.update(editingType.type_id, updateData);
      } else {
        // Create new
        const createData: DocumentTypeCreateRequest = {
          type_id: formData.type_id,
          display_name: formData.display_name,
          description: formData.description || undefined,
          folder: normalizedFolder,
          allowed_extensions: formData.allowed_extensions,
          max_size_mb: formData.max_size_mb,
          is_active: formData.is_active,
          upload_contexts: uploadContexts,
          agent_config: agentConfig,
          metadata,
        };
        await documentTypes.create(createData);
      }

      await fetchDocTypes();
      closeModal();
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Failed to save document type');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (typeId: string) => {
    try {
      setDeleting(true);
      await documentTypes.delete(typeId);
      await fetchDocTypes();
      setDeleteConfirm(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete document type');
    } finally {
      setDeleting(false);
    }
  };

  const handleToggleActive = async (docType: DocumentType) => {
    try {
      await documentTypes.update(docType.type_id, {
        is_active: !docType.is_active,
      });
      await fetchDocTypes();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update document type');
    }
  };

  const handleTogglePreviewThumbnail = async (docType: DocumentType) => {
    const enabling = !docType.is_preview_thumbnail;
    try {
      await documentTypes.update(docType.type_id, {
        is_preview_thumbnail: enabling,
      });
      await fetchDocTypes();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update document type');
    }
  };

  // Track raw input for extensions to allow typing commas
  const [extensionsInput, setExtensionsInput] = useState('');

  const handleExtensionChange = (value: string) => {
    // Store raw input to allow typing freely
    setExtensionsInput(value);

    // Parse comma-separated extensions (filter empty only for storage)
    const extensions = value
      .split(',')
      .map((ext) => ext.trim())
      .filter((ext) => ext.length > 0)
      .map((ext) => (ext.startsWith('.') ? ext : `.${ext}`));

    // Only update formData if we have valid extensions
    if (extensions.length > 0) {
      setFormData({ ...formData, allowed_extensions: extensions });
    }
  };

  // Upload context helpers
  const addUploadContext = () => {
    setUploadContexts([...uploadContexts, { entity_type: '', label: '' }]);
  };

  const updateUploadContext = (index: number, updates: Partial<UploadContextConfig>) => {
    const updated = [...uploadContexts];
    updated[index] = { ...updated[index], ...updates };
    setUploadContexts(updated);
  };

  const removeUploadContext = (index: number) => {
    setUploadContexts(uploadContexts.filter((_, i) => i !== index));
  };

  // Validation rule helpers
  const addValidationRule = () => {
    setValidationRules([...validationRules, { field: '', rule: 'required' }]);
  };

  const updateValidationRule = (index: number, updates: Partial<ValidationRule>) => {
    const updated = [...validationRules];
    updated[index] = { ...updated[index], ...updates };
    setValidationRules(updated);
  };

  const removeValidationRule = (index: number) => {
    setValidationRules(validationRules.filter((_, i) => i !== index));
  };

  // Post-action helpers
  const addPostAction = () => {
    setPostActions([...postActions, { type: 'create_entity' }]);
  };

  const updatePostAction = (index: number, updates: Partial<PostAction>) => {
    const updated = [...postActions];
    updated[index] = { ...updated[index], ...updates };
    setPostActions(updated);
  };

  const removePostAction = (index: number) => {
    setPostActions(postActions.filter((_, i) => i !== index));
  };

  if (loading && docTypes.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 text-cobalt animate-spin" />
      </div>
    );
  }

  if (error && docTypes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <AlertCircle className="w-12 h-12 text-destructive mb-4" />
        <p className="text-destructive mb-4">{error}</p>
        <Button variant="primary"
          onClick={fetchDocTypes}
          className="flex items-center gap-2 px-4 py-2 bg-cobalt text-white rounded-lg hover:bg-cobalt-dark"
        >
          <RefreshCw className="w-4 h-4" />
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium text-foreground">Document Types</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Define file categories users can upload and configure agent-based processing.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            onClick={fetchDocTypes}
            className="flex items-center gap-2 px-3 py-2 text-muted-foreground hover:text-cobalt hover:bg-muted rounded-lg transition-colors"
            title="Reload document types from server"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </Button>
          <Button variant="primary"
            onClick={openCreateModal}
            className="flex items-center gap-2 px-4 py-2 text-white bg-cobalt rounded-lg hover:bg-cobalt-dark transition-colors"
            title="Create a new document type"
          >
            <Plus className="w-4 h-4" />
            Add Type
          </Button>
        </div>
      </div>

      {/* Info Banner */}
      <div className="bg-info-subtle border border-info/30 rounded-lg p-4 flex gap-3">
        <Info className="w-5 h-5 text-info flex-shrink-0 mt-0.5" />
        <div className="text-sm text-info">
          <p className="font-medium mb-1">How document types work</p>
          <ul className="list-disc list-inside space-y-0.5 text-info">
            <li>Each type defines allowed file formats and size limits</li>
            <li>Tag exactly one type as <strong>Preview Thumbnail</strong> — the first image uploaded per entity appears on Kanban cards</li>
            <li>Enable Agent Processing to run a selected agent from the Agents tab</li>
            <li>Inactive types are hidden from upload menus but existing documents remain accessible</li>
          </ul>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-destructive-subtle border border-destructive/30 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-destructive" />
          <p className="text-sm text-destructive">{error}</p>
          <Button variant="primary"
            onClick={() => setError(null)}
            className="ml-auto text-destructive hover:text-destructive"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>
      )}

      {/* Document Types List */}
      {docTypes.length === 0 ? (
        <div className="bg-card rounded-xl border border-border p-8 text-center">
          <FileText className="w-12 h-12 text-muted-foreground/60 mx-auto mb-3" />
          <p className="text-muted-foreground mb-2">No document types configured</p>
          <p className="text-sm text-muted-foreground mb-4">
            Document types define what files can be uploaded and how they're processed.
          </p>
          <Button variant="primary"
            onClick={openCreateModal}
            className="inline-flex items-center gap-2 px-4 py-2 bg-cobalt text-white rounded-lg hover:bg-cobalt-dark"
          >
            <Plus className="w-4 h-4" />
            Add Document Type
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          {docTypes.map((docType) => (
            <div
              key={docType.id}
              className="bg-card rounded-xl border border-border overflow-hidden"
            >
              {/* Type Header */}
              <div className="flex items-center justify-between p-4">
                <div className="flex items-center gap-4">
                  <div
                    className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                      docType.is_active ? 'bg-cobalt/10' : 'bg-muted'
                    }`}
                  >
                    <FileText
                      className={`w-5 h-5 ${
                        docType.is_active ? 'text-cobalt' : 'text-muted-foreground'
                      }`}
                    />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-foreground">{docType.display_name}</h3>
                      <code className="text-xs bg-muted px-2 py-0.5 rounded text-muted-foreground">
                        {docType.type_id}
                      </code>
                      {docType.is_system && (
                        <Badge variant="default" className="bg-warning-subtle text-warning">
                          System
                        </Badge>
                      )}
                      {docType.is_active ? (
                        <Badge variant="success">Active</Badge>
                      ) : (
                        <Badge variant="default">Inactive</Badge>
                      )}
                      {docType.is_preview_thumbnail && (
                        <Badge variant="default" className="bg-cobalt/10 text-cobalt">
                          <Image className="w-3 h-3 mr-1" />
                          Preview Thumbnail
                        </Badge>
                      )}
                      {docType.agent_enabled && (
                        <Badge variant="default" className="bg-purple-100 text-purple-700">
                          <Brain className="w-3 h-3 mr-1" />
                          Agent
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mt-0.5">
                      {docType.description || 'No description'}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {hasImageExtensions(docType) && (
                    <Button
                      variant="ghost"
                      onClick={() => void handleTogglePreviewThumbnail(docType)}
                      className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors flex items-center gap-1.5 ${
                        docType.is_preview_thumbnail
                          ? 'text-cobalt bg-cobalt/10 hover:bg-cobalt/20'
                          : 'text-muted-foreground hover:bg-muted'
                      }`}
                      title={docType.is_preview_thumbnail
                        ? 'Remove preview thumbnail tag (cards will no longer show images)'
                        : 'Tag as preview thumbnail — first upload per entity shows on Kanban cards'}
                    >
                      <Image className="w-3.5 h-3.5" />
                      {docType.is_preview_thumbnail ? 'Thumbnail' : 'Set Thumbnail'}
                    </Button>
                  )}
                  <Button variant="ghost"
                    onClick={() => handleToggleActive(docType)}
                    className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                      docType.is_active
                        ? 'text-muted-foreground hover:bg-muted'
                        : 'text-cobalt hover:bg-cobalt/10'
                    }`}
                    title={docType.is_active
                      ? 'Hide this type from upload menus (existing docs remain)'
                      : 'Show this type in upload menus'}
                  >
                    {docType.is_active ? 'Disable' : 'Enable'}
                  </Button>
                  <Button variant="ghost"
                    onClick={() => openEditModal(docType)}
                    className="p-2 text-muted-foreground hover:text-cobalt hover:bg-muted rounded-lg transition-colors"
                    title="Edit document type settings"
                  >
                    <Edit2 className="w-4 h-4" />
                  </Button>
                  {!docType.is_system && (
                    <Button variant="ghost"
                      onClick={() => setDeleteConfirm(docType.type_id)}
                      className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive-subtle rounded-lg transition-colors"
                      title="Delete this document type permanently"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  )}
                  <Button variant="ghost"
                    onClick={() =>
                      setExpandedConfig(
                        expandedConfig === docType.type_id ? null : docType.type_id
                      )
                    }
                    className="p-2 text-muted-foreground hover:text-muted-foreground hover:bg-muted rounded-lg transition-colors"
                    title={expandedConfig === docType.type_id ? 'Hide details' : 'Show configuration details'}
                  >
                    {expandedConfig === docType.type_id ? (
                      <ChevronUp className="w-4 h-4" />
                    ) : (
                      <ChevronDown className="w-4 h-4" />
                    )}
                  </Button>
                </div>
              </div>

              {/* Expanded Details */}
              {expandedConfig === docType.type_id && (
                <div className="border-t border-border p-4 bg-muted/50 space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                        Storage Provider
                      </span>
                      <p className="text-sm text-foreground mt-1">
                        {formatStorageProviderLabel(
                          typeof docType.metadata?.storage_provider === 'string'
                            ? docType.metadata.storage_provider
                            : 'local'
                        )}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                        Allowed Extensions
                      </span>
                      <p className="text-sm text-foreground mt-1">
                        {docType.allowed_extensions.join(', ')}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                        Max Size
                      </span>
                      <p className="text-sm text-foreground mt-1">{docType.max_size_mb} MB</p>
                    </div>
                  </div>

                  <div>
                    <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                      Storage Path Prefix
                    </span>
                    <p className="text-sm text-foreground mt-1">{docType.folder}/</p>
                  </div>

                  {docType.agent_enabled && (
                    <div>
                      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                        Selected Agent
                      </span>
                      <p className="text-sm text-foreground mt-1">
                        {String(docType.metadata?.agent_name || 'Not configured')}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Create/Edit Modal */}
      <Modal
        open={isModalOpen}
        onClose={closeModal}
        title={editingType ? `Edit ${editingType.display_name}` : 'Add Document Type'}
        size="lg"
      >
        <div className="space-y-4">
          {/* Basic Info */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Type ID <span className="text-destructive">*</span>
                <span title="Unique identifier used internally (cannot be changed after creation)">
                  <HelpCircle className="w-3.5 h-3.5 inline ml-1 text-muted-foreground cursor-help" />
                </span>
              </label>
              <input
                type="text"
                value={formData.type_id}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    type_id: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'),
                  })
                }
                placeholder="e.g., resume, transcript"
                disabled={!!editingType}
                className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-cobalt focus:border-cobalt disabled:bg-muted disabled:cursor-not-allowed"
              />
              <p className="text-xs text-muted-foreground mt-1">Lowercase letters, numbers, underscores</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Display Name <span className="text-destructive">*</span>
              </label>
              <input
                type="text"
                value={formData.display_name}
                onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                placeholder="e.g., Resume, Interview Transcript"
                className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-cobalt focus:border-cobalt"
              />
              <p className="text-xs text-muted-foreground mt-1">Shown to users in upload menus</p>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground mb-1">
              Description
            </label>
            <input
              type="text"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="e.g., Candidate's professional resume in PDF format"
              className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-cobalt focus:border-cobalt"
            />
          </div>

          {/* File Settings */}
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Storage Provider <span className="text-destructive">*</span>
                <span title="Provider used for storing this file type">
                  <HelpCircle className="w-3.5 h-3.5 inline ml-1 text-muted-foreground cursor-help" />
                </span>
              </label>
              <select
                value={selectedStorageProvider}
                onChange={(e) => setSelectedStorageProvider(e.target.value)}
                className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-cobalt focus:border-cobalt"
              >
                {storageProviderOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground mt-1">
                {storageProviderOptions.length === 1 && storageProviderOptions[0].value === 'local'
                  ? 'No cloud storage integration configured; using local storage.'
                  : 'Configured storage providers from Integrations.'}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Allowed Extensions <span className="text-destructive">*</span>
              </label>
              <input
                type="text"
                value={extensionsInput}
                onChange={(e) => handleExtensionChange(e.target.value)}
                placeholder=".pdf, .doc, .txt"
                className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-cobalt focus:border-cobalt"
              />
              <p className="text-xs text-muted-foreground mt-1">Comma-separated (e.g., .pdf, .docx)</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Max Size (MB)
              </label>
              <input
                type="number"
                value={formData.max_size_mb}
                onChange={(e) =>
                  setFormData({ ...formData, max_size_mb: parseInt(e.target.value) || 10 })
                }
                min={1}
                max={100}
                className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-cobalt focus:border-cobalt"
              />
              <p className="text-xs text-muted-foreground mt-1">Files larger than this will be rejected</p>
            </div>
          </div>

          {selectedStorageProvider === 'local' && (
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Local Storage Folder <span className="text-destructive">*</span>
                <span title="Subdirectory where local files of this type are stored">
                  <HelpCircle className="w-3.5 h-3.5 inline ml-1 text-muted-foreground cursor-help" />
                </span>
              </label>
              <input
                type="text"
                value={formData.folder}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    folder: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'),
                  })
                }
                placeholder="e.g., resumes, transcripts"
                className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-cobalt focus:border-cobalt"
              />
            </div>
          )}

          {/* Agent Processing */}
          <div className="border-t border-border pt-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Brain className="w-5 h-5 text-purple-600" />
                <span className="font-medium text-foreground">Agent Processing</span>
                <Badge variant="cobalt">Recommended</Badge>
              </div>
              <label className="relative inline-flex items-center cursor-pointer" title="Enable intelligent agent with tool access for document processing">
                <input
                  type="checkbox"
                  checked={agentEnabled}
                  onChange={(e) => setAgentEnabled(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-accent peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-card after:border-border after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
              </label>
            </div>
            <p className="text-xs text-muted-foreground mb-4">
              Select one active agent from the Agents tab. That agent will run for uploaded files of this type.
            </p>

            {agentEnabled && (
              <div className="bg-muted rounded-lg p-4 border border-border">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">
                    Agent <span className="text-destructive">*</span>
                    <span title="Active agents configured in Settings -> Agents">
                      <HelpCircle className="w-3.5 h-3.5 inline ml-1 text-muted-foreground cursor-help" />
                    </span>
                  </label>
                  <select
                    value={selectedAgentDefinitionId}
                    onChange={(e) => setSelectedAgentDefinitionId(e.target.value)}
                    className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:ring-2 focus:ring-cobalt focus:border-cobalt text-sm"
                  >
                    <option value="">Select agent...</option>
                    {availableAgents.map((item) => (
                      <option key={item.definition_id} value={item.definition_id}>
                        {item.display_name} ({item.name})
                      </option>
                    ))}
                  </select>
                  {availableAgents.length === 0 && (
                    <p className="text-xs text-warning mt-1">
                      No active agents found. Configure and activate at least one in Settings → Agents.
                    </p>
                  )}
                  {selectedAgentDefinitionId && missingTools.length > 0 && (
                    <p className="text-xs text-destructive mt-1">
                      This agent is missing required tool(s): {missingTools.join(', ')}. Enable them for
                      the agent in Settings → Agents (and in Settings → MCP Tools).
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Upload Contexts */}
          <div className="border-t border-border pt-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="font-medium text-foreground">Upload Contexts</span>
                <span title="Define where this document type can be uploaded (which entity types)">
                  <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                </span>
              </div>
              <Button variant="ghost"
                type="button"
                onClick={addUploadContext}
                className="text-sm text-cobalt hover:underline flex items-center gap-1"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Context
              </Button>
            </div>
            <p className="text-xs text-muted-foreground mb-3">
              Specify which entity types this document can be attached to.
            </p>

            {uploadContexts.length === 0 ? (
              <div className="text-sm text-muted-foreground bg-muted/50 rounded-lg p-3 text-center">
                No upload contexts defined. Document can be uploaded to any entity.
              </div>
            ) : (
              <div className="space-y-2">
                {uploadContexts.map((ctx, index) => (
                  <div key={index} className="flex items-center gap-2 bg-muted/50 rounded-lg p-2">
                    <select
                      value={ctx.entity_type}
                      onChange={(e) => updateUploadContext(index, { entity_type: e.target.value })}
                      className="flex-1 px-2 py-1.5 text-sm border border-border rounded focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                    >
                      <option value="">Select entity type...</option>
                      {entityTypeOptions}
                    </select>
                    <input
                      type="text"
                      value={ctx.label || ''}
                      onChange={(e) => updateUploadContext(index, { label: e.target.value })}
                      placeholder="Label (optional)"
                      className="flex-1 px-2 py-1.5 text-sm border border-border rounded focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                    />
                    <Button variant="primary"
                      type="button"
                      onClick={() => removeUploadContext(index)}
                      className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive-subtle rounded"
                    >
                      <X className="w-4 h-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Validation Rules */}
          {agentEnabled && (
            <div className="border-t border-border pt-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-foreground">Validation Rules</span>
                  <span title="Rules to validate extracted data before processing">
                    <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                  </span>
                </div>
                <Button variant="ghost"
                  type="button"
                  onClick={addValidationRule}
                  className="text-sm text-cobalt hover:underline flex items-center gap-1"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add Rule
                </Button>
              </div>
              <p className="text-xs text-muted-foreground mb-3">
                Validate extracted fields (e.g., require email, check phone format).
              </p>

              {validationRules.length === 0 ? (
                <div className="text-sm text-muted-foreground bg-muted/50 rounded-lg p-3 text-center">
                  No validation rules. Extracted data will be accepted as-is.
                </div>
              ) : (
                <div className="space-y-2">
                  {validationRules.map((rule, index) => (
                    <div key={index} className="flex items-center gap-2 bg-muted/50 rounded-lg p-2">
                      <input
                        type="text"
                        value={rule.field}
                        onChange={(e) => updateValidationRule(index, { field: e.target.value })}
                        placeholder="Field name (e.g., email)"
                        className="flex-1 px-2 py-1.5 text-sm border border-border rounded focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                      />
                      <select
                        value={rule.rule}
                        onChange={(e) => updateValidationRule(index, { rule: e.target.value })}
                        className="w-32 px-2 py-1.5 text-sm border border-border rounded focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                      >
                        <option value="required">Required</option>
                        <option value="email">Email</option>
                        <option value="phone">Phone</option>
                        <option value="min_length">Min Length</option>
                        <option value="max_length">Max Length</option>
                      </select>
                      <Button variant="primary"
                        type="button"
                        onClick={() => removeValidationRule(index)}
                        className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive-subtle rounded"
                      >
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Post-Actions */}
          {agentEnabled && (
            <div className="border-t border-border pt-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-foreground">Post-Actions</span>
                  <span title="Actions to execute after successful extraction (create entities, run playbooks, etc.)">
                    <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                  </span>
                </div>
                <Button variant="ghost"
                  type="button"
                  onClick={addPostAction}
                  className="text-sm text-cobalt hover:underline flex items-center gap-1"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add Action
                </Button>
              </div>
              <p className="text-xs text-muted-foreground mb-3">
                Automatically create entities or trigger workflows after extraction.
              </p>

              {postActions.length === 0 ? (
                <div className="text-sm text-muted-foreground bg-muted/50 rounded-lg p-3 text-center">
                  No post-actions. Extracted data will only be stored with the document.
                </div>
              ) : (
                <div className="space-y-2">
                  {postActions.map((action, index) => (
                    <div key={index} className="flex items-center gap-2 bg-muted/50 rounded-lg p-2">
                      <select
                        value={action.type}
                        onChange={(e) => updatePostAction(index, { type: e.target.value })}
                        className="w-40 px-2 py-1.5 text-sm border border-border rounded focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                      >
                        <option value="create_entity">Create Entity</option>
                        <option value="update_entity">Update Entity</option>
                        <option value="find_or_create">Find or Create</option>
                        <option value="link_entity">Link Entity</option>
                        <option value="run_playbook">Run Playbook</option>
                      </select>
                      {(action.type === 'create_entity' || action.type === 'find_or_create') && (
                        <select
                          value={action.entity_type || ''}
                          onChange={(e) => updatePostAction(index, { entity_type: e.target.value })}
                          className="flex-1 px-2 py-1.5 text-sm border border-border rounded focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                        >
                          <option value="">Select entity type...</option>
                          {entityTypeOptions}
                        </select>
                      )}
                      {action.type === 'run_playbook' && (
                        <input
                          type="text"
                          value={action.playbook_id || ''}
                          onChange={(e) => updatePostAction(index, { playbook_id: e.target.value })}
                          placeholder="Playbook ID"
                          className="flex-1 px-2 py-1.5 text-sm border border-border rounded focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                        />
                      )}
                      <Button variant="primary"
                        type="button"
                        onClick={() => removePostAction(index)}
                        className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive-subtle rounded"
                      >
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Status */}
          <div className="flex items-center gap-2 border-t border-border pt-4">
            <input
              type="checkbox"
              checked={formData.is_active}
              onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              className="w-4 h-4 text-cobalt border-border rounded focus:ring-cobalt"
            />
            <span className="text-sm text-foreground">Active (users can upload this type)</span>
          </div>

          {/* Modal Error */}
          {modalError && (
            <div className="flex items-center gap-2 bg-destructive-subtle border border-destructive/30 rounded-lg px-3 py-2 text-sm text-destructive">
              <AlertCircle className="w-4 h-4 shrink-0 text-destructive" />
              <span className="flex-1">{modalError}</span>
              <button onClick={() => setModalError(null)} className="text-destructive hover:text-destructive">
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4 border-t border-border">
            <Button variant="ghost"
              onClick={closeModal}
              className="px-4 py-2 text-sm font-medium text-foreground hover:bg-muted rounded-lg transition-colors"
            >
              Cancel
            </Button>
            <Button variant="primary"
              onClick={handleSave}
              disabled={
                !formData.type_id ||
                !formData.display_name ||
                (selectedStorageProvider === 'local' && !formData.folder) ||
                (agentEnabled && !selectedAgentDefinitionId) ||
                (agentEnabled && missingTools.length > 0) ||
                formData.allowed_extensions.length === 0 ||
                saving
              }
              className="px-4 py-2 text-sm font-medium text-white bg-cobalt rounded-lg hover:bg-cobalt-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
                  Saving...
                </>
              ) : editingType ? (
                'Update'
              ) : (
                'Create'
              )}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        open={deleteConfirm !== null}
        onClose={() => setDeleteConfirm(null)}
        title="Delete Document Type"
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete this document type? This action cannot be undone.
            Existing documents of this type will not be affected, but new uploads will not be
            allowed.
          </p>
          <div className="flex justify-end gap-3">
            <Button variant="primary"
              onClick={() => setDeleteConfirm(null)}
              className="px-4 py-2 text-sm font-medium text-foreground hover:bg-muted rounded-lg transition-colors"
            >
              Cancel
            </Button>
            <Button variant="danger"
              onClick={() => deleteConfirm && handleDelete(deleteConfirm)}
              disabled={deleting}
              className="px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
            >
              {deleting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
                  Deleting...
                </>
              ) : (
                'Delete'
              )}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
