/** Static option lists for the connector request configuration. */

export const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const;
export const AUTH_TYPES = ['none', 'bearer', 'api_key', 'basic', 'custom'] as const;
export const CONTENT_TYPES = ['application/json', 'application/x-www-form-urlencoded', 'raw'] as const;

/** The content type that switches the body editor to a free-form raw payload. */
export const RAW = 'raw';
