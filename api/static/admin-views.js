/* OnyxVpn Admin — Views: subscriptions, modals, telegram auth */

const BOT_USERNAME = 'Onyx_vpn24_bot';

// ─── Helpers (traffic) ─────────────────────────────────
function formatBytes(num) {
    if (num == null || num < 0) return '—';
    if (num < 1024) return `${num} B`;
    if (num < 1024 * 1024) return `${(num / 1024).toFixed(1)} KB`;
    if (num < 1024 * 1024 * 1024) return `${(num / (1024 * 1024)).toFixed(1)} MB`;
    if (num < 1024 * 1024 * 1024 * 1024) return `${(num / (1024 * 1024 * 1024)).toFixed(2)} GB`;
    return `${(num / (1024 * 1024 * 1024 * 1024)).toFixed(2)} TB`;
}

// "Онлайн" если handshake был в последние 3 минуты. Это совпадает с порогом
// в api/admin.py:active_now — WireGuard persistent keepalive 25 сек, так что
// 3 минуты — щедрый лимит на "живость" соединения.
function isOnlineNow(lastHandshakeIso) {
    if (!lastHandshakeIso) return false;
    const diffMs = Date.now() - new Date(lastHandshakeIso).getTime();
    return diffMs >= 0 && diffMs < 3 * 60 * 1000;
}

function renderTrafficCell(sub) {
    const rx = sub.total_bytes_received || 0;
    const tx = sub.total_bytes_sent || 0;
    const hasTraffic = rx > 0 || tx > 0;

    if (!hasTraffic) {
        return el('div', { class: 'traffic-cell traffic-cell--empty', text: '—' });
    }

    return el('div', { class: 'traffic-cell' },
        el('div', { class: 'traffic-cell__row' },
            el('span', { class: 'traffic-cell__arrow traffic-cell__arrow--down', text: '↓' }),
            el('span', { class: 'traffic-cell__value', text: formatBytes(rx) }),
        ),
        el('div', { class: 'traffic-cell__row' },
            el('span', { class: 'traffic-cell__arrow traffic-cell__arrow--up', text: '↑' }),
            el('span', { class: 'traffic-cell__value', text: formatBytes(tx) }),
        ),
    );
}

function renderActivityCell(sub) {
    const online = isOnlineNow(sub.last_handshake_at);

    if (online) {
        return el('div', { class: 'activity-cell' },
            el('span', { class: 'activity-dot activity-dot--online' }),
            el('span', { class: 'activity-cell__label', text: 'Онлайн' }),
        );
    }

    return el('div', { class: 'activity-cell' },
        el('span', { class: 'activity-dot activity-dot--offline' }),
        el('span', { class: 'activity-cell__label', text: formatRelative(sub.last_handshake_at) }),
    );
}

// Индикаторы того, какие уведомления об окончании триала/подписки уже отправлены.
// notified_24h/notified_1h приходят из api/admin.py:SubscriptionOut, читаются из User.
// Пусто для не-триал подписок — нет смысла показывать "не отправлено".
function renderNotificationBadges(sub) {
    const isTrial = sub.is_trial || sub.plan_type === 'trial';
    if (!isTrial) {
        return el('div', { class: 'notif-cell notif-cell--empty', text: '—' });
    }

    const badges = [];
    if (sub.notified_24h) {
        badges.push(el('span', {
            class: 'notif-badge notif-badge--sent',
            title: 'Уведомление «осталось 24 часа» отправлено',
        }, '🔔 24ч'));
    }
    if (sub.notified_1h) {
        badges.push(el('span', {
            class: 'notif-badge notif-badge--sent',
            title: 'Уведомление «осталось 1 час» отправлено',
        }, '🔔 1ч'));
    }

    if (badges.length === 0) {
        return el('div', { class: 'notif-cell' },
            el('span', {
                class: 'notif-badge notif-badge--pending',
                title: 'Уведомления ещё не отправлялись',
            }, '⏳ ожидает'),
        );
    }

    return el('div', { class: 'notif-cell' }, ...badges);
}

// ─── Status badge ───────────────────────────────────────
function getSubscriptionStatus(sub) {
    if (!sub.is_active) return { type: 'muted', label: 'Неактивна' };
    if (sub.expires_at && new Date(sub.expires_at) < new Date()) {
        return { type: 'danger', label: 'Истекла' };
    }
    if (sub.is_trial || sub.plan_type === 'trial') return { type: 'brand', label: 'Триал' };
    return { type: 'success', label: 'Активна' };
}

function statusBadge(sub) {
    const s = getSubscriptionStatus(sub);
    return el('span', { class: `badge badge--${s.type}` },
        el('span', { class: 'badge__dot' }),
        s.label,
    );
}

// ─── Filters ────────────────────────────────────────────
function renderFilters() {
    const onSearchInput = (e) => {
        clearTimeout(window._searchDebounce);
        window._searchDebounce = setTimeout(async () => {
            App.state.searchTgId = e.target.value.trim();
            App.state.page = 1;
            await App.loadSubscriptions();
            renderApp();
        }, 300);
    };

    const onStatusChange = (e) => {
        App.state.statusFilter = e.target.value;
        App.state.page = 1;
        App.loadSubscriptions().then(() => renderApp());
    };

    return el('div', { class: 'panel__filters' },
        el('div', { class: 'input input--search' },
            el('input', {
                type: 'search',
                placeholder: 'Поиск по Telegram ID',
                value: App.state.searchTgId,
                onInput: onSearchInput,
            }),
        ),
        el('select', { class: 'select', onChange: onStatusChange },
            el('option', { value: '', selected: !App.state.statusFilter }, 'Все статусы'),
            el('option', { value: 'active', selected: App.state.statusFilter === 'active' }, 'Активные'),
            el('option', { value: 'trial', selected: App.state.statusFilter === 'trial' }, 'Триал'),
            el('option', { value: 'expired', selected: App.state.statusFilter === 'expired' }, 'Истекшие'),
        ),
    );
}

