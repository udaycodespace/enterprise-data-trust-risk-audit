/**
 * ED-BASE Auth Provider
 * 
 * React context for authentication state with Supabase integration.
 */

import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { createClient } from '@supabase/supabase-js';
import { apiClient } from '../services/apiClient';
import { tokenRefreshManager } from '../services/tokenRefresh';

const AuthContext = createContext(null);

// Initialize Supabase client
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
const supabase = supabaseUrl && supabaseAnonKey
    ? createClient(supabaseUrl, supabaseAnonKey)
    : null;

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [session, setSession] = useState(null);
    const [loading, setLoading] = useState(true);

    /**
     * Handle logout - clear all state.
     */
    const logout = useCallback(async () => {
        try {
            // Call backend logout
            await apiClient.post('/api/auth/logout', {});
        } catch (error) {
            // Ignore errors - we're logging out anyway
        }

        // Clear local state
        setUser(null);
        setSession(null);
        apiClient.setAccessToken(null);
        tokenRefreshManager.clearTokens();

        // Clear Supabase session
        if (supabase) {
            await supabase.auth.signOut();
        }
    }, []);

    /**
     * Handle session update.
     */
    const updateSession = useCallback((newSession) => {
        setSession(newSession);

        if (newSession) {
            apiClient.setAccessToken(newSession.access_token);
            tokenRefreshManager.setRefreshToken(newSession.refresh_token);
        } else {
            apiClient.setAccessToken(null);
            tokenRefreshManager.clearTokens();
        }
    }, []);

    /**
     * Login with email/password.
     */
    const login = useCallback(async (email, password) => {
        const response = await apiClient.post('/api/auth/login', {
            email,
            password,
        });

        updateSession({
            access_token: response.access_token,
            refresh_token: response.refresh_token,
        });

        setUser({ id: response.user_id, email });
        return response;
    }, [updateSession]);

    /**
     * Change password (revokes all sessions).
     */
    const changePassword = useCallback(async (newPassword) => {
        const response = await apiClient.put('/api/auth/password', {
            new_password: newPassword,
        });

        // Force logout after password change
        await logout();

        return response;
    }, [logout]);

    // Set up logout handler for API client
    useEffect(() => {
        apiClient.setLogoutHandler(logout);
    }, [logout]);

    // Check for existing session on mount
    useEffect(() => {
        const initAuth = async () => {
            try {
                if (supabase) {
                    const { data: { session } } = await supabase.auth.getSession();
                    if (session) {
                        updateSession(session);
                        setUser(session.user);
                    }
                }
            } catch (error) {
                console.error('Auth init error:', error);
            } finally {
                setLoading(false);
            }
        };

        initAuth();
    }, [updateSession]);

    // Listen for Supabase auth changes
    useEffect(() => {
        if (!supabase) return;

        const { data: { subscription } } = supabase.auth.onAuthStateChange(
            async (event, session) => {
                if (event === 'SIGNED_OUT') {
                    setUser(null);
                    updateSession(null);
                } else if (session) {
                    setUser(session.user);
                    updateSession(session);
                }
            }
        );

        return () => subscription.unsubscribe();
    }, [updateSession]);

    const value = {
        user,
        session,
        loading,
        isAuthenticated: !!user,
        login,
        logout,
        changePassword,
    };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
}

/**
 * Hook to access auth context.
 */
export function useAuth() {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within AuthProvider');
    }
    return context;
}
