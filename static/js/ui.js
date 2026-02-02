function hoursToHM(v) {
    if (isNaN(v)) return v;
    const h = Math.floor(v);
    const m = Math.round((v - h) * 60);
    return `${h}г ${m}хв`;
}

function updateUI(data) {
    const d = new Date(data.last_update);
    document.getElementById('lastUpdate').innerText = !isNaN(d.getTime()) 
        ? d.toLocaleDateString('uk-UA') + ' о ' + d.toLocaleTimeString('uk-UA', {hour:'2-digit', minute:'2-digit'})
        : data.last_update;

    const sb = document.getElementById('statusBadge');
    const dot = sb.querySelector('.dot');
    if(data.is_online) {
        sb.className = 'status-badge status-online';
        dot.className = 'dot bg-green';
        document.getElementById('statusText').textContent = "Світло Є";
    } else {
        sb.className = 'status-badge status-offline pulse';
        dot.className = 'dot bg-red';
        document.getElementById('statusText').textContent = "Світла НЕМАЄ";
    }

    document.getElementById('valOnPercent').innerText = data.stats.on_percent + '%';
    document.getElementById('valOnHours').innerText = hoursToHM(data.stats.on_hours);
    document.getElementById('valOffPercent').innerText = data.stats.off_percent + '%';
    document.getElementById('valOffHours').innerText = hoursToHM(data.stats.off_hours);
    document.getElementById('valEvents').innerText = data.stats.total_events;
    document.getElementById('valAvg').innerText = data.stats.avg_duration;
    document.getElementById('valRange').innerText = data.meta.display_range;

    const list = document.getElementById('eventsList');
    list.innerHTML = '';
    data.outages.forEach(ev => {
        const s = new Date(ev.start);
        const dur = hoursToHM(ev.duration_min/60);
        list.innerHTML += `
            <div class="list-item ${ev.is_active ? 'active-outage' : ''}">
                <div class="list-icon ${ev.is_active ? 'pulse' : ''}" style="background:${ev.is_active ? 'var(--danger)' : 'rgba(239,68,68,0.1)'};color:${ev.is_active ? 'white' : 'var(--danger)'}">
                    <span class="material-icons-round">${ev.is_active ? 'bolt' : 'power_off'}</span>
                </div>
                <div class="list-content">
                    <div class="list-time">${s.toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'})} — ${ev.is_active ? 'Зараз' : new Date(ev.end).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'})}</div>
                    <div class="list-date">${s.toLocaleDateString('uk-UA')}</div>
                </div>
                <div class="list-badge">${dur}</div>
            </div>`;
    });
    renderChart(data.outages, document.getElementById('startDate').value, document.getElementById('endDate').value);
}

function quickFilter(days, btn) {
    document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
    if(btn) btn.classList.add('active');
    
    const end = new Date();
    let start = new Date();
    if (days === 'all') start = new Date(AppState.projectStart);
    else if (days === 0) start = new Date();
    else start.setDate(end.getDate() - days);

    const sStr = start.toISOString().split('T')[0];
    const eStr = end.toISOString().split('T')[0];
    document.getElementById('startDate').value = sStr;
    document.getElementById('endDate').value = eStr;
    loadData(`start=${sStr}&end=${eStr}`);
}

function customDateLoad() {
    const s = document.getElementById('startDate').value;
    const e = document.getElementById('endDate').value;
    if(s && e) {
        document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
        loadData(`start=${s}&end=${e}`);
    }
}
