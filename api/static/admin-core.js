/* OnyxVpn Admin — Core: state, API, modals, toasts, icons */

const App = (() => {
    const state = {
        view: 'overview',
        metrics: null,
        subscriptions: [],
        loading: { metrics: false, subscriptions: false },
        page: 1,
        perPage: 20,
        total: 0,
        searchTgId: '',
        statusFilter: '',
        // Рассылки
        broadcasts: [],
        totalBroadcasts: 0,
        broadcast: null,           // детали выбранной кампании
        broadcastDeliveries: [],
        broadcastDeliveriesByStatus: {},
        broadcastDeliveriesTotal: 0,
        broadcastDeliveriesFilter: '',
        broadcastSegmentStats: null,
        templateVariables: {},
        loadingBroadcasts: false,
        modal: null,
        adminTgId: null,
    };

    const PER_PAGE = 20;
    const TOAST_DURATION = 4000;
    const MASCOT_FALLBACK_SVG = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100' fill='%23A78BFA'><text y='.9em' font-size='90'>🐱</text></svg>`;

    // ─── API ─────────────────────────────────────────────
    function getToken() {
        return sessionStorage.getItem('admin_token');
    }

    function getHeaders(extra = {}) {
        const headers = { 'Content-Type': 'application/json', ...extra };
        const token = getToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;
        return headers;
    }

    // Edge-case-master: защита от зависших fetch.
    // 1) Дефолтный таймаут 30 сек через AbortController — иначе при потере связи
    //    спиннер крутится бесконечно и App.state.loading.* остаётся true.
    // 2) Caller может передать свой signal (options.signal) — мы свяжем его с
    //    внутренним контроллером, чтобы отмена работала в обе стороны.
    const DEFAULT_FETCH_TIMEOUT_MS = 30_000;

    async function authFetch(url, options = {}) {
        const externalSignal = options.signal;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), DEFAULT_FETCH_TIMEOUT_MS);
        if (externalSignal) {
            externalSignal.addEventListener('abort', () => controller.abort(), { once: true });
        }

        try {
            const res = await fetch(url, {
                ...options,
                signal: controller.signal,
                headers: { ...getHeaders(), ...(options.headers || {}) },
            });
            if (res.status === 401) {
                sessionStorage.removeItem('admin_token');
                sessionStorage.removeItem('admin_tg_id');
                window.location.reload();
                return new Promise(() => {});
            }
            return res;
        } catch (err) {
            if (err.name === 'AbortError') {
                if (externalSignal && externalSignal.aborted) {
                    throw err; // отмена от пользователя — пробрасываем как есть
                }
                throw new Error('Превышено время ожидания (30 сек). Проверьте соединение.');
            }
            throw err;
        } finally {
            clearTimeout(timeoutId);
        }
    }

    async function loadMetrics() {
        state.loading.metrics = true;
        try {
            const res = await authFetch('/api/admin/metrics');
            if (!res.ok) throw new Error('Не удалось загрузить метрики');
            state.metrics = await res.json();
        } catch (err) {
            toast('error', 'Ошибка загрузки', err.message);
        } finally {
            // Edge-case-master: гарантированный сброс флага даже при неожиданном исключении.
            state.loading.metrics = false;
        }
    }

    async function loadSubscriptions() {
        state.loading.subscriptions = true;
        try {
            const params = new URLSearchParams({
                page: state.page.toString(),
                per_page: PER_PAGE.toString(),
            });
            if (state.searchTgId) params.append('search_tg_id', state.searchTgId);
            if (state.statusFilter) params.append('status_filter', state.statusFilter);

            const res = await authFetch(`/api/admin/subscriptions?${params}`);
            if (!res.ok) throw new Error('Не удалось загрузить подписки');
            const data = await res.json();
            state.subscriptions = data.items;
            state.total = data.total;
        } catch (err) {
            toast('error', 'Ошибка загрузки', err.message);
        } finally {
            // Edge-case-master: гарантированный сброс флага даже при неожиданном исключении.
            state.loading.subscriptions = false;
        }
    }

    async function extendSubscription(id, days) {
        const res = await authFetch(`/api/admin/subscriptions/${id}/extend`, {
            method: 'POST',
            body: JSON.stringify({ days }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Не удалось продлить');
        }
    }

    async function topUpBalance(tgId, amountRubles, comment) {
        const res = await authFetch(`/api/admin/users/${tgId}/topup`, {
            method: 'POST',
            body: JSON.stringify({ amount_rubles: amountRubles, comment }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Не удалось начислить');
        }
        return res.json();
    }

    async function revokeSubscription(id) {
        const res = await authFetch(`/api/admin/subscriptions/${id}/revoke`, {
            method: 'DELETE',
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Не удалось отозвать');
        }
    }

    async function clearAllSubscriptions() {
        const res = await authFetch('/api/admin/subscriptions/clear-all', {
            method: 'DELETE',
            body: JSON.stringify({ confirmation: 'DELETE_ALL_SUBSCRIPTIONS' }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Не удалось очистить');
        }
        return res.json();
    }

    async function loadUserTraffic(tgId) {
        const res = await authFetch(`/api/admin/users/${tgId}/traffic`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Не удалось загрузить трафик');
        }
        return res.json();
    }

    // ─── Broadcasts API ─────────────────────────────────
    async function loadBroadcasts(page = 1, perPage = 20, statusFilter = '') {
        state.loadingBroadcasts = true;
        try {
            const params = new URLSearchParams({
                page: page.toString(),
                per_page: perPage.toString(),
            });
            if (statusFilter) params.append('status', statusFilter);
            const res = await authFetch(`/api/admin/broadcasts?${params}`);
            if (!res.ok) throw new Error('Не удалось загрузить рассылки');
            const data = await res.json();
            state.broadcasts = data.items;
            state.totalBroadcasts = data.total;
        } catch (err) {
            toast('error', 'Ошибка загрузки', err.message);
        } finally {
            // Edge-case-master: гарантированный сброс флага даже при неожиданном исключении.
            state.loadingBroadcasts = false;
        }
    }

    async function loadBroadcastSegmentStats() {
        try {
            const res = await authFetch('/api/admin/broadcasts/segments/stats');
            if (!res.ok) throw new Error('Не удалось загрузить статистику сегментов');
            const data = await res.json();
            state.broadcastSegmentStats = data.segments;
            state.templateVariables = data.template_variables || {};
        } catch (err) {
            toast('error', 'Ошибка загрузки', err.message);
        }
    }

    async function loadBroadcastDetail(id) {
        try {
            const res = await authFetch(`/api/admin/broadcasts/${id}`);
            if (!res.ok) throw new Error('Не удалось загрузить кампанию');
            state.broadcast = await res.json();
            return state.broadcast;
        } catch (err) {
            toast('error', 'Ошибка загрузки', err.message);
            throw err;
        }
    }

    async function loadBroadcastDeliveries(id, page = 1, statusFilter = '') {
        try {
            const params = new URLSearchParams({
                page: page.toString(),
                per_page: '50',
            });
            if (statusFilter) params.append('status', statusFilter);
            const res = await authFetch(`/api/admin/broadcasts/${id}/deliveries?${params}`);
            if (!res.ok) throw new Error('Не удалось загрузить получателей');
            const data = await res.json();
            state.broadcastDeliveries = data.items;
            state.broadcastDeliveriesTotal = data.total;
            state.broadcastDeliveriesByStatus = data.by_status;
        } catch (err) {
            toast('error', 'Ошибка загрузки', err.message);
        }
    }

    async function createBroadcast(data) {
        const res = await authFetch('/api/admin/broadcasts', {
            method: 'POST',
            body: JSON.stringify(data),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Не удалось создать рассылку');
        }
        return res.json();
    }

    async function startBroadcast(id) {
        const res = await authFetch(`/api/admin/broadcasts/${id}/start`, {
            method: 'POST',
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Не удалось запустить');
        }
        return res.json();
    }

    async function cancelBroadcast(id) {
        const res = await authFetch(`/api/admin/broadcasts/${id}/cancel`, {
            method: 'POST',
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Не удалось отменить');
        }
        return res.json();
    }

    async function deleteBroadcast(id) {
        const res = await authFetch(`/api/admin/broadcasts/${id}`, {
            method: 'DELETE',
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Не удалось удалить');
        }
        return res.json();
    }

    async function logout() {
        const token = getToken();
        sessionStorage.removeItem('admin_token');
        sessionStorage.removeItem('admin_tg_id');
        try {
            if (token) {
                await fetch('/api/admin/logout', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                });
            }
        } catch (_) { /* noop */ }
        window.location.reload();
    }

    // ─── Toasts ──────────────────────────────────────────
    const ICONS = {
        success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><path d="M20 6L9 17L4 12"/></svg>',
        error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
        close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    };

    function toast(type, title, message) {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const el = document.createElement('div');
        el.className = `toast toast--${type}`;

        const icon = document.createElement('div');
        icon.className = 'toast__icon';
        icon.innerHTML = ICONS[type] || ICONS.info;

        const content = document.createElement('div');
        content.className = 'toast__content';

        const titleEl = document.createElement('div');
        titleEl.className = 'toast__title';
        titleEl.textContent = title;
        content.appendChild(titleEl);

        if (message) {
            const msgEl = document.createElement('div');
            msgEl.className = 'toast__message';
            msgEl.textContent = message;
            content.appendChild(msgEl);
        }

        const closeBtn = document.createElement('button');
        closeBtn.className = 'toast__close';
        closeBtn.setAttribute('aria-label', 'Закрыть');
        closeBtn.innerHTML = ICONS.close;

        el.appendChild(icon);
        el.appendChild(content);
        el.appendChild(closeBtn);
        container.appendChild(el);

        const dismiss = () => {
            el.classList.add('toast--leaving');
            setTimeout(() => el.remove(), 250);
        };

        closeBtn.addEventListener('click', dismiss);
        setTimeout(dismiss, TOAST_DURATION);
    }

    // ─── Modal helpers ───────────────────────────────────
    function rerender() {
        if (typeof window.renderApp === 'function') window.renderApp();
    }

    function openModal(config) {
        state.modal = config;
        rerender();
    }

    function closeModal() {
        state.modal = null;
        rerender();
    }

    // ─── Init ────────────────────────────────────────────
    async function init() {
        const token = getToken();
        if (!token) {
            rerender();
            initTelegramWidget();
            return;
        }
        await Promise.all([loadMetrics(), loadSubscriptions()]);
        rerender();
    }

    // Public API
    return {
        state,
        loadMetrics,
        loadSubscriptions,
        loadUserTraffic,
        extendSubscription,
        topUpBalance,
        revokeSubscription,
        clearAllSubscriptions,
        loadBroadcasts,
        loadBroadcastSegmentStats,
        loadBroadcastDetail,
        loadBroadcastDeliveries,
        createBroadcast,
        startBroadcast,
        cancelBroadcast,
        deleteBroadcast,
        logout,
        toast,
        openModal,
        closeModal,
        init,
    };
})();
