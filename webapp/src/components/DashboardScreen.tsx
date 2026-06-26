import { useEffect, useState, useRef } from 'react'
import { motion } from 'framer-motion'
import { useTelegram } from '../hooks/useTelegram'

export interface TrafficStats {
  total_bytes_received: number
  total_bytes_sent: number
  last_handshake_at: string | null
  is_online: boolean
}

interface DashboardScreenProps {
  trialExpiresAt: string | null
  traffic: TrafficStats | null
  onBuySubscription: () => void
}

const _KB = 1024
const _MB = _KB * 1024
const _GB = _MB * 1024

function formatBytes(numBytes: number): { value: string; unit: string } {
  if (!numBytes || numBytes <= 0) {
    return { value: '0', unit: 'МБ' }
  }
  if (numBytes < _MB) {
    return { value: `${(numBytes / _KB).toFixed(1)}`, unit: 'КБ' }
  }
  if (numBytes < _GB) {
    return { value: `${(numBytes / _MB).toFixed(1)}`, unit: 'МБ' }
  }
  return { value: `${(numBytes / _GB).toFixed(2)}`, unit: 'ГБ' }
}

function formatLastSeen(isoString: string | null): string {
  if (!isoString) return 'нет подключений'
  const last = new Date(isoString).getTime()
  if (Number.isNaN(last)) return 'нет подключений'
  const diffSec = Math.max(0, Math.floor((Date.now() - last) / 1000))
  if (diffSec < 60) return 'только что'
  if (diffSec < 3600) {
    const minutes = Math.floor(diffSec / 60)
    return `${minutes} мин назад`
  }
  if (diffSec < 86400) {
    const hours = Math.floor(diffSec / 3600)
    return `${hours} ч назад`
  }
  const days = Math.floor(diffSec / 86400)
  return `${days} дн назад`
}

export function DashboardScreen({ trialExpiresAt, traffic, onBuySubscription }: DashboardScreenProps) {
  const { tg } = useTelegram()
  const [timeLeft, setTimeLeft] = useState({ days: 0, hours: 0, minutes: 0 })
  const [countdownAnnouncement, setCountdownAnnouncement] = useState('')
  const lastAnnouncedThresholdRef = useRef<number | null>(null)

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

  const totalReceived = traffic?.total_bytes_received ?? 0
  const totalSent = traffic?.total_bytes_sent ?? 0
  const receivedFmt = formatBytes(totalReceived)
  const sentFmt = formatBytes(totalSent)
  const lastSeenText = formatLastSeen(traffic?.last_handshake_at ?? null)
  const isOnline = traffic?.is_online ?? false

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
            <div
              className={`status-dot ${isOnline ? 'active' : 'expired'}`}
              aria-hidden="true"
            />
            <span className="status-text">{isOnline ? 'Защищён' : 'Не подключён'}</span>
          </div>
          <div className="status-countdown">
            Осталось {timeLeft.days} дн {timeLeft.hours} ч
          </div>
        </div>

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
            {receivedFmt.value}
          </motion.span>
          <span className="usage-unit">{receivedFmt.unit}</span>
        </div>
        <div className="usage-today">
          Отправлено: {sentFmt.value} {sentFmt.unit}
        </div>
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
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={isOnline ? '#10B981' : '#6B7280'} strokeWidth="2" aria-hidden="true">
              <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>{isOnline ? 'IP защищён' : 'IP не защищён'}</span>
          </div>
          <div className="security-item">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={isOnline ? '#10B981' : '#6B7280'} strokeWidth="2" aria-hidden="true">
              <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>{isOnline ? 'DNS защищён' : 'DNS не защищён'}</span>
          </div>
          <div className="security-item">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>Соединение зашифровано</span>
          </div>
        </div>
        <div className="security-last-seen">
          Последняя активность: {lastSeenText}
        </div>
      </motion.div>
    </motion.div>
  )
}
