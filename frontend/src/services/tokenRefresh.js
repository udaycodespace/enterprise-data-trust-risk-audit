/**
 * ED-BASE Token Refresh Singleton
 * 
 * WHY singleton: Prevents concurrent refresh calls that could
 * invalidate tokens mid-flight. All pending requests wait for
 * a single refresh operation.
 */

class TokenRefreshManager {
    constructor() {
        this.isRefreshing = false;
        this.pendingRequests = [];
        this.refreshToken = null;
    }

    /**
     * Set the current refresh token.
     */
    setRefreshToken(token) {
        this.refreshToken = token;
    }

    /**
     * Get the current refresh token.
     */
    getRefreshToken() {
        return this.refreshToken;
    }

    /**
     * Clear tokens on logout.
     */
    clearTokens() {
        this.refreshToken = null;
        this.pendingRequests = [];
        this.isRefreshing = false;
    }

    /**
     * Queue a request to wait for token refresh.
     * 
     * Returns a promise that resolves with new access token
     * or rejects on refresh failure.
     */
    queueRequest() {
        return new Promise((resolve, reject) => {
            this.pendingRequests.push({ resolve, reject });
        });
    }

    /**
     * Resolve all pending requests with new token.
     */
    resolvePending(accessToken) {
        this.pendingRequests.forEach(({ resolve }) => {
            resolve(accessToken);
        });
        this.pendingRequests = [];
    }

    /**
     * Reject all pending requests on refresh failure.
     */
    rejectPending(error) {
        this.pendingRequests.forEach(({ reject }) => {
            reject(error);
        });
        this.pendingRequests = [];
    }

    /**
     * Perform token refresh.
     * 
     * WHY singleton pattern: If multiple requests fail with 401
     * simultaneously, we only make ONE refresh call. All other
     * requests wait for that single refresh to complete.
     * 
     * @param {Function} refreshFn - Async function to call refresh API
     * @param {Function} onLogout - Called if refresh fails (force logout)
     * @returns {Promise<string>} New access token
     */
    async refresh(refreshFn, onLogout) {
        // If already refreshing, queue this request
        if (this.isRefreshing) {
            return this.queueRequest();
        }

        // Check if we have a refresh token
        if (!this.refreshToken) {
            onLogout();
            throw new Error('No refresh token available');
        }

        this.isRefreshing = true;

        try {
            // Call the refresh API
            const result = await refreshFn(this.refreshToken);

            if (!result.access_token) {
                throw new Error('No access token in response');
            }

            // Update stored refresh token if rotated
            if (result.refresh_token) {
                this.refreshToken = result.refresh_token;
            }

            // Resolve all pending requests
            this.resolvePending(result.access_token);

            return result.access_token;

        } catch (error) {
            // Refresh failed - force logout
            this.rejectPending(error);
            onLogout();
            throw error;

        } finally {
            this.isRefreshing = false;
        }
    }
}

// Singleton instance
export const tokenRefreshManager = new TokenRefreshManager();
