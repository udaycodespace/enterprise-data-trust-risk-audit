/**
 * ED-TRAIL Lineage Graph Component
 */

import { useState, useEffect } from 'react';
import { fetchAssetLineage, fetchDataAssets } from '../hooks/useTrailApi';

export function LineageGraph({ teamId, assetId }) {
    const [upstream, setUpstream] = useState([]);
    const [downstream, setDownstream] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!teamId || !assetId) return;

        async function load() {
            setLoading(true);
            setError(null);
            try {
                const [up, down] = await Promise.all([
                    fetchAssetLineage(teamId, assetId, 'upstream'),
                    fetchAssetLineage(teamId, assetId, 'downstream'),
                ]);
                setUpstream(up);
                setDownstream(down);
            } catch (e) {
                setError(e.message);
            } finally {
                setLoading(false);
            }
        }

        load();
    }, [teamId, assetId]);

    if (loading) return <div className="card">Loading lineage...</div>;
    if (error) return <div className="card" style={{ color: 'var(--color-error)' }}>Error: {error}</div>;

    return (
        <div className="card">
            <h2>Lineage Graph</h2>
            <p style={{ color: 'var(--color-text-muted)', marginBottom: '1rem' }}>Asset: {assetId}</p>

            <div style={{ marginBottom: '1rem' }}>
                <h3 style={{ fontSize: '0.875rem', marginBottom: '0.5rem' }}>↑ Upstream ({upstream.length})</h3>
                {upstream.length === 0 ? (
                    <p style={{ color: 'var(--color-text-muted)' }}>No upstream dependencies</p>
                ) : (
                    upstream.map(edge => (
                        <div key={edge.id} className="node">
                            <div>{edge.source_asset_id}</div>
                            <div className="edge">→ {edge.edge_type} → {edge.target_asset_id}</div>
                            {edge.is_validated && <span style={{ color: 'var(--color-success)' }}>✓ Validated</span>}
                        </div>
                    ))
                )}
            </div>

            <div>
                <h3 style={{ fontSize: '0.875rem', marginBottom: '0.5rem' }}>↓ Downstream ({downstream.length})</h3>
                {downstream.length === 0 ? (
                    <p style={{ color: 'var(--color-text-muted)' }}>No downstream dependents</p>
                ) : (
                    downstream.map(edge => (
                        <div key={edge.id} className="node">
                            <div>{edge.source_asset_id}</div>
                            <div className="edge">→ {edge.edge_type} → {edge.target_asset_id}</div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}

export function AssetList({ teamId, onSelectAsset }) {
    const [assets, setAssets] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!teamId) return;
        fetchDataAssets(teamId)
            .then(setAssets)
            .catch(console.error)
            .finally(() => setLoading(false));
    }, [teamId]);

    if (loading) return <div className="card">Loading assets...</div>;

    return (
        <div className="card">
            <h2>Data Assets ({assets.length})</h2>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Origin</th>
                    </tr>
                </thead>
                <tbody>
                    {assets.map(asset => (
                        <tr key={asset.id} onClick={() => onSelectAsset(asset.id)} style={{ cursor: 'pointer' }}>
                            <td>{asset.name}</td>
                            <td>{asset.asset_type}</td>
                            <td>{asset.origin_unknown ? '⚠ Unknown' : '✓ Known'}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
