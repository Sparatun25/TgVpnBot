/* OnyxVpn Admin — App: render orchestrator + views */

const NAV_ITEMS = [
    { id: 'overview', label: 'Обзор', icon: 'home' },
    { id: 'subscriptions', label: 'Подписки', icon: 'key' },
    { id: 'broadcasts', label: 'Рассылки', icon: 'send' },
];

const ICONS = {
    home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" class="nav-item__icon"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
    key: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" class="nav-item__icon"><circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/></svg>',
    users: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="18" height="18"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    zap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="18" height="18"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
    dollar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="18" height="18"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
    gift: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="18" height="18"><polyline points="20 12 20 22 4 22 4 12"/><rect x="2" y="7" width="20" height="5"/><line x1="12" y1="22" x2="12" y2="7"/><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"/><path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="16" height="16"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6"/></svg>',
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    logout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>',
    chevronLeft: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><polyline points="15 18 9 12 15 6"/></svg>',
    chevronRight: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><polyline points="9 18 15 12 9 6"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="18" height="18"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    activity: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="18" height="18"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>',
    play: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
    pause: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>',
    bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    eye: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>',
};

// ─── Helpers ────────────────────────────────────────────
function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
        if (k === 'class') node.className = v;
        else if (k === 'html') node.innerHTML = v;
        else if (k === 'text') node.textContent = v;
        else if (k.startsWith('on')) {
            // addEventListener требует функцию. Строковый on* (например,
            // inline onerror для <img>) — это атрибут, не listener, иначе
            // TypeError роняет весь render и экран остаётся пустым.
            if (typeof v === 'function') {
                node.addEventListener(k.slice(2).toLowerCase(), v);
            } else {
                node.setAttribute(k, v);
            }
        }
        else if (k === 'dataset') Object.assign(node.dataset, v);
        else node.setAttribute(k, v);
    }
    for (const child of children.flat()) {
        if (child == null) continue;
        node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    }
    return node;
}

function formatMoney(kopecks) {
    return `${(kopecks / 100).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ' ')} ₽`;
}

function formatDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString('ru-RU', {
        day: 'numeric', month: 'short', year: 'numeric',
    });
}

function formatRelative(iso) {
    if (!iso) return '—';
    const diff = Date.now() - new Date(iso).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return 'только что';
    if (minutes < 60) return `${minutes} мин назад`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} ч назад`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days} д назад`;
    return formatDate(iso);
}

function getInitials(name) {
    if (!name) return '?';
    const parts = name.trim().split(/\s+/);
    return (parts[0][0] + (parts[1]?.[0] || '')).toUpperCase().slice(0, 2);
}

// ─── Login view ─────────────────────────────────────────
function renderLogin() {
    return el('div', { class: 'login' },
        el('div', { class: 'login__card' },
            el('img', {
                src: '/cat-mascot.png',
                alt: 'Onyx',
                class: 'login__mascot',
                onerror: "this.onerror=null;this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22 fill=%22%23A78BFA%22%3E%3Ctext y=%22.9em%22 font-size=%2290%22%3E🐱%3C/text%3E%3C/svg%3E'",
            }),
            el('h1', { class: 'login__title', text: 'OnyxVpn Admin' }),
            el('p', { class: 'login__subtitle', text: 'Войдите через Telegram для доступа к панели управления' }),
            el('div', { class: 'login__widget-wrapper', id: 'telegram-login-widget' }),
            el('div', { class: 'login__error', id: 'login-error' }),
        )
    );
}

// ─── Layout ─────────────────────────────────────────────
function renderSidebar() {
    const navItems = NAV_ITEMS.map(item => {
        const isActive = item.id === App.state.view;
        return el('button', {
            class: `nav-item${isActive ? ' nav-item--active' : ''}`,
            onClick: () => switchView(item.id),
        },
            el('span', { html: ICONS[item.icon] }),
            el('span', { class: 'nav-item__label', text: item.label }),
        );
    });

    return el('aside', { class: 'sidebar' },
        el('div', { class: 'sidebar__brand' },
            el('div', { class: 'sidebar__brand-logo', text: '🐱' }),
            el('div', { class: 'sidebar__brand-text' },
                el('div', { class: 'sidebar__brand-name', text: 'OnyxVpn' }),
                el('div', { class: 'sidebar__brand-tag', text: 'Admin Panel' }),
            ),
        ),
        el('nav', { class: 'sidebar__nav' },
            el('div', { class: 'sidebar__section-title', text: 'Навигация' }),
            ...navItems,
        ),
        el('div', { class: 'sidebar__footer' },
            el('div', { class: 'sidebar__mascot' },
                el('img', {
                    src: '/cat-companion.png',
                    alt: '',
                    class: 'sidebar__mascot-img',
                    onerror: "this.style.display='none'",
                }),
                el('div', { class: 'sidebar__mascot-text' },
                    el('div', { class: 'sidebar__mascot-title', text: 'Onyx рядом' }),
                    el('div', { class: 'sidebar__mascot-sub', text: 'v1.0 · 2026' }),
                ),
            ),
        ),
    );
}

