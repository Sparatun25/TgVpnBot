import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { useTelegram } from '../../hooks/useTelegram'

interface WaitingScreenProps {
  connectionUrl: string
  onActivated: () => void
}

export function WaitingScreen({ onActivated }: WaitingScreenProps) {
  const { tg } = useTelegram()
  const [elapsed, setElapsed] = useState(0)
  const [showHelp, setShowHelp] = useState(false)

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed((prev) => prev + 1)
    }, 1000)

    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (elapsed >= 45) {
      setShowHelp(true)
      tg?.HapticFeedback?.notificationOccurred('warning')
    }
  }, [elapsed, tg])

  useEffect(() => {
    const checkActivation = async () => {
      try {
        const response = await fetch('/api/subscription/status', {
          headers: {
            'Authorization': `Bearer ${window.Telegram?.WebApp?.initData || ''}`,
          },
        })
        if (response.ok) {
          const data = await response.json()
          if (data.active && data.traffic_detected) {
            onActivated()
          }
        }
      } catch {
        // Ignore errors
      }
    }

    const pollInterval = setInterval(checkActivation, 3000)
    return () => clearInterval(pollInterval)
  }, [onActivated])

  const handleHelp = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    window.open('https://t.me/OnyxVpnSupport', '_blank')
  }

  const progress = Math.min((elapsed / 45) * 100, 100)

  return (
    <motion.div
      className="onboarding-screen waiting-screen"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.4, ease: [0.32, 0.72, 0, 1] }}
    >
      <motion.div
        className="waiting-animation"
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ duration: 0.6, ease: [0.32, 0.72, 0, 1] }}
      >
        <svg width="120" height="120" viewBox="0 0 120 120" fill="none">
          <circle cx="60" cy="60" r="56" stroke="rgba(255,255,255,0.1)" strokeWidth="2" fill="none" />
          <motion.circle
            cx="60"
            cy="60"
            r="56"
            stroke="url(#waiting-gradient)"
            strokeWidth="2"
            fill="none"
            strokeLinecap="round"
            strokeDasharray="352"
            initial={{ strokeDashoffset: 352 }}
            animate={{ strokeDashoffset: 352 - (352 * progress) / 100 }}
            transition={{ duration: 0.5 }}
          />
          <defs>
            <linearGradient id="waiting-gradient" x1="0" y1="0" x2="120" y2="120">
              <stop stopColor="#10B981" />
              <stop offset="1" stopColor="#059669" />
            </linearGradient>
          </defs>
        </svg>
        <div className="waiting-pulse">
          <motion.div
            className="pulse-ring"
            animate={{ scale: [1, 1.5], opacity: [0.5, 0] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
          />
        </div>
      </motion.div>

      <motion.h2
        className="waiting-title"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.2 }}
      >
        Проверяем подключение
      </motion.h2>

      <motion.p
        className="waiting-subtitle"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.3 }}
      >
        Настройка завершится автоматически после первого подключения
      </motion.p>

      <motion.div
        className="waiting-progress"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.4 }}
      >
        <div className="progress-bar">
          <motion.div
            className="progress-fill"
            initial={{ width: '0%' }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.5 }}
          />
        </div>
        <div className="progress-text">{elapsed} сек</div>
      </motion.div>

      {showHelp && (
        <motion.button
          className="waiting-help"
          onClick={handleHelp}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          whileTap={{ scale: 0.96 }}
        >
          Помощь при подключении
        </motion.button>
      )}
    </motion.div>
  )
}