// ─── Subscriptions table ────────────────────────────────
function renderSubscriptionsRows(items) {
    if (items.length === 0) {
        return el('tr', {},
            el('td', { colspan: '10', class: 'table__empty' },
                el('div', { class: 'empty empty--inline' },
                    el('p', { class: 'empty__subtitle', text: 'Нет подписок по выбранным фильтрам' }),
                ),
            ),
        );
    }

    return items.map(sub => {
        const initials = getInitials(sub.username || `#${sub.user_tg_id}`);
        return el('tr', { class: 'subscriptions-row' },
            el('td', { class: 'table__date', text: `#${sub.id}` }),
            el('td', {},
                el('div', { class: 'table__user' },
                    el('div', { class: 'table__avatar', text: initials }),
                    el('div', { class: 'table__user-info' },
                        el('span', { class: 'table__user-name', text: sub.username || 'Без имени' }),
                        el('span', { class: 'table__user-id', text: `ID ${sub.user_tg_id}` }),
                    ),
                ),
            ),
            el('td', { class: 'table__amount', text: formatMoney(sub.balance || 0) }),
            el('td', { class: 'table__date', text: sub.plan_type || '—' }),
            el('td', {}, statusBadge(sub)),
            el('td', { class: 'table__date', text: formatDate(sub.expires_at) }),
            renderNotificationBadges(sub),
            renderTrafficCell(sub),
            renderActivityCell(sub),
            el('td', { class: 'table__actions' },
                el('button', {
                    class: 'btn btn--secondary btn--icon btn--sm',
                    title: 'Детали трафика',
                    onClick: () => App.openModal({ type: 'traffic', subscription: sub }),
                },
                    el('span', { html: ICONS.activity }),
                ),
                el('button', {
                    class: 'btn btn--secondary btn--icon btn--sm',
                    title: 'Продлить',
                    onClick: () => App.openModal({ type: 'extend', subscription: sub }),
                },
                    el('span', { html: ICONS.clock }),
                ),
                el('button', {
                    class: 'btn btn--secondary btn--icon btn--sm',
                    title: 'Пополнить баланс',
                    onClick: () => App.openModal({ type: 'topup', subscription: sub }),
                },
                    el('span', { html: ICONS.plus }),
                ),
                el('button', {
                    class: 'btn btn--danger btn--icon btn--sm',
                    title: 'Отозвать подписку',
                    onClick: () => App.openModal({
                        type: 'confirm',
                        title: 'Отозвать подписку?',
                        message: `Подписка пользователя ${sub.username || `#${sub.user_tg_id}`} будет деактивирована. Это действие нельзя отменить.`,
                        confirmLabel: 'Отозвать',
                        confirmVariant: 'danger',
                        onConfirm: async () => {
                            try {
                                await App.revokeSubscription(sub.id);
                                App.toast('success', 'Готово', 'Подписка отозвана');
                                await App.loadSubscriptions();
                                renderApp();
                            } catch (err) {
                                App.toast('error', 'Ошибка', err.message);
                            }
                            },
                    }),
                }),
            ),
        );
    });
}

function renderSkeletonRows() {
    return [1, 2, 3, 4, 5].map(() =>
        el('div', { class: 'skeleton-row' },
            el('div', { class: 'skeleton skeleton-row__avatar' }),
            el('div', { class: 'skeleton-row__lines' },
                el('div', { class: 'skeleton skeleton--text', style: 'width:30%' }),
                el('div', { class: 'skeleton skeleton--text', style: 'width:50%' }),
            ),
        )
    );
}

function renderPagination() {
    const total = App.state.total;
    const page = App.state.page;
    const perPage = App.state.perPage;
    const totalPages = Math.max(1, Math.ceil(total / perPage));
    const start = total === 0 ? 0 : (page - 1) * perPage + 1;
    const end = Math.min(total, page * perPage);

    const goPage = async (p) => {
        App.state.page = p;
        await App.loadSubscriptions();
        renderApp();
    };

    return el('div', { class: 'pagination' },
        el('div', { class: 'pagination__info', text: `${start}–${end} из ${total}` }),
        el('div', { class: 'pagination__controls' },
            el('button', {
                class: 'btn btn--secondary btn--icon btn--sm',
                disabled: page <= 1,
                onClick: () => goPage(page - 1),
            },
                el('span', { html: ICONS.chevronLeft }),
            ),
            el('span', { class: 'pagination__info', text: `Стр. ${page} из ${totalPages}` }),
            el('button', {
                class: 'btn btn--secondary btn--icon btn--sm',
                disabled: page >= totalPages,
                onClick: () => goPage(page + 1),
            },
                el('span', { html: ICONS.chevronRight }),
            ),
        ),
    );
}

function renderSubscriptionsPage() {
    const subscriptions = App.state.subscriptions;
    const loading = App.state.loading.subscriptions;

    return el('div', { class: 'page' },
        el('div', { class: 'page__header' },
            el('div', {},
                el('h1', { class: 'page__title', text: 'Подписки' }),
                el('p', { class: 'page__subtitle', text: 'Управление подписками и балансами пользователей' }),
            ),
            el('div', { class: 'page__actions' },
                el('button', {
                    class: 'btn btn--danger btn--sm',
                    onClick: () => App.openModal({
                        type: 'confirm',
                        title: 'Очистить все подписки?',
                        message: 'Будут деактивированы ВСЕ подписки в системе. Это действие нельзя отменить.',
                        confirmLabel: 'Удалить всё',
                        confirmVariant: 'danger',
                        requireTyping: 'DELETE_ALL_SUBSCRIPTIONS',
                        onConfirm: async () => {
                            try {
                                const result = await App.clearAllSubscriptions();
                                App.toast('success', 'Готово', `Удалено подписок: ${result.deleted_count || 0}`);
                                await Promise.all([App.loadMetrics(), App.loadSubscriptions()]);
                                renderApp();
                            } catch (err) {
                                App.toast('error', 'Ошибка', err.message);
                            }
                        },
                    }),
                },
                    el('span', { html: ICONS.trash }),
                    el('span', { text: 'Очистить все' }),
                ),
            ),
        ),
        el('div', { class: 'panel' },
            el('div', { class: 'panel__header' },
                el('div', { class: 'panel__title-block' },
                    el('h2', { class: 'panel__title', text: 'Список пользователей' }),
                    el('div', { class: 'panel__subtitle', text: 'Поиск, фильтрация и действия' }),
                ),
                renderFilters(),
            ),
            el('div', { class: 'table-wrapper' },
                el('table', { class: 'table' },
                    el('thead', {},
                        el('tr', {},
                            el('th', { text: 'ID' }),
                            el('th', { text: 'Пользователь' }),
                            el('th', { text: 'Баланс' }),
                            el('th', { text: 'Тариф' }),
                            el('th', { text: 'Статус' }),
                            el('th', { text: 'Истекает' }),
                            el('th', { text: 'Уведомления' }),
                            el('th', { text: 'Трафик' }),
                            el('th', { text: 'Активность' }),
                            el('th', {}, ''),
                        ),
                    ),
                    loading && subscriptions.length === 0
                        ? el('tbody', {}, ...renderSkeletonRows())
                        : el('tbody', {}, ...renderSubscriptionsRows(subscriptions)),
                ),
            ),
            !loading || subscriptions.length > 0 ? renderPagination() : null,
        ),
    );
}

