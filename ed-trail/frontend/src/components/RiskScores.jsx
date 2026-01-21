/**
 * ED-TRAIL Risk Scores Component
 */

import { useState, useEffect } from 'react';
import { fetchHighRiskAssets } from '../hooks/useTrailApi';
import { formatScore } from '../utils/currency';

export function RiskScoresList({ teamId }) {
    const [scores, setScores] = useState([]);
    const [loading, setLoading] = useState(true);
    const [minScore, setMinScore] = useState(50);

    useEffect(() => {
        if (!teamId) return;

        setLoading(true);
        fetchHighRiskAssets(teamId, minScore)
            .then(setScores)
            .catch(console.error)
            .finally(() => setLoading(false));
    }, [teamId, minScore]);

    if (loading) return <div className="card">Loading risk scores...</div>;

    return (
        <div className="card">
            <h2>High Risk Assets ({scores.length})</h2>

            <div style={{ marginBottom: '1rem' }}>
                <label style={{ marginRight: '0.5rem' }}>Min Score:</label>
                <input
                    type="range"
                    min="0"
                    max="100"
                    value={minScore}
                    onChange={e => setMinScore(Number(e.target.value))}
                    style={{ verticalAlign: 'middle' }}
                />
                <span style={{ marginLeft: '0.5rem' }}>{minScore}</span>
            </div>

            {scores.length === 0 ? (
                <p style={{ color: 'var(--color-text-muted)' }}>No assets above threshold</p>
            ) : (
                <table>
                    <thead>
                        <tr>
                            <th>Asset ID</th>
                            <th>Score</th>
                            <th>Change</th>
                            <th>Exposure</th>
                        </tr>
                    </thead>
                    <tbody>
                        {scores.map(score => {
                            const { class: scoreClass } = formatScore(score.overall_score);
                            return (
                                <tr key={score.asset_id}>
                                    <td style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>
                                        {score.asset_id.slice(0, 8)}...
                                    </td>
                                    <td>
                                        <span className={`score ${scoreClass}`}>{score.overall_score}</span>
                                    </td>
                                    <td style={{ color: score.score_change > 0 ? 'var(--color-error)' : 'var(--color-success)' }}>
                                        {score.score_change > 0 ? '+' : ''}{score.score_change || 0}
                                    </td>
                                    <td className="amount">{score.exposure_display || '-'}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            )}
        </div>
    );
}
