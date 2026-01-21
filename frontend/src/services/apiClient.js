/**
 * ED-BASE API Client
 * 
 * Fetch wrapper with:
 * - Automatic token injection
 * - 401 handling with token refresh
 * - 429 handling with retry
 * - Request ID tracking
 * - Idempotency key injection for mutations
 */

import { tokenRefreshManager } from './tokenRefresh';

const API_URL = import.meta.env.VITE_API_URL || '';

// Generate unique idempotency key
function generateIdempotencyKey() {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

// Generate request ID for tracking
function generateRequestId() {
    return `req-${Date.now()}-${Math.random().toString(36).substr(2, 6)}`;
}

class ApiClient {
    constructor() {
        this.accessToken = null;
        this.onLogout = null;
    }

    /**
     * Set access token for API calls.
     */
    setAccessToken(token) {
        this.accessToken = token;
    }

    /**
     * Set logout callback.
     */
    setLogoutHandler(handler) {
        this.onLogout = handler;
    }

    /**
     * Build headers for request.
     */
    buildHeaders(options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            'X-Request-ID': generateRequestId(),
            ...options.headers,
        };

        if (this.accessToken) {
            headers['Authorization'] = `Bearer ${this.accessToken}`;
        }

        // Add idempotency key for mutations
        if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(options.method)) {
            if (!headers['Idempotency-Key']) {
                headers['Idempotency-Key'] = generateIdempotencyKey();
            }
        }

        return headers;
    }

    /**
     * Handle 401 response with token refresh.
     */
    async handle401(originalRequest) {
        try {
            const newToken = await tokenRefreshManager.refresh(
                async (refreshToken) => {
                    const response = await fetch(`${API_URL}/api/auth/refresh`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ refresh_token: refreshToken }),
                    });

                    if (!response.ok) {
                        throw new Error('Refresh failed');
                    }

                    return response.json();
                },
                () => {
                    // Force logout on refresh failure
                    if (this.onLogout) {
                        this.onLogout();
                    }
                }
            );

            // Update stored token
            this.accessToken = newToken;

            // Retry original request with new token
            return this.request(originalRequest.url, {
                ...originalRequest.options,
                headers: {
                    ...originalRequest.options.headers,
                    'Authorization': `Bearer ${newToken}`,
                },
            });

        } catch (error) {
            throw error;
        }
    }

    /**
     * Handle 429 response with retry.
     */
    async handle429(response, originalRequest, retryCount = 0) {
        const maxRetries = 3;

        if (retryCount >= maxRetries) {
            throw new Error('Rate limit exceeded after retries');
        }

        // Get retry delay from header or default
        const retryAfter = parseInt(response.headers.get('Retry-After') || '5', 10);
        const delayMs = retryAfter * 1000;

        // Wait before retry
        await new Promise(resolve => setTimeout(resolve, delayMs));

        // Retry request
        return this.request(originalRequest.url, originalRequest.options, retryCount + 1);
    }

    /**
     * Make API request.
     */
    async request(url, options = {}, retryCount = 0) {
        const fullUrl = url.startsWith('http') ? url : `${API_URL}${url}`;
        const headers = this.buildHeaders(options);

        const requestInfo = { url, options: { ...options, headers } };

        try {
            const response = await fetch(fullUrl, {
                ...options,
                headers,
            });

            // Handle 401 - try refresh
            if (response.status === 401) {
                return this.handle401(requestInfo);
            }

            // Handle 429 - retry with backoff
            if (response.status === 429) {
                return this.handle429(response, requestInfo, retryCount);
            }

            // Parse response
            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                const error = new Error(data.error || 'Request failed');
                error.code = data.code;
                error.status = response.status;
                error.requestId = data.request_id;
                throw error;
            }

            return data;

        } catch (error) {
            // Network errors
            if (error.name === 'TypeError') {
                throw new Error('Network error - please check your connection');
            }
            throw error;
        }
    }

    // Convenience methods
    get(url, options = {}) {
        return this.request(url, { ...options, method: 'GET' });
    }

    post(url, data, options = {}) {
        return this.request(url, {
            ...options,
            method: 'POST',
            body: JSON.stringify(data),
        });
    }

    put(url, data, options = {}) {
        return this.request(url, {
            ...options,
            method: 'PUT',
            body: JSON.stringify(data),
        });
    }

    delete(url, options = {}) {
        return this.request(url, { ...options, method: 'DELETE' });
    }
}

// Singleton instance
export const apiClient = new ApiClient();
