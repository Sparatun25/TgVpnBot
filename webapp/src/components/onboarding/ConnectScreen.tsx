import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useTelegram } from '../../hooks/useTelegram'
import { useMainButton } from '../../hooks/useMainButton'

interface ConnectScreenProps {
  connectionUrl: string
  onConnect: () => void
}

const LAUNCH_DEEP_LINK_DELAY_MS = 1000
const LAUNCH_FAILED_CHECK_MS = 2000

export function ConnectScreen({ connectionUrl, onConnect }: ConnectScreenProps) {
  const { tg } = useTelegram()
  const [showFallback, setShowFallback] = useState(false)
  const [showLaunchFailed, setShowLaunchFailed] = useState(false)

  const deepLinkTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const launchCheckTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isMountedRef = useRef(true)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      if (deepLinkTimerRef.current) {
        clearTimeout(deepLinkTimerRef.current)
        deepLinkTimerRef.current = null
      }
      if (launchCheckTimerRef.current) {
        clearTimeout(launchCheckTimerRef.current)
        launchCheckTimerRef.current = null
      }
    }
  }, [])

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
    deepLinkTimerRef.current = setTimeout(() => {
      deepLinkTimerRef.current = null
      if (!isMountedRef.current) return

      try {
        window.location.href = connectionUrl

        // Если через 2 секунды пользователь всё ещё здесь — показываем карточку
        launchCheckTimerRef.current = setTimeout(() => {
          launchCheckTimerRef.current = null
          if (!isMountedRef.current) return
          if (!document.hidden) {
            setShowLaunchFailed(true)
            tg?.HapticFeedback?.notificationOccurred('warning')
          }
        }, LAUNCH_FAILED_CHECK_MS)
      } catch {
        setShowLaunchFailed(true)
        setShowFallback(true)
      }
    }, LAUNCH_DEEP_LINK_DELAY_MS)

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
        await navigator.clipboard.writeText(connectionUrl)
      } else {
        const textArea = document.createElement('textarea')
        textArea.value = connectionUrl
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

  useMainButton({
    text: 'Подключить Onyx VPN',
    onClick: handleConnect,
  })

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
            value={connectionUrl}
            readOnly
            rows={4}
          />
          <button className="fallback-copy-button" onClick={handleManualCopy}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="9" y="9" width="13" height="13" rx="2" />
              <path d="M5 15H4C2.9 15 2 14.1 2 13V4C2 2.9 2.9 2 3 2H13C14.1 2 15 2.9 15 4V5" strokeLinecap="round" strokeLinejoin="round" />
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