function renderHeader() {
    const tgId = sessionStorage.getItem('admin_tg_id') || 'admin';
    const currentLabel = NAV_ITEMS.find(i => i.id === App.state.view)?.label || '';
    return el('header', { class: 'header' },
        el('div', { class: 'header__left' },
            el('div', { class: 'header__breadcrumb' },
                el('span', { text: 'OnyxVpn' }),
                el('span', { text: ' / ' }),
                el('span', { class: 'header__breadcrumb-current', text: currentLabel }),
            ),
        ),
        el('div', { class: 'header__right' },
            el('div', { class: 'header__user' },
                el('div', { class: 'header__user-avatar', text: 'A' }),
                el('span', { text: `ID ${tgId}` }),
            ),
            el('button', {
                class: 'btn btn--ghost btn--icon',
                title: 'Выйти',
                onClick: () => App.logout(),
            },
                el('span', { html: ICONS.logout }),
            ),
        ),
    );
}

function renderOverviewPage() {
    const metrics = App.state.metrics;
    const subscriptions = App.state.subscriptions;

    const metricsGrid = metrics
        ? el('div', { class: 'metrics' },
            el('div', { class: 'metric-card' },
                el('div', { class: 'metric-card__header' },
                    el('div', { class: 'metric-card__label', text: 'Пользователей' }),
                    el('div', { class: 'metric-card__icon', html: ICONS.users }),
                ),
                el('div', { class: 'metric-card__value', text: String(metrics.total_users) }),
            ),
            el('div', { class: 'metric-card' },
                el('div', { class: 'metric-card__header' },
                    el('div', { class: 'metric-card__label', text: 'Активных подписок' }),
                    el('div', { class: 'metric-card__icon', html: ICONS.zap }),
                ),
                el('div', { class: 'metric-card__value metric-card__value--accent', text: String(metrics.active_subscriptions) }),
            ),
            el('div', { class: 'metric-card' },
                el('div', { class: 'metric-card__header' },
                    el('div', { class: 'metric-card__label', text: 'Активных триалов' }),
                    el('div', { class: 'metric-card__icon', html: ICONS.gift }),
                ),
                el('div', { class: 'metric-card__value', text: String(metrics.active_trials) }),
            ),
            el('div', { class: 'metric-card metric-card--accent' },
                el('div', { class: 'metric-card__header' },
                    el('div', { class: 'metric-card__label', text: 'Онлайн сейчас' }),
                    el('div', { class: 'metric-card__icon' },
                        el('span', { class: 'activity-dot activity-dot--online' }),
                    ),
                ),
                el('div', { class: 'metric-card__value metric-card__value--success', text: String(metrics.active_now || 0) }),
                el('div', { class: 'metric-card__hint', text: 'handshake в последние 3 мин' }),
            ),
            el('div', { class: 'metric-card' },
                el('div', { class: 'metric-card__header' },
                    el('div', { class: 'metric-card__label', text: 'Пополнений' }),
                    el('div', { class: 'metric-card__icon', html: ICONS.dollar }),
                ),
                el('div', { class: 'metric-card__value', text: formatMoney(metrics.total_deposits_kopecks) }),
            ),
            el('div', { class: 'metric-card metric-card--traffic' },
                el('div', { class: 'metric-card__header' },
                    el('div', { class: 'metric-card__label', text: 'Трафик через VPN' }),
                    el('div', { class: 'metric-card__icon', html: ICONS.activity }),
                ),
                el('div', { class: 'metric-card__value', text: formatBytes((metrics.total_traffic_rx_bytes || 0) + (metrics.total_traffic_tx_bytes || 0)) }),
                el('div', { class: 'metric-card__hint' },
                    el('span', { text: `↓ ${formatBytes(metrics.total_traffic_rx_bytes || 0)}` }),
                    el('span', { class: 'metric-card__hint-sep', text: '·' }),
                    el('span', { text: `↑ ${formatBytes(metrics.total_traffic_tx_bytes || 0)}` }),
                ),
            ),
        )
        : renderMetricsSkeleton();

    const recentPanel = subscriptions.length > 0
        ? renderRecentActivity(subscriptions.slice(0, 5))
        : renderEmptySubscriptions();

    return el('div', { class: 'page' },
        el('div', { class: 'page__header' },
            el('div', {},
                el('h1', { class: 'page__title', text: 'Обзор' }),
                el('p', { class: 'page__subtitle', text: 'Ключевые метрики и активность сервиса' }),
            ),
        ),
        metricsGrid,
        recentPanel,
    );
}

