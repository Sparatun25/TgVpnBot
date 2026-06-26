import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { useTelegram } from '../../hooks/useTelegram'

interface WaitingScreenProps {
  onActivated: () => void
}

// Общий таймаут ожидания активации. После него polling останавливается
// и юзеру показывается кнопка «Продолжить вручную» — защита от бесконечного спиннера,
// если бэкенд по какой-то причине не подтвердил активацию (например, ключ
// уже создан, но первый пакет через VPN ещё не прошёл).
const OVERALL_TIMEOUT_SECONDS = 300

export function WaitingScreen({ onActivated }: WaitingScreenProps) {
  const { tg } = useTelegram()
  const [elapsed, setElapsed] = useState(0)
  const [showHelp, setShowHelp] = useState(false)
  const [timedOut, setTimedOut] = useState(false)

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed((prev) => prev + 1)
    }, 1000)

    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (elapsed >= 45 && !showHelp) {
      setShowHelp(true)
      tg?.HapticFeedback?.notificationOccurred('warning')
    }
    if (elapsed >= OVERALL_TIMEOUT_SECONDS && !timedOut) {
      setTimedOut(true)
      tg?.HapticFeedback?.notificationOccurred('warning')
    }
  }, [elapsed, showHelp, timedOut, tg])

  useEffect(() => {
    if (timedOut) return

    const POLL_INTERVAL_MS = 3000
    const REQUEST_TIMEOUT_MS = 8000

    const checkActivation = async () => {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
      try {
        const response = await fetch('/api/subscription/status', {
          headers: {
            'Authorization': `Bearer ${window.Telegram?.WebApp?.initData || ''}`,
          },
          signal: controller.signal,
        })
        clearTimeout(timeoutId)
        if (response.ok) {
          const data = await response.json()
          if (data.active && data.auto_advance_eligible) {
            onActivated()
          }
        }
      } catch {
        clearTimeout(timeoutId)
      }
    }

    const pollInterval = setInterval(checkActivation, POLL_INTERVAL_MS)
    return () => clearInterval(pollInterval)
  }, [onActivated, timedOut])

  const handleSkip = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    onActivated()
  }

  const handleHelp = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    // Открываем Telegram-чат поддержки через tg.openTelegramLink,
    // чтобы он открывался внутри Telegram, а не в системном браузере.
    if (tg?.openTelegramLink) {
      tg.openTelegramLink('https://t.me/OnyxVpnSupport')
    } else if (tg?.openLink) {
      tg.openLink('https://t.me/OnyxVpnSupport')
    } else {
      window.open('https://t.me/OnyxVpnSupport', '_blank', 'noopener,noreferrer')
    }
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
        <div className="waiting-cat-wrap">
          <motion.div
            className="waiting-cat-breathing"
            animate={{ scale: [1, 1.04, 1] }}
            transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
          >
            <img
              src="/cat-waiting.png"
              alt="Котик ждёт подключения"
              className="waiting-cat-image"
              draggable={false}
            />
          </motion.div>
          <svg
            className="waiting-progress-ring"
            width="160"
            height="160"
            viewBox="0 0 160 160"
            fill="none"
            aria-hidden="true"
          >
            <circle
              cx="80"
              cy="80"
              r="74"
              stroke="rgba(255,255,255,0.08)"
              strokeWidth="2"
              fill="none"
            />
            <motion.circle
              cx="80"
              cy="80"
              r="74"
              stroke="url(#waiting-gradient)"
              strokeWidth="2.5"
              fill="none"
              strokeLinecap="round"
              strokeDasharray="464"
              initial={{ strokeDashoffset: 464 }}
              animate={{ strokeDashoffset: 464 - (464 * progress) / 100 }}
              transition={{ duration: 0.5 }}
              style={{ rotate: -90, transformOrigin: '80px 80px' }}
            />
            <defs>
              <linearGradient id="waiting-gradient" x1="0" y1="0" x2="160" y2="160">
                <stop stopColor="#A78BFA" />
                <stop offset="1" stopColor="#7C3AED" />
              </linearGradient>
            </defs>
          </svg>
        </div>
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

      {timedOut && (
        <motion.button
          className="waiting-skip"
          onClick={handleSkip}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          whileTap={{ scale: 0.96 }}
        >
          Продолжить вручную
        </motion.button>
      )}
    </motion.div>
  )
}
