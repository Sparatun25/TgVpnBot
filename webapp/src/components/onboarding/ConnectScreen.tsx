import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useTelegram } from '../../hooks/useTelegram'

interface ConnectScreenProps {
  connectionUrl: string
  onConnect: () => void
}

export function ConnectScreen({ connectionUrl, onConnect }: ConnectScreenProps) {
  const { tg } = useTelegram()
  const [showFallback, setShowFallback] = useState(false)
  const [showLaunchFailed, setShowLaunchFailed] = useState(false)
  const [manualKey, setManualKey] = useState(connectionUrl)

  const handleConnect = async () => {
    tg?.HapticFeedback?.impactOccurred('light')

    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(connectionUrl)
        tg?.HapticFeedback?.notificationOccurred('success')
      } else {
        throw new Error('Clipboard API not available')
      }
    } catch {
      setShowFallback(true)
      tg?.HapticFeedback?.notificationOccurred('warning')
    }

    // Пытаемся открыть Amnezia VPN через deep link
    setTimeout(() => {
      try {
        window.location.href = connectionUrl

        // Если через 2 секунды пользователь всё ещё здесь — показываем карточку
        setTimeout(() => {
          if (!document.hidden) {
            setShowLaunchFailed(true)
            tg?.HapticFeedback?.notificationOccurred('warning')
          }
        }, 2000)
      } catch {
        setShowLaunchFailed(true)
        setShowFallback(true)
      }
    }, 1000)

    onConnect()
  }

  const handleRetryLaunch = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    try {
      window.location.href = connectionUrl
    } catch {
      // Ignore
    }
  }

  const handleDismissLaunchFailed = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    setShowLaunchFailed(false)
  }

  const handleManualCopy = async () => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(manualKey)
      } else {
        const textArea = document.createElement('textarea')
        textArea.value = manualKey
        textArea.style.position = 'fixed'
        textArea.style.opacity = '0'
        textArea.style.left = '-9999px'
        document.body.appendChild(textArea)
        textArea.focus()
        textArea.select()
        document.execCommand('copy')
        document.body.removeChild(textArea)
      }
      tg?.HapticFeedback?.notificationOccurred('success')
    } catch {
      tg?.HapticFeedback?.notificationOccurred('error')
    }
  }

  return (
    <motion.div
      className="onboarding-screen connect-screen"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.4, ease: [0.32, 0.72, 0, 1] }}
    >
      <motion.h2
        className="connect-title"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1 }}
      >
        Подключите Onyx VPN
      </motion.h2>

      <motion.div
        className="connect-steps"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.2 }}
      >
        <div className="connect-step">
          <div className="step-number">1</div>
          <div className="step-text">Нажмите кнопку ниже</div>
        </div>
        <div className="connect-step">
          <div className="step-number">2</div>
          <div className="step-text">Ключ автоматически скопируется</div>
        </div>
        <div className="connect-step">
          <div className="step-number">3</div>
          <div className="step-text">Amnezia VPN откроется автоматически</div>
        </div>
      </motion.div>

      <motion.button
        className="connect-cta"
        onClick={handleConnect}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.3 }}
        whileTap={{ scale: 0.96 }}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M13 2L3 14H12L11 22L21 10H12L13 2Z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Подключить Onyx VPN
      </motion.button>

      {showFallback && (
        <motion.div
          className="clipboard-fallback"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.4 }}
        >
          <div className="fallback-title">Скопируйте ключ вручную:</div>
          <textarea
            className="fallback-key"
            value={manualKey}
            onChange={(e) => setManualKey(e.target.value)}
            readOnly
            rows={4}
          />
          <button className="fallback-copy-button" onClick={handleManualCopy}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="9" y="9" width="13" height="13" rx="2" />
              <path d="M5 15H4C2.9 15 2 14.1 2 13V4C2 2.9 2.9 2 4 2H13C14.1 2 15 2.9 15 4V5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Скопировать вручную
          </button>
        </motion.div>
      )}

      <AnimatePresence>
        {showLaunchFailed && (
          <motion.div
            className="launch-failed-card"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.4, ease: [0.32, 0.72, 0, 1] }}
          >
            <div className="launch-failed-icon">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 8V12M12 16H12.01" strokeLinecap="round" />
              </svg>
            </div>
            <h3 className="launch-failed-title">Не удалось открыть Amnezia VPN автоматически</h3>
            <p className="launch-failed-subtitle">
              Ключ уже скопирован. Откройте Amnezia VPN и вставьте его вручную.
            </p>
            <div className="launch-failed-actions">
              <motion.button
                className="launch-failed-primary"
                onClick={handleRetryLaunch}
                whileTap={{ scale: 0.96 }}
              >
                Открыть Amnezia ещё раз
              </motion.button>
              <motion.button
                className="launch-failed-secondary"
                onClick={handleDismissLaunchFailed}
                whileTap={{ scale: 0.96 }}
              >
                Понятно
              </motion.button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.details
        className="connect-help"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.5 }}
      >
        <summary className="help-toggle">
          <span>Не получилось автоматически?</span>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 9L12 15L18 9" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </summary>
        <div className="help-content">
          <p className="help-step">
            <strong>1.</strong> Скопируйте ключ вручную (см. выше)
          </p>
          <p className="help-step">
            <strong>2.</strong> Откройте Amnezia VPN
          </p>
          <p className="help-step">
            <strong>3.</strong> Нажмите <strong>«+»</strong> → <strong>«Вставить конфигурацию»</strong> → <strong>«Готово»</strong>
          </p>
        </div>
      </motion.details>
    </motion.div>
  )
}
