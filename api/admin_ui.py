"""Админ-панель: веб-интерфейс."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["admin-ui"])


@router.get("/admin", response_class=HTMLResponse)
async def admin_ui(request: Request):
    """Веб-интерфейс админ-панели."""
    return """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OnyxVpn Admin</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script crossorigin="anonymous" src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script crossorigin="anonymous" src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script crossorigin="anonymous" src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <style>
        :root {
            --onyx-black: #0D0D0D;
            --onyx-dark: #1A1A1A;
            --onyx-gray: #2A2A2A;
            --onyx-light: #3A3A3A;
            --onyx-accent: #C9A96E;
            --onyx-accent-hover: #D4B87A;
            --onyx-purple: #A78BFA;
            --onyx-blue: #60A5FA;
            --onyx-success: #10B981;
            --onyx-error: #EF4444;
            --onyx-text: #FFFFFF;
            --onyx-text-muted: #8A8A8A;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
            background: var(--onyx-black);
            color: var(--onyx-text);
            min-height: 100vh;
        }

        .admin-container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 24px;
        }

        .admin-header {
            margin-bottom: 32px;
        }

        .admin-title {
            font-size: 32px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--onyx-accent), var(--onyx-accent-hover));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 8px;
        }

        .admin-subtitle {
            color: var(--onyx-text-muted);
            font-size: 14px;
        }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }

        .metric-card {
            background: var(--onyx-dark);
            border: 1px solid var(--onyx-gray);
            border-radius: 16px;
            padding: 24px;
            transition: all 0.2s ease;
        }

        .metric-card:hover {
            border-color: var(--onyx-light);
            transform: translateY(-2px);
        }

        .metric-label {
            font-size: 13px;
            color: var(--onyx-text-muted);
            margin-bottom: 8px;
        }

        .metric-value {
            font-size: 36px;
            font-weight: 700;
            color: var(--onyx-accent);
        }

        .metric-trend {
            font-size: 12px;
            color: var(--onyx-success);
            margin-top: 4px;
        }

        .section {
            background: var(--onyx-dark);
            border: 1px solid var(--onyx-gray);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
        }

        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .section-title {
            font-size: 20px;
            font-weight: 600;
        }

        .filters {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }

        .filter-input {
            padding: 10px 16px;
            background: var(--onyx-black);
            border: 1px solid var(--onyx-gray);
            border-radius: 10px;
            color: var(--onyx-text);
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s ease;
        }

        .filter-input:focus {
            border-color: var(--onyx-accent);
        }

        .filter-select {
            padding: 10px 16px;
            background: var(--onyx-black);
            border: 1px solid var(--onyx-gray);
            border-radius: 10px;
            color: var(--onyx-text);
            font-size: 14px;
            outline: none;
            cursor: pointer;
        }

        .table {
            width: 100%;
            border-collapse: collapse;
        }

        .table th {
            text-align: left;
            padding: 12px;
            font-size: 13px;
            font-weight: 600;
            color: var(--onyx-text-muted);
            border-bottom: 1px solid var(--onyx-gray);
        }

        .table td {
            padding: 16px 12px;
            font-size: 14px;
            border-bottom: 1px solid var(--onyx-gray);
        }

        .table tr:hover {
            background: rgba(255, 255, 255, 0.02);
        }

        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }

        .badge-active {
            background: rgba(16, 185, 129, 0.2);
            color: var(--onyx-success);
        }

        .badge-expired {
            background: rgba(239, 68, 68, 0.2);
            color: var(--onyx-error);
        }

        .badge-trial {
            background: rgba(167, 139, 250, 0.2);
            color: var(--onyx-purple);
        }

        .action-buttons {
            display: flex;
            gap: 8px;
        }

        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .btn-primary {
            background: var(--onyx-accent);
            color: var(--onyx-black);
        }

        .btn-primary:hover {
            background: var(--onyx-accent-hover);
        }

        .btn-danger {
            background: var(--onyx-error);
            color: white;
        }

        .btn-danger:hover {
            background: #DC2626;
        }

        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.8);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }

        .modal {
            background: var(--onyx-dark);
            border: 1px solid var(--onyx-gray);
            border-radius: 16px;
            padding: 32px;
            max-width: 480px;
            width: 90%;
        }

        .modal-title {
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 16px;
        }

        .modal-body {
            margin-bottom: 24px;
        }

        .modal-footer {
            display: flex;
            gap: 12px;
            justify-content: flex-end;
        }

        .form-group {
            margin-bottom: 16px;
        }

        .form-label {
            display: block;
            font-size: 13px;
            color: var(--onyx-text-muted);
            margin-bottom: 8px;
        }

        .form-input {
            width: 100%;
            padding: 12px;
            background: var(--onyx-black);
            border: 1px solid var(--onyx-gray);
            border-radius: 10px;
            color: var(--onyx-text);
            font-size: 14px;
            outline: none;
        }

        .form-input:focus {
            border-color: var(--onyx-accent);
        }

        .loading {
            text-align: center;
            padding: 40px;
            color: var(--onyx-text-muted);
        }

        .error {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid var(--onyx-error);
            border-radius: 12px;
            padding: 16px;
            color: var(--onyx-error);
            margin-bottom: 16px;
        }

        .pagination {
            display: flex;
            gap: 8px;
            justify-content: center;
            margin-top: 20px;
        }

        .pagination button {
            padding: 8px 14px;
            background: var(--onyx-gray);
            border: 1px solid var(--onyx-light);
            border-radius: 8px;
            color: var(--onyx-text);
            cursor: pointer;
        }

        .pagination button:hover {
            background: var(--onyx-light);
        }

        .pagination button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        @media (max-width: 768px) {
            .admin-container { padding: 16px; }
            .metrics-grid { grid-template-columns: 1fr; }
            .table { font-size: 12px; }
            .table th, .table td { padding: 8px 6px; }
        }
    </style>
