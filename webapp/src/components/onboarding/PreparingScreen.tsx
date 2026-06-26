import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { useTelegram } from '../../hooks/useTelegram'

interface PreparingScreenProps {
  isLoading: boolean
  error?: string | null
  hasStarted: boolean
  onActivate: () => void
  onContinue: () => void
  onBack: () => void
  onRetry?: () => void
}

const loadingMessages = [
  'Создаем VPN-доступ...',
  'Готовим персональный ключ...',
  'Почти готово...',
]

export function PreparingScreen({
  isLoading,
  error,
  hasStarted,
  onActivate,
  onContinue,
  onBack,
  onRetry,
}: PreparingScreenProps) {
  const { tg } = useTelegram()
  const [messageIndex, setMessageIndex] = useState(0)
  // Ref-гард: onActivate зовём ровно один раз за mount, даже если React strict mode
  // дёрнет useEffect дважды. Retry идёт через отдельный onRetry prop.
  const activatedRef = useRef(false)

  // Auto-trigger API on mount — реальный вызов, никаких фейковых таймеров.
  useEffect(() => {
    if (!activatedRef.current) {
      activatedRef.current = true
      onActivate()
    }
  }, [onActivate])

  // Цикл сообщений крутится только пока реально идёт загрузка.
  useEffect(() => {
    if (!isLoading) return

    const interval = setInterval(() => {
      setMessageIndex((prev) => {
        if (prev < loadingMessages.length - 1) {
          return prev + 1
        }
        return prev
      })
    }, 1500)

    return () => clearInterval(interval)
  }, [isLoading])

  // Success haptic — только когда API реально вернул успех.
  useEffect(() => {
    if (!isLoading && !error && hasStarted) {
      tg?.HapticFeedback?.notificationOccurred('success')
    }
  }, [isLoading, error, hasStarted, tg])

  const handleContinue = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    onContinue()
  }

  const handleBack = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    onBack()
  }

  const isSuccess = hasStarted && !isLoading && !error

  return (
    <motion.div
      className="onboarding-screen preparing-screen"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.4, ease: [0.32, 0.72, 0, 1] }}
    >
      <button className="back-button" onClick={handleBack} aria-label="Назад">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M19 12H5M12 19L5 12L12 5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      <motion.div
        className="preparing-animation"
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ duration: 0.6, ease: [0.32, 0.72, 0, 1] }}
      >
        {isSuccess ? (
          <motion.div
            className="success-icon"
            initial={{ scale: 0, rotate: -180 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ duration: 0.5, ease: [0.32, 0.72, 0, 1] }}
          >
            <svg width="80" height="80" viewBox="0 0 80 80" fill="none" aria-hidden="true">
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
            <svg width="80" height="80" viewBox="0 0 80 80" fill="none" aria-hidden="true">
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
        role={error ? 'alert' : undefined}
      >
        {error ? 'Не удалось активировать триал' : isSuccess ? 'VPN-доступ готов' : 'Подготавливаем ваш VPN-доступ'}
      </motion.h2>

      <motion.p
        className="preparing-subtitle"
        key={messageIndex}
        initial={{ opacity: 0, y: 5 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -5 }}
        transition={{ duration: 0.3 }}
      >
        {error ? error : isSuccess ? 'Ваш персональный ключ создан' : loadingMessages[messageIndex]}
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

      {isSuccess && (
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
