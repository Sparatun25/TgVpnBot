import { useState } from 'react'
import { TelegramUser, useTelegram } from '../hooks/useTelegram'

interface ProfileScreenProps {
  user: TelegramUser | null
  subscriptionExpiresAt: string | null
  referralCode?: string
}

export function ProfileScreen({ user, subscriptionExpiresAt, referralCode }: ProfileScreenProps) {
  const [copied, setCopied] = useState(false)
  const { tg } = useTelegram()

  const referralLink = `https://t.me/onyxvpn_bot?start=ref_${user?.id}`

  const handleCopyReferral = async () => {
    try {
      await navigator.clipboard.writeText(referralLink)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      console.error('Ошибка копирования')
    }
  }

  const handleDocClick = (e: React.MouseEvent<HTMLAnchorElement>, path: string) => {
    e.preventDefault()
    const url = `${window.location.origin}${path}`
    if (tg?.openLink) {
      tg.openLink(url)
    } else {
      window.open(url, '_blank')
    }
  }

  return (
    <div className="profile-screen">
      <h2 className="screen-title">Профиль</h2>

      <div className="profile-header">
        <div className="profile-avatar">
          {user?.photo_url ? (
            <img src={user.photo_url} alt="Avatar" className="profile-avatar-image" />
          ) : (
            <div className="profile-avatar-placeholder">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 21V19C20 16.7909 18.2091 15 16 15H8C5.79086 15 4 16.7909 4 19V21" strokeLinecap="round" strokeLinejoin="round" />
                <circle cx="12" cy="7" r="4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          )}
        </div>
        <div className="profile-info">
          <div className="profile-name">
            {user?.first_name} {user?.last_name}
          </div>
          {user?.username && (
            <div className="profile-username">@{user.username}</div>
          )}
        </div>
      </div>

      {subscriptionExpiresAt && (
        <div className="profile-subscription">
          <div className="profile-subscription-label">Подписка активна до</div>
          <div className="profile-subscription-date">
            {new Date(subscriptionExpiresAt).toLocaleDateString('ru-RU', {
              day: 'numeric',
              month: 'long',
              year: 'numeric',
            })}
          </div>
        </div>
      )}

      <div className="profile-section">
        <h3 className="profile-section-title">Пригласи друга</h3>
        <p className="profile-section-subtitle">
          Получи 50 ₽ за каждого приглашённого друга
        </p>

        <div className="referral-card">
          <div className="referral-mascot">
            <svg width="80" height="80" viewBox="0 0 80 80" fill="none">
              <circle cx="40" cy="40" r="38" fill="#1A1A1A" stroke="#2A2A2A" strokeWidth="2" />
              <circle cx="30" cy="35" r="3" fill="#A78BFA" />
              <circle cx="50" cy="35" r="3" fill="#A78BFA" />
              <path d="M32 45C34 48 46 48 48 45" stroke="#A78BFA" strokeWidth="2" strokeLinecap="round" />
              <path d="M25 25L30 30M55 25L50 30" stroke="#A78BFA" strokeWidth="2" strokeLinecap="round" />
              <path d="M20 20L25 25M60 20L55 25" stroke="#A78BFA" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </div>

          <div className="referral-code">{referralCode}</div>

          <button
            className={`referral-button ${copied ? 'referral-button-copied' : ''}`}
            onClick={handleCopyReferral}
          >
            {copied ? (
              <>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Скопировано
              </>
            ) : (
              <>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" />
                  <path d="M5 15H4C2.89543 15 2 14.1046 2 13V4C2 2.89543 2.89543 2 4 2H13C14.1046 2 15 2.89543 15 4V5" strokeLinecap="round" />
                </svg>
                Скопировать ссылку
              </>
            )}
          </button>
        </div>
      </div>

      <div className="profile-stats">
        <div className="profile-stat">
          <div className="profile-stat-value">0</div>
          <div className="profile-stat-label">Приглашено</div>
        </div>
        <div className="profile-stat">
          <div className="profile-stat-value">0 ₽</div>
          <div className="profile-stat-label">Заработано</div>
        </div>
      </div>

      <div className="profile-section">
        <h3 className="profile-section-title">Информация</h3>
        <div className="profile-links">
          <a href="/pricing" className="profile-link">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="12" y1="1" x2="12" y2="23" />
              <path d="M17 5H9.5A3.5 3.5 0 0 0 9.5 12H14.5A3.5 3.5 0 0 1 14.5 19H5" />
            </svg>
            <span>Тарифы и цены</span>
          </a>
          <a href="/privacy" className="profile-link">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 22S8 18 8 12V6L12 2L16 6V12C16 18 12 22 12 22Z" />
            </svg>
            <span>Политика конфиденциальности</span>
          </a>
          <a href="/terms" className="profile-link">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6A2 2 0 0 0 4 4V20A2 2 0 0 0 6 20H18A2 2 0 0 0 20 18V8L14 2Z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
            <span>Пользовательское соглашение</span>
          </a>
          <a href="https://t.me/OnyxVpnSupport" className="profile-link">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 11.5A8.38 8.38 0 0 1 12.5 20A8.5 8.5 0 0 1 3 11.5A8.38 8.38 0 0 1 11.5 3A8.5 8.5 0 0 1 21 11.5Z" />
              <path d="M8 12L11 15L16 9" />
            </svg>
            <span>Поддержка</span>
          </a>
        </div>
      </div>
    </div>
  )
}
