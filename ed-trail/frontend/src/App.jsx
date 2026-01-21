/**
 * ED-TRAIL App Component
 */

import { useState } from 'react';
import { AssetList, LineageGraph } from './components/LineageGraph';
import { BreakEventsList } from './components/BreakEvents';
import { RiskScoresList } from './components/RiskScores';

function App() {
    const [activeTab, setActiveTab] = useState('lineage');
    const [selectedAsset, setSelectedAsset] = useState(null);

    // In production, get from ED-BASE auth context
    const teamId = 'demo-team-id';

    const tabs = [
        { id: 'lineage', label: 'Lineage' },
        { id: 'breaks', label: 'Break Events' },
        { id: 'risk', label: 'Risk Scores' },
    ];

    return (
        <div className="container">
            <header style={{ marginBottom: '1rem' }}>
                <h1>ED-TRAIL</h1>
                <p style={{ color: 'var(--color-text-muted)' }}>Data Lineage & Integrity</p>
            </header>

            <nav style={{ marginBottom: '1rem', display: 'flex', gap: '0.5rem' }}>
                {tabs.map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        style={{
                            padding: '0.5rem 1rem',
                            background: activeTab === tab.id ? 'var(--color-primary)' : 'var(--color-surface)',
                            border: '1px solid var(--color-border)',
                            borderRadius: '4px',
                            color: 'var(--color-text)',
                            cursor: 'pointer',
                        }}
                    >
                        {tab.label}
                    </button>
                ))}
            </nav>

            {activeTab === 'lineage' && (
                <div className="grid">
                    <AssetList teamId={teamId} onSelectAsset={setSelectedAsset} />
                    {selectedAsset && <LineageGraph teamId={teamId} assetId={selectedAsset} />}
                </div>
            )}

            {activeTab === 'breaks' && <BreakEventsList teamId={teamId} />}

            {activeTab === 'risk' && <RiskScoresList teamId={teamId} />}

            <footer style={{ marginTop: '2rem', padding: '1rem', borderTop: '1px solid var(--color-border)', color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                <p>Currency: INR (₹) • Security: ED-BASE</p>
            </footer>
        </div>
    );
}

export default App;