// ─── Modals ─────────────────────────────────────────────
function renderExtendModal(modal) {
    const sub = modal.subscription;
    const input = el('input', {
        type: 'number',
        class: 'input',
        min: '1',
        max: '365',
        value: '30',
        placeholder: '30',
        id: 'extend-days',
    });

    const submit = async () => {
        const days = parseInt(input.value, 10);
        if (!days || days < 1) {
            App.toast('warning', 'Проверь данные', 'Введи количество дней от 1');
            return;
        }
        const btn = document.getElementById('modal-submit');
        if (btn) btn.classList.add('btn--loading');
        try {
            await App.extendSubscription(sub.id, days);
            App.toast('success', 'Готово', `Подписка продлена на ${days} дн.`);
            await Promise.all([App.loadMetrics(), App.loadSubscriptions()]);
            App.closeModal();
        } catch (err) {
            App.toast('error', 'Ошибка', err.message);
        } finally {
            if (btn) btn.classList.remove('btn--loading');
        }
    };

    setTimeout(() => input.focus(), 50);

    return el('div', { class: 'modal-overlay', onClick: (e) => e.target === e.currentTarget && App.closeModal() },
        el('div', { class: 'modal' },
            el('button', { class: 'modal__close', onClick: () => App.closeModal(), html: ICONS.close }),
            el('h2', { class: 'modal__title', text: 'Продлить подписку' }),
            el('div', { class: 'modal__user-info' },
                el('strong', { text: sub.username || `ID ${sub.user_tg_id}` }),
                el('span', { text: ` · ID ${sub.user_tg_id} · тариф: ${sub.plan_type || '—'}` }),
            ),
            el('div', { class: 'modal__body' },
                el('label', { class: 'input-label', for: 'extend-days' },
                    el('span', { text: 'На сколько дней продлить' }),
                    input,
                ),
                el('div', { class: 'input-hint', text: 'Можно указать от 1 до 365 дней' }),
            ),
            el('div', { class: 'modal__footer' },
                el('button', { class: 'btn btn--ghost', onClick: () => App.closeModal(), text: 'Отмена' }),
                el('button', { class: 'btn btn--primary', id: 'modal-submit', onClick: submit, text: 'Продлить' }),
            ),
        ),
    );
}

function renderTopupModal(modal) {
    const sub = modal.subscription;
    const amountInput = el('input', {
        type: 'number',
        class: 'input',
        min: '1',
        step: '1',
        value: '100',
        placeholder: '100',
        id: 'topup-amount',
    });
    const commentInput = el('input', {
        type: 'text',
        class: 'input',
        maxlength: '200',
        placeholder: 'Например: компенсация за простой',
        id: 'topup-comment',
    });

    const submit = async () => {
        const amount = parseInt(amountInput.value, 10);
        const comment = commentInput.value.trim();
        if (!amount || amount < 1) {
            App.toast('warning', 'Проверь данные', 'Введи сумму больше 0');
            return;
        }
        const btn = document.getElementById('modal-submit');
        if (btn) btn.classList.add('btn--loading');
        try {
            const result = await App.topUpBalance(sub.user_tg_id, amount, comment);
            App.toast('success', 'Готово', `Баланс пополнен на ${amount} ₽`);
            await App.loadSubscriptions();
            App.closeModal();
            if (result?.new_balance !== undefined) {
                setTimeout(() => App.toast('info', 'Новый баланс', `${result.new_balance / 100} ₽`), 200);
            }
        } catch (err) {
            App.toast('error', 'Ошибка', err.message);
        } finally {
            if (btn) btn.classList.remove('btn--loading');
        }
    };

    setTimeout(() => amountInput.focus(), 50);

    return el('div', { class: 'modal-overlay', onClick: (e) => e.target === e.currentTarget && App.closeModal() },
        el('div', { class: 'modal' },
            el('button', { class: 'modal__close', onClick: () => App.closeModal(), html: ICONS.close }),
            el('h2', { class: 'modal__title', text: 'Пополнить баланс' }),
            el('div', { class: 'modal__user-info' },
                el('strong', { text: sub.username || `ID ${sub.user_tg_id}` }),
                el('span', { text: ` · текущий баланс: ${formatMoney(sub.balance || 0)}` }),
            ),
            el('div', { class: 'modal__body' },
                el('label', { class: 'input-label', for: 'topup-amount' },
                    el('span', { text: 'Сумма пополнения (₽)' }),
                    amountInput,
                ),
                el('label', { class: 'input-label', for: 'topup-comment' },
                    el('span', { text: 'Комментарий (необязательно)' }),
                    commentInput,
                ),
            ),
            el('div', { class: 'modal__footer' },
                el('button', { class: 'btn btn--ghost', onClick: () => App.closeModal(), text: 'Отмена' }),
                el('button', { class: 'btn btn--primary', id: 'modal-submit', onClick: submit, text: 'Начислить' }),
            ),
        ),
    );
}

