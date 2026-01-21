/**
 * ED-TRAIL API Hooks
 * Uses ED-BASE apiClient unchanged.
 */

// Import from ED-BASE
// import { apiClient } from '../../../frontend/src/services/apiClient';

const API_BASE = '/api/trail';

async function fetchApi(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || 'Request failed');
    }

    return response.json();
}

export async function fetchDataSources(teamId) {
    return fetchApi(`${API_BASE}/sources?team_id=${teamId}`);
}

export async function fetchDataAssets(teamId, options = {}) {
    let url = `${API_BASE}/assets?team_id=${teamId}`;
    if (options.sourceId) url += `&source_id=${options.sourceId}`;
    if (options.orphansOnly) url += `&orphans_only=true`;
    return fetchApi(url);
}

export async function fetchAssetLineage(teamId, assetId, direction = 'upstream') {
    return fetchApi(`${API_BASE}/assets/${assetId}/lineage?team_id=${teamId}&direction=${direction}`);
}

export async function fetchBreakEvents(teamId, options = {}) {
    let url = `${API_BASE}/breaks?team_id=${teamId}`;
    if (options.status) url += `&status=${options.status}`;
    if (options.severity) url += `&severity=${options.severity}`;
    return fetchApi(url);
}

export async function fetchAssetScore(teamId, assetId) {
    return fetchApi(`${API_BASE}/assets/${assetId}/score?team_id=${teamId}`);
}

export async function fetchHighRiskAssets(teamId, minScore = 50) {
    return fetchApi(`${API_BASE}/scores/high-risk?team_id=${teamId}&min_score=${minScore}`);
}
