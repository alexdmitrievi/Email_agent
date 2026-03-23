"""Analytics dashboard endpoint — returns HTML dashboard page."""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.config import settings
from app.routers.admin import _verify_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Agent — Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #0f172a; color: #e2e8f0; padding: 20px; }
        h1 { color: #38bdf8; margin-bottom: 20px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .card { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
        .card h3 { color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
        .card .value { font-size: 32px; font-weight: 700; color: #f1f5f9; }
        .card .sub { font-size: 13px; color: #64748b; margin-top: 4px; }
        .funnel { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; margin-bottom: 24px; }
        .funnel h2 { color: #38bdf8; margin-bottom: 16px; }
        .bar-row { display: flex; align-items: center; margin-bottom: 8px; }
        .bar-label { width: 180px; font-size: 13px; color: #94a3b8; }
        .bar-track { flex: 1; background: #334155; border-radius: 4px; height: 24px; overflow: hidden; }
        .bar-fill { height: 100%; background: linear-gradient(90deg, #3b82f6, #06b6d4); border-radius: 4px;
                     display: flex; align-items: center; padding-left: 8px; font-size: 12px; font-weight: 600; min-width: 30px; }
        .error { color: #f87171; background: #1e293b; padding: 20px; border-radius: 12px; }
        #loading { text-align: center; padding: 40px; color: #64748b; }
    </style>
</head>
<body>
    <h1>Email Agent Dashboard</h1>
    <div id="loading">Loading...</div>
    <div id="content" style="display:none;">
        <div class="grid" id="cards"></div>
        <div class="funnel" id="funnel"><h2>Воронка</h2><div id="bars"></div></div>
        <div class="funnel" id="ab-section"><h2>A/B тестирование</h2><div id="ab-stats"></div></div>
    </div>
    <div id="error" class="error" style="display:none;"></div>

    <script>
        const TOKEN = new URLSearchParams(window.location.search).get('token') || '';
        async function load() {
            try {
                const resp = await fetch('/admin/stats', {
                    headers: { 'Authorization': 'Bearer ' + TOKEN }
                });
                if (!resp.ok) throw new Error('Auth failed: ' + resp.status);
                const data = await resp.json();
                render(data);
            } catch(e) {
                document.getElementById('loading').style.display = 'none';
                document.getElementById('error').style.display = 'block';
                document.getElementById('error').textContent = 'Error: ' + e.message;
            }
        }

        function render(data) {
            document.getElementById('loading').style.display = 'none';
            document.getElementById('content').style.display = 'block';

            // Cards
            const today = data.recent_days[0] || {};
            const cards = [
                { label: 'Получено писем', value: today.emails_received || 0 },
                { label: 'Отправлено писем', value: today.emails_sent || 0 },
                { label: 'Новых лидов', value: today.new_leads || 0 },
                { label: 'Передано менеджеру', value: today.handoffs || 0 },
            ];
            document.getElementById('cards').innerHTML = cards.map(c =>
                `<div class="card"><h3>${c.label}</h3><div class="value">${c.value}</div></div>`
            ).join('');

            // Funnel
            const funnel = data.funnel || {};
            const total = Math.max(Object.values(funnel).reduce((a,b) => a+b, 0), 1);
            document.getElementById('bars').innerHTML = Object.entries(funnel).map(([stage, count]) => {
                const pct = Math.round(count / total * 100);
                return `<div class="bar-row">
                    <div class="bar-label">${stage}</div>
                    <div class="bar-track"><div class="bar-fill" style="width:${Math.max(pct,3)}%">${count}</div></div>
                </div>`;
            }).join('');

            // A/B
            const ab = data.ab_testing || {};
            document.getElementById('ab-stats').innerHTML = `
                <p>Всего ответов на A/B тесты: <b>${ab.total_replies || 0}</b></p>
                <p>Вариант A (консервативный): <b>${ab.variant_a_replies || 0}</b> ответов</p>
                <p>Вариант B (креативный): <b>${ab.variant_b_replies || 0}</b> ответов</p>
            `;
        }

        load();
        setInterval(load, 60000);
    </script>
</body>
</html>
"""


@router.get("", response_class=HTMLResponse)
async def dashboard():
    """Serve the analytics dashboard page."""
    return DASHBOARD_HTML