function renderConfirmModal(modal) {
    const confirmInput = modal.requireTyping
        ? el('input', {
            type: 'text',
            class: 'input',
            placeholder: modal.requireTyping,
            id: 'confirm-input',
        })
        : null;

    const submit = async () => {
        if (modal.requireTyping && confirmInput.value.trim() !== modal.requireTyping) {
            App.toast('warning', 'Не совпадает', `Введи "${modal.requireTyping}" для подтверждения`);
            return;
        }
        const btn = document.getElementById('modal-submit');
        if (btn) btn.classList.add('btn--loading');
        try {
            await modal.onConfirm();
        } catch (err) {
            App.toast('error', 'Ошибка', err.message);
        } finally {
            if (btn) btn.classList.remove('btn--loading');
        }
    };

    const variantClass = modal.confirmVariant === 'danger' ? 'btn--danger' : 'btn--primary';

    return el('div', { class: 'modal-overlay', onClick: (e) => e.target === e.currentTarget && App.closeModal() },
        el('div', { class: 'modal' },
            el('button', { class: 'modal__close', onClick: () => App.closeModal(), html: ICONS.close }),
            el('h2', { class: 'modal__title', text: modal.title }),
            el('p', { class: 'modal__subtitle', text: modal.message }),
            confirmInput
                ? el('div', { class: 'modal__body' },
                    el('label', { class: 'input-label', for: 'confirm-input' },
                        el('span', { html: `Введи <code>${modal.requireTyping}</code> для подтверждения` }),
                        confirmInput,
                    ),
                )
                : null,
            el('div', { class: 'modal__footer' },
                el('button', { class: 'btn btn--ghost', onClick: () => App.closeModal(), text: 'Отмена' }),
                el('button', { class: `btn ${variantClass}`, id: 'modal-submit', onClick: submit, text: modal.confirmLabel || 'Подтвердить' }),
            ),
        ),
    );
}

function renderTrafficModal(modal) {
    const sub = modal.subscription;
    const tgId = sub.user_tg_id;
    const container = el('div', { class: 'traffic-modal__content' });

    // Заполняем контейнер loading-состоянием, потом подгружаем реальные данные
    container.appendChild(
        el('div', { class: 'traffic-modal__loading' },
            el('div', { class: 'spinner' }),
            el('span', { text: 'Загружаю данные трафика…' }),
        ),
    );

    const load = async () => {
        try {
            const data = await App.loadUserTraffic(tgId);
            container.innerHTML = '';
            renderTrafficData(container, sub, data);
        } catch (err) {
            container.innerHTML = '';
            container.appendChild(
                el('div', { class: 'traffic-modal__error' },
                    el('p', { class: 'traffic-modal__error-title', text: 'Не удалось загрузить трафик' }),
                    el('p', { class: 'traffic-modal__error-message', text: err.message }),
                ),
            );
        }
    };

    // Запускаем загрузку после того, как DOM готов
    setTimeout(load, 50);

    return el('div', { class: 'modal-overlay', onClick: (e) => e.target === e.currentTarget && App.closeModal() },
        el('div', { class: 'modal modal--wide' },
            el('button', { class: 'modal__close', onClick: () => App.closeModal(), html: ICONS.close }),
            el('h2', { class: 'modal__title', text: 'Трафик пользователя' }),
            el('div', { class: 'modal__user-info' },
                el('strong', { text: sub.username || `ID ${tgId}` }),
                el('span', { text: ` · ID ${tgId}` }),
            ),
            container,
            el('div', { class: 'modal__footer' },
                el('button', { class: 'btn btn--ghost', onClick: () => App.closeModal(), text: 'Закрыть' }),
                el('button', { class: 'btn btn--secondary', onClick: load, html: `${ICONS.activity}<span>Обновить</span>` }),
            ),
        ),
    );
}

function renderTrafficData(container, sub, data) {
    const rx = data.total_bytes_received || 0;
    const tx = data.total_bytes_sent || 0;
    const online = isOnlineNow(data.last_handshake_at);

    container.appendChild(
        el('div', { class: 'traffic-modal__stats' },
            // Большая карточка скачанного
            el('div', { class: 'traffic-stat traffic-stat--down' },
                el('div', { class: 'traffic-stat__label', text: 'Скачано ↓' }),
                el('div', { class: 'traffic-stat__value', text: formatBytes(rx) }),
                el('div', { class: 'traffic-stat__raw', text: `${rx.toLocaleString('ru-RU')} B` }),
            ),
            // Большая карточка загруженного
            el('div', { class: 'traffic-stat traffic-stat--up' },
                el('div', { class: 'traffic-stat__label', text: 'Загружено ↑' }),
                el('div', { class: 'traffic-stat__value', text: formatBytes(tx) }),
                el('div', { class: 'traffic-stat__raw', text: `${tx.toLocaleString('ru-RU')} B` }),
            ),
        ),
    );

    // Активность / онлайн
    container.appendChild(
        el('div', { class: 'traffic-modal__activity' },
            el('div', { class: 'traffic-modal__activity-row' },
                el('span', {
                    class: `activity-dot ${online ? 'activity-dot--online' : 'activity-dot--offline'}`,
                }),
                el('div', {},
                    el('div', { class: 'traffic-modal__activity-title', text: online ? 'Онлайн' : 'Не в сети' }),
                    el('div', { class: 'traffic-modal__activity-sub', text: online ? 'Подключен в последние 3 минуты' : `Последний трафик: ${formatRelative(data.last_handshake_at)}` }),
                ),
            ),
            data.last_activity_at && data.last_activity_at !== data.last_handshake_at
                ? el('div', { class: 'traffic-modal__activity-row' },
                    el('span', { class: 'traffic-modal__activity-icon', html: ICONS.activity }),
                    el('div', {},
                        el('div', { class: 'traffic-modal__activity-title', text: 'Активность' }),
                        el('div', { class: 'traffic-modal__activity-sub', text: formatRelative(data.last_activity_at) }),
                    ),
                )
                : null,
        ),
    );

    // Информация о подписке и балансе
    container.appendChild(
        el('div', { class: 'traffic-modal__details' },
            el('div', { class: 'traffic-modal__detail' },
                el('div', { class: 'traffic-modal__detail-label', text: 'Баланс' }),
                el('div', { class: 'traffic-modal__detail-value', text: formatMoney(sub.balance || 0) }),
            ),
            el('div', { class: 'traffic-modal__detail' },
                el('div', { class: 'traffic-modal__detail-label', text: 'Подписка' }),
                el('div', { class: 'traffic-modal__detail-value' },
                    statusBadge(sub),
                ),
            ),
            el('div', { class: 'traffic-modal__detail' },
                el('div', { class: 'traffic-modal__detail-label', text: 'Тариф' }),
                el('div', { class: 'traffic-modal__detail-value', text: sub.plan_type || '—' }),
            ),
            el('div', { class: 'traffic-modal__detail' },
                el('div', { class: 'traffic-modal__detail-label', text: 'Истекает' }),
                el('div', { class: 'traffic-modal__detail-value', text: formatDate(sub.expires_at) }),
            ),
        ),
    );

    // Публичный ключ (усечённый)
    const pubKey = sub.uuid || '';
    const shortKey = pubKey.length > 24 ? `${pubKey.slice(0, 16)}…${pubKey.slice(-8)}` : pubKey;
    container.appendChild(
        el('div', { class: 'traffic-modal__key' },
            el('div', { class: 'traffic-modal__detail-label', text: 'Публичный ключ WireGuard' }),
            el('div', {
                class: 'traffic-modal__key-value',
                title: pubKey,
                text: shortKey || '—',
            }),
        ),
    );

    // Если данных нет вообще — покажем пояснение
    if (rx === 0 && tx === 0 && !data.last_handshake_at) {
        container.appendChild(
            el('div', { class: 'traffic-modal__empty' },
                el('p', { text: 'Пользователь ещё не использовал VPN. Данные появятся после первого подключения.' }),
            ),
        );
    }
}

