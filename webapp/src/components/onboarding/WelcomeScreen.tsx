import { motion } from 'framer-motion'
import { useTelegram } from '../../hooks/useTelegram'

interface WelcomeScreenProps {
  onStart: () => void
}

export function WelcomeScreen({ onStart }: WelcomeScreenProps) {
  const { tg } = useTelegram()

  const handleStart = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    onStart()
  }

  return (
    <motion.div
      className="onboarding-screen"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.4, ease: [0.32, 0.72, 0, 1] }}
    >
      <div className="welcome-hero">
        <motion.div
          className="welcome-icon"
          initial={{ scale: 0, rotate: -180 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ duration: 0.6, ease: [0.32, 0.72, 0, 1], delay: 0.1 }}
        >
          <svg width="80" height="80" viewBox="0 0 80 80" fill="none">
            <circle cx="40" cy="40" r="38" stroke="url(#welcome-gradient)" strokeWidth="2" fill="none" />
            <path
              d="M20 40C20 28.954 28.954 20 40 20C51.046 20 60 28.954 60 40C60 51.046 51.046 60 40 60"
              stroke="url(#welcome-gradient)"
              strokeWidth="2"
              strokeLinecap="round"
            />
            <circle cx="40" cy="40" r="6" fill="url(#welcome-gradient)" />
            <defs>
              <linearGradient id="welcome-gradient" x1="20" y1="20" x2="60" y2="60">
                <stop stopColor="#FFFFFF" />
                <stop offset="1" stopColor="#A0A0A0" />
              </linearGradient>
            </defs>
          </svg>
        </motion.div>

        <motion.h1
          className="welcome-title"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.2 }}
        >
          Onyx VPN
        </motion.h1>

        <motion.p
          className="welcome-subtitle"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.3 }}
        >
          Попробуйте все возможности VPN бесплатно в течение 3 дней
        </motion.p>
      </div>

      <motion.div
        className="welcome-benefits"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.4 }}
      >
        <div className="benefit-item">
          <div className="benefit-icon">🛡</div>
          <div className="benefit-text">Безопасное соединение</div>
        </div>
        <div className="benefit-item">
          <div className="benefit-icon">⚡️</div>
          <div className="benefit-text">Высокая скорость</div>
        </div>
        <div className="benefit-item">
          <div className="benefit-icon">🌍</div>
          <div className="benefit-text">Доступ без ограничений</div>
        </div>
      </motion.div>

      <motion.div
        className="welcome-trial-card"
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4, delay: 0.5 }}
      >
        <div className="trial-feature">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>3 дня бесплатно</span>
        </div>
        <div className="trial-feature">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>Без привязки карты</span>
        </div>
        <div className="trial-feature">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>Активация за 1 минуту</span>
        </div>
      </motion.div>

      <motion.div
        className="welcome-social-proof"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.6 }}
      >
        ⚡️ 14,280 пользователей защищают свои данные с Onyx прямо сейчас
      </motion.div>

      <motion.button
        className="welcome-cta"
        onClick={handleStart}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.7 }}
        whileTap={{ scale: 0.96 }}
      >
        Начать бесплатно
      </motion.button>
    </motion.div>
  )
}
