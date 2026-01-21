/**
 * ED-TRAIL Currency Display
 * Converts paise to INR for display.
 */

export function formatINR(paise) {
    if (paise === null || paise === undefined) return null;
    const rupees = paise / 100;
    return `₹${rupees.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatScore(score) {
    if (score >= 70) return { class: 'score-high', label: 'High Risk' };
    if (score >= 40) return { class: 'score-medium', label: 'Medium Risk' };
    return { class: 'score-low', label: 'Low Risk' };
}