</head>
<body>
    <div id="root"></div>
    <script type="text/babel">
        const { useState, useEffect } = React;

        function AdminPanel() {
            const [metrics, setMetrics] = useState(null);
            const [subscriptions, setSubscriptions] = useState([]);
            const [loading, setLoading] = useState(true);
            const [error, setError] = useState(null);
            const [page, setPage] = useState(1);
            const [total, setTotal] = useState(0);
            const [searchTgId, setSearchTgId] = useState('');
            const [statusFilter, setStatusFilter] = useState('');
            const [modal, setModal] = useState(null);

            const initData = window.Telegram?.WebApp?.initData || '';

            const headers = {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${initData}`,
            };

            useEffect(() => {
                loadMetrics();
                loadSubscriptions();
            }, [page, searchTgId, statusFilter]);

            const loadMetrics = async () => {
                try {
                    const res = await fetch('/api/admin/metrics', { headers });
                    if (!res.ok) throw new Error('Не удалось загрузить метрики');
                    const data = await res.json();
                    setMetrics(data);
                } catch (err) {
                    setError(err.message);
                }
            };

            const loadSubscriptions = async () => {
                setLoading(true);
                try {
                    const params = new URLSearchParams({
                        page: page.toString(),
                        per_page: '20',
                    });
                    if (searchTgId) params.append('search_tg_id', searchTgId);
                    if (statusFilter) params.append('status_filter', statusFilter);

                    const res = await fetch(`/api/admin/subscriptions?${params}`, { headers });
                    if (!res.ok) throw new Error('Не удалось загрузить подписки');
                    const data = await res.json();
                    setSubscriptions(data.items);
                    setTotal(data.total);
                } catch (err) {
                    setError(err.message);
                } finally {
                    setLoading(false);
                }
            };

            const handleExtend = async (subscriptionId, days) => {
                try {
                    const res = await fetch(`/api/admin/subscriptions/${subscriptionId}/extend`, {
                        method: 'POST',
                        headers,
                        body: JSON.stringify({ days }),
                    });
                    if (!res.ok) throw new Error('Не удалось продлить подписку');
                    setModal(null);
                    loadSubscriptions();
                    loadMetrics();
                } catch (err) {
                    alert(err.message);
                }
            };

            const handleRevoke = async (subscriptionId) => {
                if (!confirm('Вы уверены? Ключ будет отозван безвозвратно.')) return;
                try {
                    const res = await fetch(`/api/admin/subscriptions/${subscriptionId}/revoke`, {
                        method: 'DELETE',
                        headers,
                    });
                    if (!res.ok) throw new Error('Не удалось отозвать ключ');
                    loadSubscriptions();
                    loadMetrics();
                } catch (err) {
                    alert(err.message);
                }
            };

            if (error) {
                return (
                    <div className="admin-container">
                        <div className="error">{error}</div>
                        <button className="btn btn-primary" onClick={() => window.location.reload()}>
                            Обновить страницу
                        </button>
                    </div>
                );
            }

            return (
                <div className="admin-container">
                    <div className="admin-header">
                        <h1 className="admin-title">OnyxVpn Admin</h1>
                        <p className="admin-subtitle">Панель управления подписками</p>
                    </div>

                    {metrics && (
                        <div className="metrics-grid">
                            <div className="metric-card">
                                <div className="metric-label">Всего пользователей</div>
                                <div className="metric-value">{metrics.total_users}</div>
                            </div>
                            <div className="metric-card">
                                <div className="metric-label">Активных подписок</div>
                                <div className="metric-value">{metrics.active_subscriptions}</div>
                            </div>
                            <div className="metric-card">
                                <div className="metric-label">Активных триалов</div>
                                <div className="metric-value">{metrics.active_trials}</div>
                            </div>
                            <div className="metric-card">
                                <div className="metric-label">Всего пополнений</div>
                                <div className="metric-value">{(metrics.total_deposits_kopecks / 100).toFixed(0)} ₽</div>
                            </div>
                        </div>
                    )}

                    <div className="section">
                        <div className="section-header">
                            <h2 className="section-title">Подписки</h2>
                            <div className="filters">
                                <input
                                    type="text"
                                    className="filter-input"
                                    placeholder="Поиск по tg_id"
                                    value={searchTgId}
                                    onChange={(e) => setSearchTgId(e.target.value)}
                                />
                                <select
                                    className="filter-select"
                                    value={statusFilter}
                                    onChange={(e) => setStatusFilter(e.target.value)}
                                >
                                    <option value="">Все</option>
                                    <option value="active">Активные</option>
                                    <option value="expired">Истёкшие</option>
                                    <option value="trial">Триалы</option>
                                </select>
                            </div>
                        </div>

                        {loading ? (
                            <div className="loading">Загрузка...</div>
                        ) : (
                            <>
                                <table className="table">
                                    <thead>
                                        <tr>
                                            <th>ID</th>
                                            <th>Telegram ID</th>
                                            <th>Username</th>
                                            <th>Тип</th>
                                            <th>Статус</th>
                                            <th>Истекает</th>
                                            <th>Действия</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {subscriptions.map((sub) => (
                                            <tr key={sub.id}>
                                                <td>{sub.id}</td>
                                                <td>{sub.user_tg_id}</td>
                                                <td>{sub.username || '—'}</td>
                                                <td>
                                                    <span className={`badge badge-${sub.plan_type === 'trial' ? 'trial' : 'active'}`}>
                                                        {sub.plan_type}
                                                    </span>
                                                </td>
                                                <td>
                                                    <span className={`badge badge-${sub.is_active ? 'active' : 'expired'}`}>
                                                        {sub.is_active ? 'Активна' : 'Истекла'}
                                                    </span>
                                                </td>
                                                <td>{new Date(sub.expires_at).toLocaleDateString('ru-RU')}</td>
                                                <td>
                                                    <div className="action-buttons">
                                                        <button
                                                            className="btn btn-primary"
                                                            onClick={() => setModal({ type: 'extend', subscriptionId: sub.id })}
                                                        >
                                                            Продлить
                                                        </button>
                                                        {sub.is_active && (
                                                            <button
                                                                className="btn btn-danger"
                                                                onClick={() => handleRevoke(sub.id)}
                                                            >
                                                                Отозвать
                                                            </button>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>

                                <div className="pagination">
                                    <button
                                        disabled={page === 1}
                                        onClick={() => setPage(p => p - 1)}
                                    >
                                        ← Назад
                                    </button>
                                    <span style={{ padding: '8px 14px' }}>
                                        Стр. {page} из {Math.ceil(total / 20)}
                                    </span>
                                    <button
                                        disabled={page >= Math.ceil(total / 20)}
                                        onClick={() => setPage(p => p + 1)}
                                    >
                                        Вперёд →
                                    </button>
                                </div>
                            </>
                        )}
                    </div>

                    {modal && modal.type === 'extend' && (
                        <ExtendModal
                            subscriptionId={modal.subscriptionId}
                            onClose={() => setModal(null)}
                            onExtend={handleExtend}
                        />
                    )}
                </div>
            );
        }

        function ExtendModal({ subscriptionId, onClose, onExtend }) {
            const [days, setDays] = useState(30);

            return (
                <div className="modal-overlay" onClick={onClose}>
                    <div className="modal" onClick={(e) => e.stopPropagation()}>
                        <h3 className="modal-title">Продлить подписку</h3>
                        <div className="modal-body">
                            <div className="form-group">
                                <label className="form-label">Количество дней</label>
                                <input
                                    type="number"
                                    className="form-input"
                                    value={days}
                                    onChange={(e) => setDays(parseInt(e.target.value))}
                                    min="1"
                                    max="365"
                                />
                            </div>
                        </div>
                        <div className="modal-footer">
                            <button className="btn" onClick={onClose}>Отмена</button>
                            <button className="btn btn-primary" onClick={() => onExtend(subscriptionId, days)}>
                                Продлить
                            </button>
                        </div>
                    </div>
                </div>
            );
        }

        ReactDOM.createRoot(document.getElementById('root')).render(<AdminPanel />);
    </script>
</body>
</html>
"""
