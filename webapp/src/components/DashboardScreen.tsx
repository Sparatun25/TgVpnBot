import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { useTelegram } from '../hooks/useTelegram'

interface DashboardScreenProps {
  trialExpiresAt: string | null
  onBuySubscription: () => void
}

export function DashboardScreen({ trialExpiresAt, onBuySubscription }: DashboardScreenProps) {
  const { tg } = useTelegram()
  const [timeLeft, setTimeLeft] = useState({ days: 0, hours: 0, minutes: 0 })
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
            <div className="status-dot" />
            <span className="status-text">Активен</span>
          </div>
          <div className="status-countdown">
            Осталось {timeLeft.days} дн {timeLeft.hours} ч
          </div>
        </div>

        <div className="progress-container">
          <motion.div
            className="progress-bar"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 1, delay: 0.3, ease: [0.32, 0.72, 0, 1] }}
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
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2">
              <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>IP защищён</span>
          </div>
          <div className="security-item">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2">
              <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>DNS защищён</span>
          </div>
          <div className="security-item">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2">
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
          <div className="insight-icon">📊</div>
          <div className="insight-text">
            Вы использовали VPN чаще, чем 84% новых пользователей
          </div>
        </div>
        <div className="insight-item">
          <div className="insight-icon">⚡️</div>
          <div className="insight-text">
            За эту неделю VPN защитил ваше соединение 52 часа
          </div>
        </div>
        <div className="insight-item">
          <div className="insight-icon">🛡</div>
          <div className="insight-text">
            Сегодня защищено 100% ваших подключений
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}
