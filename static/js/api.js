async function loadData(params) {
    document.getElementById('loader').classList.add('show');
    try {
        const res = await fetch(`api/stats?${params}&nocache=${Date.now()}`);
        const data = await res.json();
        AppState.lastOutages = data.outages;
        updateUI(data);
    } catch(e) { 
        console.error("API Error:", e);
    } finally {
        setTimeout(() => document.getElementById('loader').classList.remove('show'), 200);
    }
}
