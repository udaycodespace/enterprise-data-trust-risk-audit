/**
 * ED-BASE App Component
 * 
 * Root application component with minimal UI skeleton.
 * No business logic - only security foundation demonstration.
 */

import { useAuth } from './hooks/useAuth';

function App() {
    const { user, loading, isAuthenticated, logout } = useAuth();

    if (loading) {
        return (
            <div className="container">
                <div className="card">
                    <p>Loading...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="container">
            <div className="card">
                <h1>ED-BASE</h1>
                <p style={{ color: 'var(--color-text-muted)', marginTop: '0.5rem' }}>
                    Enterprise Security Foundation
                </p>

                <div style={{ marginTop: '2rem' }}>
                    {isAuthenticated ? (
                        <>
                            <p className="success">✓ Authenticated</p>
                            <p style={{ marginTop: '0.5rem' }}>
                                User ID: {user?.id}
                            </p>
                            <button
                                className="btn btn-primary"
                                onClick={logout}
                                style={{ marginTop: '1rem' }}
                            >
                                Logout
                            </button>
                        </>
                    ) : (
                        <>
                            <p className="error">Not authenticated</p>
                            <p style={{ marginTop: '0.5rem', color: 'var(--color-text-muted)' }}>
                                Use the API to authenticate.
                            </p>
                        </>
                    )}
                </div>

                <div style={{ marginTop: '2rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)' }}>
                    <h3>Security Features</h3>
                    <ul style={{ marginTop: '0.5rem', paddingLeft: '1.5rem', color: 'var(--color-text-muted)' }}>
                        <li>Session revocation on every request</li>
                        <li>Token refresh singleton</li>
                        <li>Rate limit handling (429 retry)</li>
                        <li>Idempotency key injection</li>
                        <li>Request ID tracking</li>
                    </ul>
                </div>
            </div>
        </div>
    );
}

export default App;
