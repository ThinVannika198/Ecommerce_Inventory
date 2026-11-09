/* dashboard.js */

document.addEventListener('DOMContentLoaded', function () {

  /* ===== Sales & Purchases chart (clickable months) ===== */
(function () {
    const canvas = document.getElementById('salesChart');   // use your real canvas id
    const dataEl = document.getElementById('chart-data');
    if (!canvas || !dataEl) return;

    const data = JSON.parse(dataEl.textContent);
    const monthUrl = canvas.dataset.monthUrl;
    const money = n => '$' + Number(n).toFixed(2);

    new Chart(canvas, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [
                { label: 'Sales Target', data: data.target,    backgroundColor: '#4b5563', borderRadius: 6 },
                { label: 'Sales',        data: data.sales,     backgroundColor: '#ef4444', borderRadius: 6 },
                { label: 'Purchases',    data: data.purchases, backgroundColor: '#8b5cf6', borderRadius: 6 },
            ],
        },
        options: {
            responsive: true,
            plugins: { legend: { position: 'bottom', labels: { color: '#cbd5e1' } } },
            scales: {
                x: { ticks: { color: '#94a3b8' }, grid: { display: false } },
                y: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' }, beginAtZero: true },
            },
            onHover: (e, els) => {
                e.native.target.style.cursor = els.length ? 'pointer' : 'default';
            },
            onClick: (evt, els) => {
                if (!els.length) return;
                showMonth(data.keys[els[0].index]);
            },
        },
    });

    async function showMonth(key) {
        const res = await fetch(monthUrl + '?month=' + encodeURIComponent(key));
        if (!res.ok) return;
        const d = await res.json();

        document.getElementById('mp-title').textContent = d.month;
        document.getElementById('mp-customers').textContent = d.customers_count;
        document.getElementById('mp-walkins').textContent = d.walkins;
        document.getElementById('mp-orders').textContent = d.orders;
        document.getElementById('mp-sales').textContent = money(d.sales);

        const body = document.getElementById('mp-rows');
        body.innerHTML = '';
        if (!d.customers.length) {
            body.innerHTML = '<tr><td colspan="3">No customers bought this month.</td></tr>';
        }
        d.customers.forEach(c => {
            const tr = document.createElement('tr');
            tr.innerHTML = '<td></td><td></td><td></td>';
            tr.children[0].textContent = c.name;
            tr.children[1].textContent = c.orders;
            tr.children[2].textContent = money(c.spent);
            body.appendChild(tr);
        });

        document.getElementById('month-panel').hidden = false;
    }

    // "6 Months" dropdown -> reload with ?months=6 or 12
    const monthsSelect = document.getElementById('months-select');
    if (monthsSelect) {
        monthsSelect.addEventListener('change', () => {
            window.location.search = '?months=' + monthsSelect.value;
        });
    }
})();

    // ─── Products by Brand Donut ───
    const brandCtx = document.getElementById('brandDonut');
    if (brandCtx) {
        // Read data from the JSON script tag
        const brandDataEl = document.getElementById('brand-data');
        let brandLabels = [];
        let brandCounts = [];

        if (brandDataEl) {
            try {
                const parsed = JSON.parse(brandDataEl.textContent);
                brandLabels = parsed.labels || [];
                brandCounts = parsed.counts || [];
            } catch (e) {
                console.warn('Could not parse brand data:', e);
            }
        }

        new Chart(brandCtx.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: brandLabels,
                datasets: [{
                    data: brandCounts,
                    backgroundColor: [
                        '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
                        '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16'
                    ],
                    borderColor: '#1e293b',
                    borderWidth: 3,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '68%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#cbd5e1',
                            font: { size: 12 },
                            padding: 12,
                            boxWidth: 14
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                                const v = ctx.parsed;
                                const pct = total ? ((v / total) * 100).toFixed(1) : 0;
                                return `${ctx.label}: ${v} (${pct}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

});