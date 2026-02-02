function renderChart(outages, sIso, eIso) {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const ctx = document.getElementById('mainChart').getContext('2d');
    if(AppState.chartInstance) AppState.chartInstance.destroy();

    const map = {};
    for(let d = new Date(sIso); d <= new Date(eIso); d.setDate(d.getDate()+1)) {
        map[d.toLocaleDateString('uk-UA')] = {off: 0};
    }

    outages.forEach(ev => {
        const k = new Date(ev.start.replace(' ', 'T')).toLocaleDateString('uk-UA');
        if(map[k]) map[k].off += (ev.duration_min / 60);
    });

    const labels = Object.keys(map);
    AppState.chartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                { label: 'Є світло', data: labels.map(l => 24 - map[l].off), backgroundColor: '#10b981', borderRadius: 4, hidden: AppState.hideGreenLayer },
                { label: 'Немає', data: labels.map(l => map[l].off), backgroundColor: '#ef4444', borderRadius: 4 }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: {
                x: { stacked: true, grid: { display: false }, ticks: { color: isDark ? '#94a3b8' : '#6b7280' } },
                y: { stacked: true, max: 24, grid: { color: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)' }, ticks: { color: isDark ? '#94a3b8' : '#6b7280' } }
            },
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${c.dataset.label}: ${hoursToHM(c.raw)}` } } }
        }
    });
}

function toggleChartView() {
    AppState.hideGreenLayer = !AppState.hideGreenLayer;
    renderChart(AppState.lastOutages, document.getElementById('startDate').value, document.getElementById('endDate').value);
}