function renderModal() {
    const modal = App.state.modal;
    if (!modal) return null;

    if (modal.type === 'extend') return renderExtendModal(modal);
    if (modal.type === 'topup') return renderTopupModal(modal);
    if (modal.type === 'confirm') return renderConfirmModal(modal);
    if (modal.type === 'traffic') return renderTrafficModal(modal);
    if (modal.type === 'broadcast-create') return renderBroadcastCreateModal(modal);
    return null;
}

// ─── Telegram auth ──────────────────────────────────────
async function initTelegramWidget() {
    const wrapper = document.getElementById('telegram-login-widget');
    if (!wrapper) return;

    wrapper.setAttribute('data-telegram-login', BOT_USERNAME);
    wrapper.setAttribute('data-size', 'large');
    wrapper.setAttribute('data-onauth', 'onTelegramAuth');
    wrapper.setAttribute('data-request-access', 'write');

    // The telegram-widget.js script may not have re-scanned the DOM after our render,
    // so re-inject a script tag to trigger widget creation.
    const existing = document.querySelector('script[data-telegram-widget-reloaded]');
    if (!existing) {
        const s = document.createElement('script');
        s.src = 'https://telegram.org/js/telegram-widget.js?22';
        s.async = true;
        s.setAttribute('data-telegram-widget-reloaded', 'true');
        s.onerror = () => {
            const errorEl = document.getElementById('login-error');
            if (errorEl) {
                errorEl.textContent = 'Не удалось загрузить Telegram-виджет. Проверь подключение к интернету.';
                errorEl.classList.add('login__error--visible');
            }
        };
        document.body.appendChild(s);
    }
}

window.onTelegramAuth = async function (user) {
    const errorEl = document.getElementById('login-error');
    if (errorEl) errorEl.classList.remove('login__error--visible');

    try {
        const res = await fetch('/api/admin/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(user),
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Не удалось войти');
        }

        const data = await res.json();
        if (data.token) {
            sessionStorage.setItem('admin_token', data.token);
            sessionStorage.setItem('admin_tg_id', String(user.id));
        }

        window.location.reload();
    } catch (err) {
        if (errorEl) {
            errorEl.textContent = err.message || 'Ошибка авторизации';
            errorEl.classList.add('login__error--visible');
        }
    }
};

// ─── Broadcasts ────────────────────────────────────────
// Локализованные имена сегментов для UI.
// Ключи — lowercase значения из enum (api/admin.py сериализует .value).
const BROADCAST_SEGMENT_LABELS = {
    'trial': 'На пробном тарифе',
    'paid': 'На платном тарифе',
    'trial_expiring_24h': 'Триал истекает через 24ч',
    'trial_expiring_1h': 'Триал истекает через 1ч',
    'expired': 'Истёкшая подписка',
    'inactive_7d': 'Неактивные 7+ дней',
    'with_balance': 'С положительным балансом',
    'all': 'Все пользователи',
};

const BROADCAST_STATUS_LABELS = {
    'draft': 'Черновик',
    'sending': 'Отправляется',
    'completed': 'Завершена',
    'canceled': 'Отменена',
    'failed': 'Ошибка',
};

const BROADCAST_STATUS_TYPES = {
    'draft': 'muted',
    'sending': 'info',
    'completed': 'success',
    'canceled': 'warning',
    'failed': 'danger',
};

const DELIVERY_STATUS_LABELS = {
    'pending': 'Ожидает',
    'sent': 'Отправлено',
    'failed': 'Ошибка',
    'blocked': 'Заблокирован',
};

const DELIVERY_STATUS_TYPES = {
    'pending': 'muted',
    'sent': 'success',
    'failed': 'danger',
    'blocked': 'warning',
};

function broadcastStatusBadge(status) {
    const label = BROADCAST_STATUS_LABELS[status] || status;
    const type = BROADCAST_STATUS_TYPES[status] || 'muted';
    return el('span', { class: `badge badge--${type}` },
        el('span', { class: 'badge__dot' }),
        label,
    );
}

function deliveryStatusBadge(status) {
    const label = DELIVERY_STATUS_LABELS[status] || status;
    const type = DELIVERY_STATUS_TYPES[status] || 'muted';
    return el('span', { class: `badge badge--${type}` }, label);
}

