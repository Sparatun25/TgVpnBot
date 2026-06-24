"""Админ-панель: веб-интерфейс."""

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from api.auth import validate_login_widget
from core.config import settings

router = APIRouter(tags=["admin-ui"])


class TelegramLoginData(BaseModel):
    """Данные от Telegram Login Widget."""
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


@router.post("/api/admin/login")
async def admin_login(data: TelegramLoginData):
    """
    Валидация Telegram Login Widget для админки.

    Возвращает токен (tg_id) если пользователь — админ.
    """
    # Преобразуем в словарь для валидации
    data_dict = data.model_dump()

    bot_token = settings.bot_token
    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BOT_TOKEN не настроен",
        )

    try:
        tg_id = validate_login_widget(data_dict, bot_token.get_secret_value())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Ошибка валидации: {str(e)}",
        )

    # Проверяем, что пользователь — админ
    if tg_id not in settings.bot_admin_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещён: вы не администратор",
        )

    return {"tg_id": tg_id, "message": "Авторизация успешна"}


@router.get("/api/admin/config")
async def admin_config():
    """
    Конфиг для Telegram Login Widget.

    Возвращает bot_username для виджета.
    """
    bot_token = settings.bot_token
    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BOT_TOKEN не настроен",
        )

    # Для виджета нужен username бота
    # Временное решение: возвращаем заглушку, нужно будет настроить
    return {
        "bot_username": "Onyx_vpn24_bot",
    }


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
    <div id="app"></div>
    <script>
        // Состояние приложения
        let state = {
            metrics: null,
            subscriptions: [],
            loading: true,
            error: null,
            page: 1,
            total: 0,
            searchTgId: '',
            statusFilter: '',
            modal: null,
        };

        // Получить заголовки для API
        function getHeaders() {
            const headers = { 'Content-Type': 'application/json' };
            const adminTgId = sessionStorage.getItem('admin_tg_id');
            if (adminTgId) {
                headers['X-Admin-Tg-Id'] = adminTgId;
            }
            return headers;
        }

        // Загрузка метрик
        async function loadMetrics() {
            try {
                const res = await fetch('/api/admin/metrics', { headers: getHeaders() });
                if (!res.ok) throw new Error('Не удалось загрузить метрики');
                state.metrics = await res.json();
            } catch (err) {
                state.error = err.message;
            }
            render();
        }

        // Загрузка подписок
        async function loadSubscriptions() {
            state.loading = true;
            render();

            try {
                const params = new URLSearchParams({
                    page: state.page.toString(),
                    per_page: '20',
                });
                if (state.searchTgId) params.append('search_tg_id', state.searchTgId);
                if (state.statusFilter) params.append('status_filter', state.statusFilter);

                const res = await fetch(`/api/admin/subscriptions?${params}`, { headers: getHeaders() });
                if (!res.ok) throw new Error('Не удалось загрузить подписки');
                const data = await res.json();
                state.subscriptions = data.items;
                state.total = data.total;
            } catch (err) {
                state.error = err.message;
            } finally {
                state.loading = false;
            }
            render();
        }

        // Продление подписки
        async function handleExtend(subscriptionId, days) {
            try {
                const res = await fetch(`/api/admin/subscriptions/${subscriptionId}/extend`, {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({ days }),
                });
                if (!res.ok) throw new Error('Не удалось продлить подписку');
                state.modal = null;
                await loadSubscriptions();
                await loadMetrics();
            } catch (err) {
                alert(err.message);
            }
        }

        // Отзыв ключа
        async function handleRevoke(subscriptionId) {
            if (!confirm('Вы уверены? Ключ будет отозван безвозвратно.')) return;
            try {
                const res = await fetch(`/api/admin/subscriptions/${subscriptionId}/revoke`, {
                    method: 'DELETE',
                    headers: getHeaders(),
                });
                if (!res.ok) throw new Error('Не удалось отозвать ключ');
                await loadSubscriptions();
                await loadMetrics();
            } catch (err) {
                alert(err.message);
            }
        }

        // Выход
        function handleLogout() {
            sessionStorage.removeItem('admin_tg_id');
            window.location.reload();
        }

        // Рендер экрана входа
        function renderLogin() {
            return `
                <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;padding:24px;">
                    <div style="background:var(--onyx-dark);border:1px solid var(--onyx-gray);border-radius:24px;padding:48px;max-width:480px;width:100%;text-align:center;">
                        <h1 style="font-size:32px;font-weight:700;background:linear-gradient(135deg,var(--onyx-accent),var(--onyx-accent-hover));-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:8px;">OnyxVpn Admin</h1>
                        <p style="color:var(--onyx-text-muted);font-size:14px;margin-bottom:32px;">Авторизуйтесь через Telegram</p>
                        <div id="telegram-login-widget" style="margin-bottom:24px;"></div>
                        <div id="login-error" style="display:none;background:rgba(239,68,68,0.1);border:1px solid var(--onyx-error);border-radius:12px;padding:16px;color:var(--onyx-error);margin-top:16px;"></div>
                    </div>
                </div>
            `;
        }

        // Рендер админ-панели
        function renderAdmin() {
            const metricsHtml = state.metrics ? `
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-label">Всего пользователей</div>
                        <div class="metric-value">${state.metrics.total_users}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Активных подписок</div>
                        <div class="metric-value">${state.metrics.active_subscriptions}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Активных триалов</div>
                        <div class="metric-value">${state.metrics.active_trials}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Всего пополнений</div>
                        <div class="metric-value">${(state.metrics.total_deposits_kopecks / 100).toFixed(0)} ₽</div>
                    </div>
                </div>
            ` : '';

            const subscriptionsHtml = state.loading ? '<div class="loading">Загрузка...</div>' : `
                <table class="table">
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
                        ${state.subscriptions.map(sub => `
                            <tr>
                                <td>${sub.id}</td>
                                <td>${sub.user_tg_id}</td>
                                <td>${sub.username || '—'}</td>
                                <td><span class="badge badge-${sub.plan_type === 'trial' ? 'trial' : 'active'}">${sub.plan_type}</span></td>
                                <td><span class="badge badge-${sub.is_active ? 'active' : 'expired'}">${sub.is_active ? 'Активна' : 'Истекла'}</span></td>
                                <td>${new Date(sub.expires_at).toLocaleDateString('ru-RU')}</td>
                                <td>
                                    <div class="action-buttons">
                                        <button class="btn btn-primary" onclick="showExtendModal(${sub.id})">Продлить</button>
                                        ${sub.is_active ? `<button class="btn btn-danger" onclick="handleRevoke(${sub.id})">Отозвать</button>` : ''}
                                    </div>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
                <div class="pagination">
                    <button ${state.page === 1 ? 'disabled' : ''} onclick="changePage(-1)">← Назад</button>
                    <span style="padding:8px 14px;">Стр. ${state.page} из ${Math.ceil(state.total / 20)}</span>
                    <button ${state.page >= Math.ceil(state.total / 20) ? 'disabled' : ''} onclick="changePage(1)">Вперёд →</button>
                </div>
            `;

            return `
                <div class="admin-container">
                    <div class="admin-header">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                            <div>
                                <h1 class="admin-title">OnyxVpn Admin</h1>
                                <p class="admin-subtitle">Панель управления подписками</p>
                            </div>
                            <button class="btn btn-danger" style="font-size:12px;padding:6px 12px;" onclick="handleLogout()">Выйти</button>
                        </div>
                    </div>
                    ${metricsHtml}
                    <div class="section">
                        <div class="section-header">
                            <h2 class="section-title">Подписки</h2>
                            <div class="filters">
                                <input type="text" class="filter-input" placeholder="Поиск по tg_id" value="${state.searchTgId}" oninput="updateSearch(this.value)">
                                <select class="filter-select" value="${state.statusFilter}" onchange="updateFilter(this.value)">
                                    <option value="">Все</option>
                                    <option value="active">Активные</option>
                                    <option value="expired">Истёкшие</option>
                                    <option value="trial">Триалы</option>
                                </select>
                            </div>
                        </div>
                        ${subscriptionsHtml}
                    </div>
                </div>
            `;
        }

        // Рендер модального окна
        function renderModal() {
            if (!state.modal || state.modal.type !== 'extend') return '';
            return `
                <div class="modal-overlay" onclick="closeModal()">
                    <div class="modal" onclick="event.stopPropagation()">
                        <h3 class="modal-title">Продлить подписку</h3>
                        <div class="modal-body">
                            <div class="form-group">
                                <label class="form-label">Количество дней</label>
                                <input type="number" id="extend-days" class="form-input" value="30" min="1" max="365">
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button class="btn" onclick="closeModal()">Отмена</button>
                            <button class="btn btn-primary" onclick="submitExtend()">Продлить</button>
                        </div>
                    </div>
                </div>
            `;
        }

        // Основной рендер
        function render() {
            const app = document.getElementById('app');
            const adminTgId = sessionStorage.getItem('admin_tg_id');

            if (state.error) {
                app.innerHTML = `<div class="admin-container"><div class="error">${state.error}</div><button class="btn btn-primary" onclick="window.location.reload()">Обновить страницу</button></div>`;
                return;
            }

            if (!adminTgId) {
                app.innerHTML = renderLogin();
                initTelegramWidget();
            } else {
                app.innerHTML = renderAdmin() + renderModal();
            }
        }

        // Инициализация Telegram Login Widget
        function initTelegramWidget() {
            const container = document.getElementById('telegram-login-widget');
            if (!container) return;

            const script = document.createElement('script');
            script.src = 'https://telegram.org/js/telegram-widget.js?22';
            script.setAttribute('data-telegram-login', 'Onyx_vpn24_bot');
            script.setAttribute('data-size', 'large');
            script.setAttribute('data-onauth', 'onTelegramAuth(user)');
            script.setAttribute('data-request-access', 'write');
            container.appendChild(script);
        }

        // Обработчик авторизации от Telegram
        window.onTelegramAuth = async function(data) {
            try {
                const res = await fetch('/api/admin/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data),
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Ошибка авторизации');
                }

                const result = await res.json();
                sessionStorage.setItem('admin_tg_id', result.tg_id);
                window.location.reload();
            } catch (err) {
                const errorDiv = document.getElementById('login-error');
                if (errorDiv) {
                    errorDiv.textContent = err.message;
                    errorDiv.style.display = 'block';
                }
            }
        };

        // Вспомогательные функции
        function showExtendModal(subscriptionId) {
            state.modal = { type: 'extend', subscriptionId };
            render();
        }

        function closeModal() {
            state.modal = null;
            render();
        }

        function submitExtend() {
            const daysInput = document.getElementById('extend-days');
            const days = parseInt(daysInput.value);
            if (state.modal && state.modal.type === 'extend') {
                handleExtend(state.modal.subscriptionId, days);
            }
        }

        function changePage(delta) {
            state.page += delta;
            loadSubscriptions();
        }

        function updateSearch(value) {
            state.searchTgId = value;
            state.page = 1;
            loadSubscriptions();
        }

        function updateFilter(value) {
            state.statusFilter = value;
            state.page = 1;
            loadSubscriptions();
        }

        // Инициализация
        document.addEventListener('DOMContentLoaded', () => {
            const adminTgId = sessionStorage.getItem('admin_tg_id');
            if (adminTgId) {
                loadMetrics();
                loadSubscriptions();
            } else {
                render();
            }
        });
    </script>
</body>
</html>
"""
