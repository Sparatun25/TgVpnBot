import { useState } from 'react'
import { motion } from 'framer-motion'
import { TelegramUser } from '../hooks/useTelegram'
import { useTelegram } from '../hooks/useTelegram'

interface ProfileScreenProps {
  user: TelegramUser | null
  subscriptionExpiresAt: string | null
  referralCode?: string
  referralCount?: number
  referralEarnings?: number
}

export function ProfileScreen({
  user,
  subscriptionExpiresAt,
  referralCode,
  referralCount = 0,
  referralEarnings = 0,
}: ProfileScreenProps) {
  const { tg } = useTelegram()
  const [copied, setCopied] = useState(false)

  const referralLink = `https://t.me/Onyx_vpn24_bot?start=ref_${user?.id}`
  const referralGoal = 3
  const referralProgress = Math.min(referralCount / referralGoal, 1)

  const handleCopyReferral = async () => {
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
      setTimeout(() => setCopied(false), 2000)
    } catch {
      tg?.HapticFeedback?.notificationOccurred('error')
    }
  }

  const isActive = subscriptionExpiresAt && new Date(subscriptionExpiresAt) > new Date()

  return (
    <motion.div
      className="profile-screen"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
    >
      <motion.div
        className="profile-header"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1 }}
      >
        <div className="profile-avatar">
          {user?.photo_url ? (
            <img src={user.photo_url} alt="Avatar" className="profile-avatar-image" />
          ) : (
            <div className="profile-avatar-placeholder">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
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
      </motion.div>

      <motion.div
        className={`profile-subscription-card ${isActive ? 'active' : 'expired'}`}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.2 }}
      >
        <div className="subscription-status">
          <div className={`status-dot ${isActive ? 'active' : 'expired'}`} />
          <span className="status-label">
            {isActive ? 'Подписка активна' : 'Подписка неактивна'}
          </span>
        </div>
        {subscriptionExpiresAt && (
          <div className="subscription-date">
            {isActive
              ? `до ${new Date(subscriptionExpiresAt).toLocaleDateString('ru-RU', {
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                })}`
              : 'Истекла'}
          </div>
        )}
      </motion.div>

      <motion.div
        className="referral-section"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.3 }}
      >
        <h3 className="referral-title">Пригласи друга</h3>
        <p className="referral-subtitle">Получи 50 ₽ за каждого приглашённого друга</p>

        <div className="referral-progress">
          <div className="progress-header">
            <span>Пригласите {referralGoal} друзей — месяц бесплатно!</span>
            <span className="progress-count">
              {referralCount}/{referralGoal}
            </span>
          </div>
          <div className="progress-bar">
            <motion.div
              className="progress-fill"
              initial={{ width: 0 }}
              animate={{ width: `${referralProgress * 100}%` }}
              transition={{ duration: 0.8, delay: 0.5, ease: [0.32, 0.72, 0, 1] }}
            />
          </div>
        </div>

        <div className="referral-stats">
          <div className="referral-stat">
            <div className="stat-value">{referralCount}</div>
            <div className="stat-label">Приглашено друзей</div>
          </div>
          <div className="referral-stat">
            <div className="stat-value">{referralEarnings} ₽</div>
            <div className="stat-label">Заработано</div>
          </div>
        </div>

        <motion.button
          className={`referral-copy-button ${copied ? 'copied' : ''}`}
          onClick={handleCopyReferral}
          whileTap={{ scale: 0.96 }}
        >
          {copied ? (
            <>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Скопировано
            </>
          ) : (
            <>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="9" y="9" width="13" height="13" rx="2" />
                <path d="M5 15H4C2.89543 15 2 14.1046 2 13V4C2 2.89543 2.89543 2 4 2H13C14.1046 2 15 2.89543 15 4V5" strokeLinecap="round" />
              </svg>
              Скопировать ссылку
            </>
          )}
        </motion.button>

        {referralCode && (
          <div className="referral-code-display">
            Код: <span className="code-value">{referralCode}</span>
          </div>
        )}
      </motion.div>

      <motion.div
        className="profile-links"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.4 }}
      >
        <a href="https://t.me/OnyxVpnSupport" className="profile-link" target="_blank" rel="noopener noreferrer">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 11.5A8.38 8.38 0 0 1 12.5 20A8.5 8.5 0 0 1 3 11.5A8.38 8.38 0 0 1 11.5 3A8.5 8.5 0 0 1 21 11.5Z" />
            <path d="M8 12L11 15L16 9" />
          </svg>
          <span>Поддержка</span>
        </a>
      </motion.div>
    </motion.div>
  )
}
