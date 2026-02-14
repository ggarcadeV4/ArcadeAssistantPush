export class HttpError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export const errors = {
  badRequest: (msg, details) => new HttpError(400, 'BAD_REQUEST', msg, details),
  unauthorized: (msg = 'Missing or invalid credentials') => new HttpError(401, 'UNAUTHORIZED', msg),
  rateLimited: (msg, retryAfterMs) => new HttpError(429, 'RATE_LIMITED', msg, { retry_after_ms: retryAfterMs }),
  providerError: (msg, requestId) => new HttpError(500, 'PROVIDER_ERROR', msg, { request_id: requestId }),
  notConfigured: (provider) => new HttpError(501, 'NOT_CONFIGURED', `${provider} not configured`),
};

export function toJson(err) {
  const body = { code: err.code || 'PROVIDER_ERROR', message: err.message };
  if (err.details) Object.assign(body, err.details);
  return { status: err.status || 500, body };
}