function renderBroadcastsPage() {
    const campaigns = App.state.broadcasts || [];
    const loading = App.state.loadingBroadcasts;

    return el('div', { class: 'page' },
        el('div', { class: 'page__header' },
            el('div', {},
                el('h1', { class: 'page__title', text: 'Рассылки' }),
                el('p', { class: 'page__subtitle', text: 'Отправка сообщений пользователям через бота по выбранному сегменту' }),
            ),
            el('div', { class: 'page__actions' },
                el('button', {
                    class: 'btn btn--primary',
                    onClick: async () => {
                        await App.loadBroadcastSegmentStats();
                        App.openModal({ type: 'broadcast-create' });
                    },
                },
                    el('span', { html: ICONS.plus }),
                    el('span', { text: 'Новая рассылка' }),
                ),
            ),
        ),
        el('div', { class: 'panel' },
            el('div', { class: 'panel__header' },
                el('div', { class: 'panel__title-block' },
                    el('h2', { class: 'panel__title', text: 'Кампании' }),
                    el('div', { class: 'panel__subtitle', text: 'Список созданных рассылок' }),
                ),
            ),
            el('div', { class: 'table-wrapper' },
                el('table', { class: 'table' },
                    el('thead', {},
                        el('tr', {},
                            el('th', { text: 'Название' }),
                            el('th', { text: 'Сегмент' }),
                            el('th', { text: 'Статус' }),
                            el('th', { text: 'Прогресс' }),
                            el('th', { text: 'Создана' }),
                            el('th', {}, ''),
                        ),
                    ),
                    loading && campaigns.length === 0
                        ? el('tbody', {},
                            el('tr', {},
                                el('td', { colspan: '6', class: 'table__empty' },
                                    el('div', { class: 'empty empty--inline' },
                                        el('p', { class: 'empty__subtitle', text: 'Загружаю кампании…' }),
                                    ),
                                ),
                            ),
                        )
                        : campaigns.length === 0
                            ? el('tbody', {},
                                el('tr', {},
                                    el('td', { colspan: '6', class: 'table__empty' },
                                        el('div', { class: 'empty empty--inline' },
                                            el('p', { class: 'empty__subtitle', text: 'Пока нет ни одной рассылки. Создай первую.' }),
                                        ),
                                    ),
                                ),
                            )
                            : el('tbody', {}, ...renderBroadcastRows(campaigns)),
                ),
            ),
        ),
    );
}

function renderBroadcastRows(items) {
    return items.map(c => {
        const total = c.total_recipients || 0;
        const sent = c.sent_count || 0;
        const failed = c.failed_count || 0;
        const blocked = c.blocked_count || 0;
        const done = sent + failed + blocked;
        const pct = total > 0 ? Math.round((done / total) * 100) : 0;

        return el('tr', { class: 'broadcast-row' },
            el('td', {},
                el('div', { class: 'broadcast-row__title', text: c.title }),
                c.message_text
                    ? el('div', {
                        class: 'broadcast-row__preview',
                        text: c.message_text.length > 80 ? c.message_text.slice(0, 80) + '…' : c.message_text,
                    })
                    : null,
            ),
            el('td', { class: 'broadcast-row__segment', text: BROADCAST_SEGMENT_LABELS[c.target_segment] || c.target_segment }),
            el('td', {}, broadcastStatusBadge(c.status)),
            el('td', {},
                el('div', { class: 'progress' },
                    el('div', {
                        class: `progress__bar ${c.status === 'completed' ? 'progress__bar--done' : ''}`,
                        style: `width: ${pct}%`,
                    }),
                ),
                el('div', { class: 'progress__label', text: `${done} / ${total} · ✓${sent} ✗${failed} ⊘${blocked}` }),
            ),
            el('td', { class: 'table__date', text: formatDate(c.created_at) }),
            el('td', { class: 'table__actions' },
                el('button', {
                    class: 'btn btn--secondary btn--icon btn--sm',
                    title: 'Детали',
                    onClick: async () => {
                        App.state.view = 'broadcast-detail';
                        await App.loadBroadcastDetail(c.id);
                        await App.loadBroadcastDeliveries(c.id);
                        renderApp();
                    },
                },
                    el('span', { html: ICONS.eye }),
                ),
                c.status === 'draft'
                    ? el('button', {
                        class: 'btn btn--primary btn--icon btn--sm',
                        title: 'Запустить рассылку',
                        onClick: () => App.openModal({
                            type: 'confirm',
                            title: 'Запустить рассылку?',
                            message: `Сообщение будет отправлено ${total} пользователям сегмента «${BROADCAST_SEGMENT_LABELS[c.target_segment] || c.target_segment}».`,
                            confirmLabel: 'Запустить',
                            confirmVariant: 'primary',
                            onConfirm: async () => {
                                try {
                                    await App.startBroadcast(c.id);
                                    App.toast('success', 'Запущено', 'Рассылка выполняется в фоне');
                                    await App.loadBroadcasts();
                                    renderApp();
                                } catch (err) {
                                    App.toast('error', 'Ошибка', err.message);
                                }
                            },
                        }),
                    },
                        el('span', { html: ICONS.play }),
                    )
                    : null,
                c.status === 'draft' || c.status === 'canceled' || c.status === 'failed'
                    ? el('button', {
                        class: 'btn btn--danger btn--icon btn--sm',
                        title: 'Удалить',
                        onClick: () => App.openModal({
                            type: 'confirm',
                            title: 'Удалить рассылку?',
                            message: `Кампания «${c.title}» будет удалена вместе со статистикой доставок.`,
                            confirmLabel: 'Удалить',
                            confirmVariant: 'danger',
                            onConfirm: async () => {
                                try {
                                    await App.deleteBroadcast(c.id);
                                    App.toast('success', 'Удалено', 'Рассылка удалена');
                                    await App.loadBroadcasts();
                                    renderApp();
                                } catch (err) {
                                    App.toast('error', 'Ошибка', err.message);
                                }
                            },
                        }),
                    },
                        el('span', { html: ICONS.trash }),
                    )
                    : null,
            ),
        );
    });
}

