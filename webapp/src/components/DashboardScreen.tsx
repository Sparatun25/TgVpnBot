import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { useTelegram } from '../hooks/useTelegram'

interface DashboardScreenProps {
  trialExpiresAt: string | null
  onBuySubscription: () => void
}

export function DashboardScreen({ trialExpiresAt, onBuySubscription }: DashboardScreenProps) {
  const { tg } = useTelegram()
  const [timeLeft, setTimeLeft] = useState({ days: 0, hours: 0, minutes: 0 })
  const [countdownAnnouncement, setCountdownAnnouncement] = useState('')
  const lastAnnouncedThresholdRef = useRef<number | null>(null)
  const trafficUsed = 12.4
  const todayTraffic = 1.1
  const protectionTime = 52
  const maxSpeed = 85
  const connections = 3

  useEffect(() => {
    if (!trialExpiresAt) return

    const updateCountdown = () => {
      const now = new Date().getTime()
      const expires = new Date(trialExpiresAt).getTime()
      const diff = expires - now

      if (diff > 0) {
        const days = Math.floor(diff / (1000 * 60 * 60 * 24))
        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
        const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
        setTimeLeft({ days, hours, minutes })

        // Пороговые анонсы: «менее 24ч» и «1 час». Без них экранный диктор
        // молчит весь триал и пользователь не знает, что время подходит к концу.
        // Ref-хранилище гарантирует, что один порог анонсируется ровно один раз.
        const totalHours = days * 24 + hours
        let nextThreshold: number | null = null
        if (totalHours <= 1) nextThreshold = 1
        else if (totalHours <= 24) nextThreshold = 24

        if (nextThreshold !== null && nextThreshold !== lastAnnouncedThresholdRef.current) {
          lastAnnouncedThresholdRef.current = nextThreshold
          setCountdownAnnouncement(
            nextThreshold === 1
              ? 'До окончания триала остался 1 час.'
              : 'До окончания триала осталось менее 24 часов.'
          )
        }
      } else if (lastAnnouncedThresholdRef.current !== 0) {
        lastAnnouncedThresholdRef.current = 0
        setCountdownAnnouncement('Пробный период закончился.')
      }
    }

    updateCountdown()
    const interval = setInterval(updateCountdown, 60000)
    return () => clearInterval(interval)
  }, [trialExpiresAt])

  const handleBuyClick = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    onBuySubscription()
  }

  const progress = ((timeLeft.days * 24 + timeLeft.hours) / (3 * 24)) * 100

  return (
    <motion.div
      className="dashboard-screen"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
    >
      <motion.div
        className="status-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1 }}
      >
        <div className="status-header">
          <div className="status-indicator">
            <div className="status-dot" aria-hidden="true" />
            <span className="status-text">Активен</span>
          </div>
          <div className="status-countdown">
            Осталось {timeLeft.days} дн {timeLeft.hours} ч
          </div>
        </div>

        {/* Скрытая live-область для пороговых анонсов (<24ч, <1ч, истёк).
            Видимый countdown обновляется каждую минуту — слишком часто для
            диктора; здесь срабатывает только при пересечении порога. */}
        <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">
          {countdownAnnouncement}
        </div>

        <div
          className="progress-container"
          role="progressbar"
          aria-valuenow={Math.round(progress)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Остаток триала: ${timeLeft.days} дн ${timeLeft.hours} ч`}
        >
          <motion.div
            className="progress-bar"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 1, delay: 0.3, ease: [0.32, 0.72, 0, 1] }}
            aria-hidden="true"
          />
        </div>

        <motion.button
          className="buy-subscription-button"
          onClick={handleBuyClick}
          whileTap={{ scale: 0.96 }}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.4 }}
        >
          Купить подписку
        </motion.button>
      </motion.div>

      <motion.div
        className="usage-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.2 }}
      >
        <div className="card-title">Использовано трафика</div>
        <div className="usage-value">
          <motion.span
            className="usage-number"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.5 }}
          >
            {trafficUsed}
          </motion.span>
          <span className="usage-unit">ГБ</span>
        </div>
        <div className="usage-today">Сегодня: {todayTraffic} ГБ</div>
      </motion.div>

      <motion.div
        className="security-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.3 }}
      >
        <div className="card-title">Безопасность</div>
        <div className="security-items">
          <div className="security-item">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2" aria-hidden="true">
              <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>IP защищён</span>
          </div>
          <div className="security-item">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2" aria-hidden="true">
              <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>DNS защищён</span>
          </div>
          <div className="security-item">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2" aria-hidden="true">
              <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>Соединение зашифровано</span>
          </div>
        </div>
      </motion.div>

      <motion.div
        className="stats-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.4 }}
      >
        <div className="card-title">Статистика</div>
        <div className="stats-grid">
          <div className="stat-item">
            <div className="stat-value">
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.6, delay: 0.6 }}
              >
                {protectionTime}
              </motion.span>
              ч
            </div>
            <div className="stat-label">Время защиты</div>
          </div>
          <div className="stat-item">
            <div className="stat-value">
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.6, delay: 0.7 }}
              >
                {maxSpeed}
              </motion.span>
              Мбит/с
            </div>
            <div className="stat-label">Макс. скорость</div>
          </div>
          <div className="stat-item">
            <div className="stat-value">
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.6, delay: 0.8 }}
              >
                {connections}
              </motion.span>
            </div>
            <div className="stat-label">Подключений</div>
          </div>
        </div>
      </motion.div>

      <motion.div
        className="insights-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.5 }}
      >
        <div className="card-title">Инсайты</div>
        <div className="insight-item">
          <div className="insight-icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="20" x2="18" y2="10" />
              <line x1="12" y1="20" x2="12" y2="4" />
              <line x1="6" y1="20" x2="6" y2="14" />
              <line x1="3" y1="20" x2="21" y2="20" />
            </svg>
          </div>
          <div className="insight-text">
            Вы использовали VPN чаще, чем 84% новых пользователей
          </div>
        </div>
        <div className="insight-item">
          <div className="insight-icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
          </div>
          <div className="insight-text">
            За эту неделю VPN защитил ваше соединение 52 часа
          </div>
        </div>
        <div className="insight-item">
          <div className="insight-icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <path d="M9 12l2 2 4-4" />
            </svg>
          </div>
          <div className="insight-text">
            Сегодня защищено 100% ваших подключений
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}
