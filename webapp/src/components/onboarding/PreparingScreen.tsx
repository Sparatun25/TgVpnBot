import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { useTelegram } from '../../hooks/useTelegram'

interface PreparingScreenProps {
  onComplete: () => void
  onBack: () => void
  error?: string | null
  onRetry?: () => void
}

const loadingMessages = [
  'Создаем VPN-доступ...',
  'Готовим персональный ключ...',
  'Почти готово...',
]

export function PreparingScreen({ onComplete, onBack, error, onRetry }: PreparingScreenProps) {
  const { tg } = useTelegram()
  const [messageIndex, setMessageIndex] = useState(0)
  const [isComplete, setIsComplete] = useState(false)

  useEffect(() => {
    const interval = setInterval(() => {
      setMessageIndex((prev) => {
        if (prev < loadingMessages.length - 1) {
          return prev + 1
        }
        return prev
      })
    }, 1500)

    const timeout = setTimeout(() => {
      setIsComplete(true)
      tg?.HapticFeedback?.notificationOccurred('success')
    }, 4500)

    return () => {
      clearInterval(interval)
      clearTimeout(timeout)
    }
  }, [tg])

  const handleContinue = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    onComplete()
  }

  const handleBack = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    onBack()
  }

  return (
    <motion.div
      className="onboarding-screen preparing-screen"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.4, ease: [0.32, 0.72, 0, 1] }}
    >
      <button className="back-button" onClick={handleBack}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M19 12H5M12 19L5 12L12 5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      <motion.div
        className="preparing-animation"
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ duration: 0.6, ease: [0.32, 0.72, 0, 1] }}
      >
        {isComplete ? (
          <motion.div
            className="success-icon"
            initial={{ scale: 0, rotate: -180 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ duration: 0.5, ease: [0.32, 0.72, 0, 1] }}
          >
            <svg width="80" height="80" viewBox="0 0 80 80" fill="none">
              <circle cx="40" cy="40" r="38" stroke="#10B981" strokeWidth="2" fill="none" />
              <motion.path
                d="M25 40L35 50L55 30"
                stroke="#10B981"
                strokeWidth="3"
                strokeLinecap="round"
                strokeLinejoin="round"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 0.5, delay: 0.2 }}
              />
            </svg>
          </motion.div>
        ) : (
          <motion.div
            className="loading-spinner"
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          >
            <svg width="80" height="80" viewBox="0 0 80 80" fill="none">
              <circle cx="40" cy="40" r="38" stroke="rgba(255,255,255,0.1)" strokeWidth="2" fill="none" />
              <circle
                cx="40"
                cy="40"
                r="38"
                stroke="url(#spinner-gradient)"
                strokeWidth="2"
                fill="none"
                strokeLinecap="round"
                strokeDasharray="60 180"
              />
              <defs>
                <linearGradient id="spinner-gradient" x1="0" y1="0" x2="80" y2="80">
                  <stop stopColor="#FFFFFF" />
                  <stop offset="1" stopColor="#A0A0A0" />
                </linearGradient>
              </defs>
            </svg>
          </motion.div>
        )}
      </motion.div>

      <motion.h2
        className="preparing-title"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.2 }}
      >
        {error ? 'Не удалось активировать триал' : isComplete ? 'VPN-доступ готов' : 'Подготавливаем ваш VPN-доступ'}
      </motion.h2>

      <motion.p
        className="preparing-subtitle"
        key={messageIndex}
        initial={{ opacity: 0, y: 5 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -5 }}
        transition={{ duration: 0.3 }}
      >
        {error ? error : isComplete ? 'Ваш персональный ключ создан' : loadingMessages[messageIndex]}
      </motion.p>

      {error && (
        <motion.button
          className="preparing-cta"
          onClick={() => onRetry?.()}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.3 }}
          whileTap={{ scale: 0.96 }}
        >
          Попробовать снова
        </motion.button>
      )}

      {isComplete && !error && (
        <motion.button
          className="preparing-cta"
          onClick={handleContinue}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.3 }}
          whileTap={{ scale: 0.96 }}
        >
          Продолжить
        </motion.button>
      )}
    </motion.div>
  )
}