function renderBroadcastDetailPage() {
    const c = App.state.broadcast;
    if (!c) {
        return el('div', { class: 'page' },
            el('div', { class: 'empty' },
                el('p', { class: 'empty__subtitle', text: 'Кампания не найдена' }),
                el('button', {
                    class: 'btn btn--secondary',
                    onClick: () => { App.state.view = 'broadcasts'; renderApp(); },
                    text: '← К списку',
                }),
            ),
        );
    }

    const total = c.total_recipients || 0;
    const sent = c.sent_count || 0;
    const failed = c.failed_count || 0;
    const blocked = c.blocked_count || 0;
    const pending = Math.max(0, total - sent - failed - blocked);
    const byStatus = App.state.broadcastDeliveriesByStatus || {};

    return el('div', { class: 'page' },
        el('div', { class: 'page__header' },
            el('div', {},
                el('button', {
                    class: 'page__back',
                    onClick: async () => {
                        App.state.view = 'broadcasts';
                        App.state.broadcast = null;
                        await App.loadBroadcasts();
                        renderApp();
                    },
                }, '← К списку рассылок'),
                el('h1', { class: 'page__title', text: c.title }),
                el('div', { class: 'page__meta' },
                    el('span', {}, broadcastStatusBadge(c.status)),
                    el('span', { class: 'page__meta-sep', text: '·' }),
                    el('span', { text: BROADCAST_SEGMENT_LABELS[c.target_segment] || c.target_segment }),
                    el('span', { class: 'page__meta-sep', text: '·' }),
                    el('span', { text: `Создана ${formatDate(c.created_at)}` }),
                ),
            ),
            el('div', { class: 'page__actions' },
                c.status === 'draft'
                    ? el('button', {
                        class: 'btn btn--primary',
                        onClick: () => App.openModal({
                            type: 'confirm',
                            title: 'Запустить рассылку?',
                            message: `Сообщение будет отправлено ${total} пользователям.`,
                            confirmLabel: 'Запустить',
                            confirmVariant: 'primary',
                            onConfirm: async () => {
                                try {
                                    await App.startBroadcast(c.id);
                                    App.toast('success', 'Запущено', 'Рассылка выполняется в фоне');
                                    await Promise.all([App.loadBroadcastDetail(c.id), App.loadBroadcastDeliveries(c.id)]);
                                    renderApp();
                                } catch (err) {
                                    App.toast('error', 'Ошибка', err.message);
                                }
                            },
                        }),
                    }, el('span', { text: 'Запустить' }))
                    : null,
                c.status === 'sending'
                    ? el('button', {
                        class: 'btn btn--danger',
                        onClick: () => App.openModal({
                            type: 'confirm',
                            title: 'Отменить рассылку?',
                            message: 'Уже отправленные сообщения не отзовутся. Неотправленные будут пропущены.',
                            confirmLabel: 'Отменить',
                            confirmVariant: 'danger',
                            onConfirm: async () => {
                                try {
                                    await App.cancelBroadcast(c.id);
                                    App.toast('success', 'Отменено', 'Рассылка помечена как отменённая');
                                    await Promise.all([App.loadBroadcastDetail(c.id), App.loadBroadcastDeliveries(c.id)]);
                                    renderApp();
                                } catch (err) {
                                    App.toast('error', 'Ошибка', err.message);
                                }
                            },
                        }),
                    }, el('span', { text: 'Отменить' }))
                    : null,
                (c.status === 'draft' || c.status === 'canceled' || c.status === 'failed')
                    ? el('button', {
                        class: 'btn btn--danger',
                        onClick: () => App.openModal({
                            type: 'confirm',
                            title: 'Удалить рассылку?',
                            message: 'Кампания и её статистика будут удалены безвозвратно.',
                            confirmLabel: 'Удалить',
                            confirmVariant: 'danger',
                            onConfirm: async () => {
                                try {
                                    await App.deleteBroadcast(c.id);
                                    App.toast('success', 'Удалено', 'Рассылка удалена');
                                    App.state.view = 'broadcasts';
                                    App.state.broadcast = null;
                                    await App.loadBroadcasts();
                                    renderApp();
                                } catch (err) {
                                    App.toast('error', 'Ошибка', err.message);
                                }
                            },
                        }),
                    }, el('span', { text: 'Удалить' }))
                    : null,
            ),
        ),
        // Карточка прогресса
        el('div', { class: 'broadcast-stats' },
            el('div', { class: 'broadcast-stat broadcast-stat--total' },
                el('div', { class: 'broadcast-stat__label', text: 'Получателей' }),
                el('div', { class: 'broadcast-stat__value', text: String(total) }),
            ),
            el('div', { class: 'broadcast-stat broadcast-stat--sent' },
                el('div', { class: 'broadcast-stat__label', text: 'Отправлено' }),
                el('div', { class: 'broadcast-stat__value', text: String(sent) }),
            ),
            el('div', { class: 'broadcast-stat broadcast-stat--failed' },
                el('div', { class: 'broadcast-stat__label', text: 'Ошибка' }),
                el('div', { class: 'broadcast-stat__value', text: String(failed) }),
            ),
            el('div', { class: 'broadcast-stat broadcast-stat--blocked' },
                el('div', { class: 'broadcast-stat__label', text: 'Заблокировали бота' }),
                el('div', { class: 'broadcast-stat__value', text: String(blocked) }),
            ),
            el('div', { class: 'broadcast-stat broadcast-stat--pending' },
                el('div', { class: 'broadcast-stat__label', text: 'В очереди' }),
                el('div', { class: 'broadcast-stat__value', text: String(pending) }),
            ),
        ),
        // Текст сообщения
        el('div', { class: 'panel' },
            el('div', { class: 'panel__header' },
                el('div', { class: 'panel__title-block' },
                    el('h2', { class: 'panel__title', text: 'Текст сообщения' }),
                ),
            ),
            el('div', { class: 'broadcast-message' },
                el('pre', { class: 'broadcast-message__text', text: c.message_text }),
            ),
        ),
        // Таблица получателей
        el('div', { class: 'panel' },
            el('div', { class: 'panel__header' },
                el('div', { class: 'panel__title-block' },
                    el('h2', { class: 'panel__title', text: 'Получатели' }),
                    el('div', { class: 'panel__subtitle', text: `Всего: ${total}` }),
                ),
                renderBroadcastDeliveriesFilters(byStatus),
            ),
            el('div', { class: 'table-wrapper' },
                el('table', { class: 'table' },
                    el('thead', {},
                        el('tr', {},
                            el('th', { text: 'Telegram ID' }),
                            el('th', { text: 'Username' }),
                            el('th', { text: 'Статус' }),
                            el('th', { text: 'Отправлено' }),
                            el('th', { text: 'Ошибка' }),
                        ),
                    ),
                    el('tbody', {}, ...renderBroadcastDeliveriesRows(App.state.broadcastDeliveries || [])),
                ),
            ),
        ),
    );
}

function renderBroadcastDeliveriesFilters(byStatus) {
    const items = [
        { key: '', label: 'Все', count: (byStatus.pending || 0) + (byStatus.sent || 0) + (byStatus.failed || 0) + (byStatus.blocked || 0) },
        { key: 'pending', label: 'Ожидает', count: byStatus.pending || 0 },
        { key: 'sent', label: 'Отправлено', count: byStatus.sent || 0 },
        { key: 'failed', label: 'Ошибка', count: byStatus.failed || 0 },
        { key: 'blocked', label: 'Заблокирован', count: byStatus.blocked || 0 },
    ];

    const currentFilter = App.state.broadcastDeliveriesFilter || '';

    return el('div', { class: 'panel__filters' },
        ...items.map(item => {
            const isActive = currentFilter === item.key;
            return el('button', {
                class: `chip ${isActive ? 'chip--active' : ''}`,
                onClick: async () => {
                    App.state.broadcastDeliveriesFilter = item.key;
                    await App.loadBroadcastDeliveries(App.state.broadcast.id, 1, item.key);
                    renderApp();
                },
            },
                el('span', { text: item.label }),
                el('span', { class: 'chip__count', text: String(item.count) }),
            );
        }),
    );
}

