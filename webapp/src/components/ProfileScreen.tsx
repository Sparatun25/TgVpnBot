import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { TelegramUser, useTelegram } from '../hooks/useTelegram'

interface ProfileScreenProps {
  user: TelegramUser | null
  subscriptionExpiresAt: string | null
  referralCode?: string
  referralCount?: number
  /**
   * Готовая реферальная ссылка от бэкенда (https://t.me/<bot>?start=ref_<id>).
   * null если бэкенд не смог получить username бота — кнопка копирования
   * остаётся disabled. Это убирает хардкод username из клиента: источник
   * правды для deep-link-формата теперь только в bot/utils/referral.py.
   */
  referralLink?: string | null
}

const COPIED_INDICATOR_MS = 2000
const REFERRAL_GOAL = 3

export function ProfileScreen({
  user,
  subscriptionExpiresAt,
  referralCode,
  referralCount = 0,
  referralLink,
}: ProfileScreenProps) {
  const { tg } = useTelegram()
  const [copied, setCopied] = useState(false)
  const copiedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (copiedTimerRef.current) {
        clearTimeout(copiedTimerRef.current)
        copiedTimerRef.current = null
      }
    }
  }, [])

  // Поддержка открывается через Telegram in-app browser (tg.openLink), а не
  // через target="_blank" — последний вырывает юзера из Telegram и оставляет
  // вкладку браузера, из которой он потом не может вернуться в приложение.
  // href сохранён как fallback: если tg нет (Mini App открыт напрямую в браузере
  // для отладки), обычный переход по ссылке работает.
  const openExternal = (url: string) => {
    if (tg?.openLink) {
      tg.openLink(url)
    } else {
      window.open(url, '_blank', 'noopener,noreferrer')
    }
  }

  const referralProgress = Math.min(referralCount / REFERRAL_GOAL, 1)

  const handleCopyReferral = async () => {
    if (!referralLink) return
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(referralLink)
      } else {
        const textArea = document.createElement('textarea')
        textArea.value = referralLink
        textArea.style.position = 'fixed'
        textArea.style.opacity = '0'
        textArea.style.left = '-9999px'
        document.body.appendChild(textArea)
        textArea.focus()
        textArea.select()
        document.execCommand('copy')
        document.body.removeChild(textArea)
      }
      setCopied(true)
      tg?.HapticFeedback?.notificationOccurred('success')
      if (copiedTimerRef.current) {
        clearTimeout(copiedTimerRef.current)
      }
      copiedTimerRef.current = setTimeout(() => {
        copiedTimerRef.current = null
        setCopied(false)
      }, COPIED_INDICATOR_MS)
    } catch {
      tg?.HapticFeedback?.notificationOccurred('error')
    }
  }

  const isActive = subscriptionExpiresAt ? new Date(subscriptionExpiresAt) > new Date() : false
  const hasExpiry = !!subscriptionExpiresAt
  const expiresDateLabel = subscriptionExpiresAt
    ? new Date(subscriptionExpiresAt).toLocaleDateString('ru-RU', {
        day: 'numeric',
        month: 'long',
      })
    : null

  const fullName = [user?.first_name, user?.last_name].filter(Boolean).join(' ')

  return (
    <motion.div
      className="profile-screen"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
    >
      <motion.div
        className="profile-header"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.05 }}
      >
        <div className="profile-avatar" aria-hidden={user?.photo_url ? undefined : 'true'}>
          {user?.photo_url ? (
            <img
              src={user.photo_url}
              alt={fullName ? `${fullName}, фото профиля` : 'Фото профиля'}
              className="profile-avatar-image"
            />
          ) : (
            <div className="profile-avatar-placeholder">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M20 21V19C20 16.7909 18.2091 15 16 15H8C5.79086 15 4 16.7909 4 19V21" strokeLinecap="round" strokeLinejoin="round" />
                <circle cx="12" cy="7" r="4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          )}
        </div>
        <div className="profile-info">
          <div className="profile-name">{fullName || 'Пользователь'}</div>
          {user?.username && (
            <div className="profile-username">@{user.username}</div>
          )}
        </div>
      </motion.div>

      <hr className="profile-divider" aria-hidden="true" />

      <motion.div
        className={`profile-subscription ${isActive ? 'profile-subscription--active' : ''}`}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.15 }}
      >
        <div className="profile-subscription__status">
          <span className="profile-subscription__dot" aria-hidden="true" />
          <span>{isActive ? 'Подписка активна' : 'Подписка неактивна'}</span>
        </div>
        {hasExpiry && (
          <div className={`profile-subscription__date ${isActive ? '' : 'profile-subscription__date--muted'}`}>
            {isActive ? `до ${expiresDateLabel}` : 'Истекла'}
          </div>
        )}
      </motion.div>

      <hr className="profile-divider" aria-hidden="true" />

      <motion.div
        className="profile-referral"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.25 }}
      >
        <div className="profile-referral__header">
          <h2 className="profile-referral__title">Пригласи друга</h2>
          <p className="profile-referral__subtitle">
            Получи 50 ₽ за каждого друга. {REFERRAL_GOAL} приглашённых — месяц бесплатно.
          </p>
        </div>

        <div className="profile-referral__progress">
          <div className="profile-referral__progress-text">
            <span>Прогресс</span>
            <span>
              <span className="profile-referral__count">{referralCount}</span> / {REFERRAL_GOAL}
            </span>
          </div>
          <div
            className="profile-referral__bar"
            role="progressbar"
            aria-valuenow={referralCount}
            aria-valuemin={0}
            aria-valuemax={REFERRAL_GOAL}
            aria-label={`Приглашено ${referralCount} из ${REFERRAL_GOAL} друзей`}
          >
            <motion.div
              className="profile-referral__fill"
              initial={{ transform: 'scaleX(0)' }}
              animate={{ transform: `scaleX(${referralProgress})` }}
              transition={{ duration: 0.8, delay: 0.4, ease: [0.32, 0.72, 0, 1] }}
              aria-hidden="true"
            />
          </div>
        </div>

        <button
          type="button"
          className={`profile-referral__copy ${copied ? 'profile-referral__copy--copied' : ''}`}
          onClick={handleCopyReferral}
          disabled={!referralLink}
          aria-label={copied ? 'Скопировано' : 'Скопировать реферальную ссылку'}
        >
          {copied ? (
            <>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Скопировано
            </>
          ) : (
            <>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <rect x="9" y="9" width="13" height="13" rx="2" />
                <path d="M5 15H4C2.89543 15 2 14.1046 2 13V4C2 2.89543 2.89543 2 4 2H13C14.1046 2 15 2.89543 15 4V5" strokeLinecap="round" />
              </svg>
              Скопировать ссылку
            </>
          )}
        </button>

        {/* Отдельная live-область для анонса результата копирования.
            Сам <button> не должен быть live-region (role=status на интерактивном
            элементе — анти-паттерн: скринридер проглатывает событие нажатия).
            Здесь aria-live="polite" гарантирует, что диктор проговорит текст
            при изменении copied, не перебивая другие анонсы. */}
        <div className="visually-hidden" role="status" aria-live="polite">
          {copied ? 'Реферальная ссылка скопирована в буфер обмена' : ''}
        </div>

        {referralCode && (
          <div className="profile-referral__progress-text" style={{ marginTop: -4 }}>
            <span>Код</span>
            <span className="profile-referral__count">{referralCode}</span>
          </div>
        )}
      </motion.div>

      <hr className="profile-divider" aria-hidden="true" />

      <motion.a
        href="https://t.me/OnyxVpnSupport"
        className="profile-link"
        onClick={(e) => {
          e.preventDefault()
          openExternal('https://t.me/OnyxVpnSupport')
        }}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.35 }}
      >
        <span>Поддержка</span>
        <span className="profile-link__arrow" aria-hidden="true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M5 12H19M13 6L19 12L13 18" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </motion.a>

      <motion.div
        className="profile-mascot"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.5, ease: [0.32, 0.72, 0, 1] }}
      >
        <img
          src="/cat-about.png"
          alt=""
          className="profile-mascot__img"
          draggable={false}
        />
        <p className="profile-mascot__quote">
          «Спасибо, что выбрали Onyx VPN»
        </p>
      </motion.div>
    </motion.div>
  )
}
