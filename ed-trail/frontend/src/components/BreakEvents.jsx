/**
 * ED-TRAIL Break Events Component
 */

import { useState, useEffect } from 'react';
import { fetchBreakEvents } from '../hooks/useTrailApi';

export function BreakEventsList({ teamId }) {
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState({ status: '', severity: '' });

    useEffect(() => {
        if (!teamId) return;

        setLoading(true);
        fetchBreakEvents(teamId, filter)
            .then(setEvents)
            .catch(console.error)
            .finally(() => setLoading(false));
    }, [teamId, filter.status, filter.severity]);

    if (loading) return <div className="card">Loading break events...</div>;

    return (
        <div className="card">
            <h2>Break Events ({events.length})</h2>

            <div style={{ marginBottom: '1rem', display: 'flex', gap: '1rem' }}>
                <select
                    value={filter.status}
                    onChange={e => setFilter(f => ({ ...f, status: e.target.value }))}
                    style={{ padding: '0.25rem', background: 'var(--color-bg)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
                >
                    <option value="">All Status</option>
                    <option value="open">Open</option>
                    <option value="resolved">Resolved</option>
                </select>

                <select
                    value={filter.severity}
                    onChange={e => setFilter(f => ({ ...f, severity: e.target.value }))}
                    style={{ padding: '0.25rem', background: 'var(--color-bg)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
                >
                    <option value="">All Severity</option>
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                </select>
            </div>

            {events.length === 0 ? (
                <p style={{ color: 'var(--color-text-muted)' }}>No break events found</p>
            ) : (
                <table>
                    <thead>
                        <tr>
                            <th>Title</th>
                            <th>Type</th>
                            <th>Severity</th>
                            <th>Status</th>
                            <th>Impact</th>
                            <th>Detected</th>
                        </tr>
                    </thead>
                    <tbody>
                        {events.map(event => (
                            <tr key={event.id}>
                                <td>{event.title}</td>
                                <td>{event.break_type}</td>
                                <td className={`severity-${event.severity}`}>{event.severity}</td>
                                <td className={`status-${event.status}`}>{event.status}</td>
                                <td className="amount">{event.impact_amount_display || '-'}</td>
                                <td>{new Date(event.detected_at).toLocaleDateString()}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}