function renderMetricsSkeleton() {
    return el('div', { class: 'metrics' },
        [1, 2, 3, 4].map(() => el('div', { class: 'metric-card' },
            el('div', { class: 'metric-card__header' },
                el('div', { class: 'skeleton', style: 'height:12px;width:60%' }),
            ),
            el('div', { class: 'skeleton skeleton--number' }),
        )),
    );
}

function renderRecentActivity(items) {
    const activityItems = items.map(sub =>
        el('div', { class: 'activity-item' },
            el('div', { class: 'activity-item__icon', html: ICONS.key }),
            el('div', { class: 'activity-item__content' },
                el('div', { class: 'activity-item__title', text: sub.username || `ID ${sub.user_tg_id}` }),
                el('div', { class: 'activity-item__subtitle', text: `Подписка · ${sub.plan_type || '—'} · ${formatMoney(sub.balance)}` }),
            ),
            el('div', { class: 'activity-item__time', text: formatRelative(sub.expires_at) }),
        )
    );

    return el('div', { class: 'panel' },
        el('div', { class: 'panel__header' },
            el('div', { class: 'panel__title-block' },
                el('h2', { class: 'panel__title', text: 'Последние подписки' }),
                el('div', { class: 'panel__subtitle', text: '5 самых свежих записей' }),
            ),
        ),
        el('div', { class: 'activity-list' }, ...activityItems),
    );
}

function renderEmptySubscriptions() {
    return el('div', { class: 'panel' },
        el('div', { class: 'panel__header' },
            el('div', { class: 'panel__title-block' },
                el('h2', { class: 'panel__title', text: 'Подписки' }),
                el('div', { class: 'panel__subtitle', text: 'Управление пользователями и их подписками' }),
            ),
        ),
        el('div', { class: 'empty' },
            el('img', {
                src: '/cat-companion.png',
                alt: '',
                class: 'empty__mascot',
                onerror: "this.onerror=null;this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22 fill=%22%23A78BFA%22%3E%3Ctext y=%22.9em%22 font-size=%2290%22%3E🐱%3C/text%3E%3C/svg%3E'",
            }),
            el('h3', { class: 'empty__title', text: 'Тут пока пусто' }),
            el('p', { class: 'empty__subtitle', text: 'Когда появятся первые пользователи — увидите их здесь' }),
        ),
    );
}

async function switchView(viewId) {
    App.state.view = viewId;
    App.state.page = 1;
    if (viewId === 'broadcasts') {
        await App.loadBroadcasts();
    }
    renderApp();
}

window.switchView = switchView;
window.renderApp = renderApp;

function renderApp() {
    const app = document.getElementById('app');
    if (!app) return;

    const token = sessionStorage.getItem('admin_token');
    if (!token) {
        app.innerHTML = '';
        app.appendChild(renderLogin());
        return;
    }

    app.innerHTML = '';
    app.appendChild(renderSidebar());
    app.appendChild(renderHeader());

    const main = el('main', { class: 'main' });
    if (App.state.view === 'overview') {
        main.appendChild(renderOverviewPage());
    } else if (App.state.view === 'subscriptions') {
        main.appendChild(renderSubscriptionsPage());
    } else if (App.state.view === 'broadcasts') {
        main.appendChild(renderBroadcastsPage());
    } else if (App.state.view === 'broadcast-detail') {
        main.appendChild(renderBroadcastDetailPage());
    }
    app.appendChild(main);
}

document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
