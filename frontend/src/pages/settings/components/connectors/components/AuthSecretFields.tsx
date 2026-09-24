import Field, { inputClass } from './Field';

interface AuthSecretFieldsProps {
  authType: string;
  secrets: Record<string, string>;
  setSecret: (key: string, value: string) => void;
  apiKeyHeader: string;
  setApiKeyHeader: (value: string) => void;
  apiKeyIn: 'header' | 'query';
  setApiKeyIn: (value: 'header' | 'query') => void;
  isEditing: boolean;
}

/** Renders the secret + auth-config inputs for the selected auth type. */
export default function AuthSecretFields({
  authType,
  secrets,
  setSecret,
  apiKeyHeader,
  setApiKeyHeader,
  apiKeyIn,
  setApiKeyIn,
  isEditing,
}: AuthSecretFieldsProps) {
  if (authType === 'none' || authType === 'custom') return null;
  const placeholder = isEditing ? 'Leave blank to keep current secret' : '';
  const secretInput = (key: string, label: string) => (
    <Field label={label}>
      <input
        type="password"
        value={secrets[key] ?? ''}
        onChange={(e) => setSecret(key, e.target.value)}
        className={inputClass}
        placeholder={placeholder}
        autoComplete="new-password"
      />
    </Field>
  );
  return (
    <div className="grid grid-cols-2 gap-3 rounded-lg border border-dashed border-border p-3">
      {authType === 'bearer' && secretInput('token', 'Bearer token')}
      {authType === 'basic' && secretInput('username', 'Username')}
      {authType === 'basic' && secretInput('password', 'Password')}
      {authType === 'api_key' && secretInput('api_key', 'API key')}
      {authType === 'api_key' && (
        <Field label="Send as">
          <select
            value={apiKeyIn}
            onChange={(e) => setApiKeyIn(e.target.value as 'header' | 'query')}
            className={inputClass}
          >
            <option value="header">Header</option>
            <option value="query">Query param</option>
          </select>
        </Field>
      )}
      {authType === 'api_key' && (
        <Field label={apiKeyIn === 'query' ? 'Param name' : 'Header name'}>
          <input
            value={apiKeyHeader}
            onChange={(e) => setApiKeyHeader(e.target.value)}
            className={inputClass}
          />
        </Field>
      )}
    </div>
  );
}