function renderBroadcastDeliveriesRows(items) {
    if (items.length === 0) {
        return el('tr', {},
            el('td', { colspan: '5', class: 'table__empty' },
                el('div', { class: 'empty empty--inline' },
                    el('p', { class: 'empty__subtitle', text: 'Нет получателей' }),
                ),
            ),
        );
    }

    return items.map(d => el('tr', {},
        el('td', { class: 'table__date', text: String(d.user_tg_id) }),
        el('td', { text: d.username ? `@${d.username}` : '—' }),
        el('td', {}, deliveryStatusBadge(d.status)),
        el('td', { class: 'table__date', text: d.sent_at ? formatDate(d.sent_at) : '—' }),
        el('td', { class: 'broadcast-row__error', text: d.error_message || '—' }),
    ));
}

function renderBroadcastCreateModal(modal) {
    const stats = App.state.broadcastSegmentStats || {};
    const templateVars = App.state.templateVariables || {};
    const segments = Object.keys(stats);

    const titleInput = el('input', {
        type: 'text',
        class: 'input',
        maxlength: '100',
        placeholder: 'Например: «Акция на 1 месяц»',
        id: 'broadcast-title',
    });

    // Сегмент: select с актуальным числом получателей рядом.
    const segmentSelect = el('select', {
        class: 'input',
        id: 'broadcast-segment',
    },
        ...segments.map(seg =>
            el('option', { value: seg, selected: seg === 'TRIAL' ? 'selected' : null },
                `${BROADCAST_SEGMENT_LABELS[seg] || seg} (${stats[seg] || 0})`
            ),
        ),
    );

    // Текст сообщения.
    const messageInput = el('textarea', {
        class: 'input input--textarea',
        rows: '6',
        maxlength: '4096',
        placeholder: 'Текст сообщения. Можно использовать {{first_name}}, {{balance}}, {{days_left}}, {{plan_type}}',
        id: 'broadcast-message',
    });

    // Подсказка по переменным.
    const varsHint = el('div', { class: 'input-hint' },
        'Доступные переменные: ',
        ...Object.keys(templateVars).map((v, i) =>
            el('span', { class: 'input-hint__var', text: `{{${v}}}` + (i < Object.keys(templateVars).length - 1 ? ', ' : '') }),
        ),
        el('br'),
        el('span', { text: 'Первая строка — превью в списке кампаний.' }),
    );

    // Live audience counter справа от select.
    const audienceCounter = el('div', { class: 'broadcast-audience', text: `Получателей: ${stats['TRIAL'] || 0}` });
    segmentSelect.addEventListener('change', () => {
        const seg = segmentSelect.value;
        audienceCounter.textContent = `Получателей: ${stats[seg] || 0}`;
    });

    const submit = async () => {
        const title = titleInput.value.trim();
        const segment = segmentSelect.value;
        const message = messageInput.value.trim();

        if (!title) {
            App.toast('warning', 'Проверь данные', 'Введи название рассылки');
            return;
        }
        if (!message) {
            App.toast('warning', 'Проверь данные', 'Введи текст сообщения');
            return;
        }
        const audience = stats[segment] || 0;
        if (audience === 0) {
            App.toast('warning', 'Сегмент пуст', `В сегменте «${BROADCAST_SEGMENT_LABELS[segment]}» нет получателей`);
            return;
        }

        const btn = document.getElementById('modal-submit');
        if (btn) btn.classList.add('btn--loading');
        try {
            const result = await App.createBroadcast({
                title,
                target_segment: segment,
                message_text: message,
            });
            App.toast('success', 'Создано', `Черновик создан. Запусти его из списка.`);
            App.closeModal();
            App.state.view = 'broadcast-detail';
            App.state.broadcast = result;
            await App.loadBroadcastDeliveries(result.id);
            renderApp();
        } catch (err) {
            App.toast('error', 'Ошибка', err.message);
        } finally {
            if (btn) btn.classList.remove('btn--loading');
        }
    };

    setTimeout(() => titleInput.focus(), 50);

    return el('div', { class: 'modal-overlay', onClick: (e) => e.target === e.currentTarget && App.closeModal() },
        el('div', { class: 'modal modal--wide' },
            el('button', { class: 'modal__close', onClick: () => App.closeModal(), html: ICONS.close }),
            el('h2', { class: 'modal__title', text: 'Новая рассылка' }),
            el('p', { class: 'modal__subtitle', text: 'Сообщение будет отправлено от имени бота выбранному сегменту пользователей.' }),
            el('div', { class: 'modal__body' },
                el('label', { class: 'input-label', for: 'broadcast-title' },
                    el('span', { text: 'Название кампании' }),
                    titleInput,
                ),
                el('label', { class: 'input-label', for: 'broadcast-segment' },
                    el('span', { text: 'Сегмент получателей' }),
                    segmentSelect,
                    audienceCounter,
                ),
                el('label', { class: 'input-label', for: 'broadcast-message' },
                    el('span', { text: 'Текст сообщения' }),
                    messageInput,
                    varsHint,
                ),
            ),
            el('div', { class: 'modal__footer' },
                el('button', { class: 'btn btn--ghost', onClick: () => App.closeModal(), text: 'Отмена' }),
                el('button', { class: 'btn btn--primary', id: 'modal-submit', onClick: submit, text: 'Создать черновик' }),
            ),
        ),
    );
}

// ─── Esc key handler ────────────────────────────────────
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && App.state.modal) {
        App.closeModal();
    }
});

// Patch renderApp to also render modal layer
const _originalRenderApp = window.renderApp;
window.renderApp = function () {
    _originalRenderApp();
    const modalEl = renderModal();
    if (modalEl) {
        document.getElementById('app').appendChild(modalEl);
    }
};
