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
      {/* HERO — editorial status. Eyebrow top-left, big serif headline,
          italic countdown в правом нижнем углу. Асимметрия задаёт rhythm. */}
      <motion.section
        className="dashboard-hero"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="dashboard-hero__top">
          <div className="eyebrow eyebrow--accent">
            <span
              className={`status-dot ${isOnline ? 'active' : 'expired'}`}
              aria-hidden="true"
            />
            {isOnline ? 'Защищён' : 'Не подключён'}
          </div>
          {trialExpiresAt && (
            <div className="dashboard-hero__countdown">
              Осталось <span className="numeric">{timeLeft.days}</span> дн <span className="numeric">{timeLeft.hours}</span> ч
            </div>
          )}
        </div>

        <h1 className="display-headline display-headline--xxl dashboard-hero__title">
          {isOnline ? (
            <>Трафик <em className="display-headline--italic">под охраной</em></>
          ) : (
            <>Нет <em className="display-headline--italic">соединения</em></>
          )}
        </h1>

        <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">
          {countdownAnnouncement}
        </div>

        {trialExpiresAt && (
          <div
            className="dashboard-hero__progress"
            role="progressbar"
            aria-valuenow={Math.round(progress)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Остаток триала: ${timeLeft.days} дн ${timeLeft.hours} ч`}
          >
            <motion.div
              className="dashboard-hero__progress-fill"
              initial={{ scaleX: 0 }}
              animate={{ scaleX: progress / 100 }}
              transition={{ duration: 1, delay: 0.4, ease: [0.32, 0.72, 0, 1] }}
              aria-hidden="true"
            />
          </div>
        )}
      </motion.section>

      <hr className="hairline" aria-hidden="true" />

      {/* TRAFFIC — большая цифра как editorial hero. Eyebrow слева,
          гигантская цифра по центру, детали справа. */}
      <motion.section
        className="dashboard-traffic"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.15, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="eyebrow">Трафик</div>
        <div className="dashboard-traffic__hero">
          <motion.span
            className="display-headline display-headline--xxl numeric"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.7, delay: 0.3 }}
          >
            {receivedFmt.value}
          </motion.span>
          <span className="dashboard-traffic__unit">{receivedFmt.unit}</span>
        </div>
        <div className="dashboard-traffic__detail">
          <span className="stat-label">Отправлено</span>
          <span className="stat-value stat-value--small numeric">
            {sentFmt.value} {sentFmt.unit}
          </span>
        </div>
      </motion.section>

      <hr className="hairline" aria-hidden="true" />

      {/* SECURITY — компактные paired details. Каждая пара: label + status.
          Без cards — просто ритм label/value через hairlines. */}
      <motion.section
        className="dashboard-security"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.25, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="eyebrow">Безопасность</div>
        <div className="dashboard-security__grid">
          <div className="dashboard-security__row">
            <span className="stat-label">IP-адрес</span>
            <span className={`security-status ${isOnline ? 'security-status--ok' : 'security-status--off'}`}>
              {isOnline ? 'защищён' : 'открыт'}
            </span>
          </div>
          <hr className="hairline" aria-hidden="true" />
          <div className="dashboard-security__row">
            <span className="stat-label">DNS</span>
            <span className={`security-status ${isOnline ? 'security-status--ok' : 'security-status--off'}`}>
              {isOnline ? 'защищён' : 'открыт'}
            </span>
          </div>
          <hr className="hairline" aria-hidden="true" />
          <div className="dashboard-security__row">
            <span className="stat-label">Шифрование</span>
            <span className="security-status security-status--ok">активно</span>
          </div>
          <hr className="hairline" aria-hidden="true" />
          <div className="dashboard-security__row">
            <span className="stat-label">Последняя активность</span>
            <span className="security-status">{lastSeenText}</span>
          </div>
        </div>
      </motion.section>

      {/* CTA — subtle text-link style вместо big button.
          Editorial luxury: подсказка, не продажа. */}
      <motion.button
        className="dashboard-cta"
        onClick={handleBuyClick}
        whileTap={{ scale: 0.985 }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.5 }}
      >
        <span>Продлить подписку</span>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
          <path d="M5 12H19M12 5L19 12L12 19" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </motion.button>
    </motion.div>
  )
}
