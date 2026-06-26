import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { useTelegram } from '../hooks/useTelegram'
import { useApi } from '../hooks/useApi'

interface BalanceScreenProps {
  balance: number
  onBalanceUpdate?: () => void
}

const POLL_INTERVAL_MS = 2000
const POLL_TIMEOUT_MS = 120000
const FETCH_TIMEOUT_MS = 8000
const SUCCESS_DISMISS_MS = 2000

export function BalanceScreen({ balance, onBalanceUpdate }: BalanceScreenProps) {
  const { tg, getInitData } = useTelegram()
  const { createPayment } = useApi(getInitData)
  const [amount, setAmount] = useState('')
  const [isProcessing, setIsProcessing] = useState(false)
  const [paymentStatus, setPaymentStatus] = useState<'idle' | 'pending' | 'success' | 'timeout'>('idle')

  const quickAmounts = [100, 300, 500, 1000]

  const isMountedRef = useRef(true)
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      if (successTimerRef.current) {
        clearTimeout(successTimerRef.current)
        successTimerRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (paymentStatus !== 'pending') return

    let cancelled = false

    const pollPaymentStatus = async () => {
      const fetchController = new AbortController()
      const timeoutId = setTimeout(() => fetchController.abort(), FETCH_TIMEOUT_MS)
      try {
        const response = await fetch('/api/payment/status', {
          headers: {
            'Authorization': `Bearer ${getInitData()}`,
          },
          signal: fetchController.signal,
        })
        clearTimeout(timeoutId)

        if (cancelled || !isMountedRef.current) return

        if (response.ok) {
          const data = await response.json()
          if (data.status === 'succeeded') {
            setPaymentStatus('success')
            tg?.HapticFeedback?.notificationOccurred('success')
            successTimerRef.current = setTimeout(() => {
              successTimerRef.current = null
              if (!isMountedRef.current) return
              setPaymentStatus('idle')
              setAmount('')
              onBalanceUpdate?.()
            }, SUCCESS_DISMISS_MS)
          }
        }
      } catch {
        clearTimeout(timeoutId)
      }
    }

    const interval = setInterval(pollPaymentStatus, POLL_INTERVAL_MS)
    const overallTimeout = setTimeout(() => {
      cancelled = true
      clearInterval(interval)
      // Если polling провисел POLL_TIMEOUT_MS без успеха — переводим UI
      // в timeout, иначе юзер будет бесконечно смотреть на спиннер.
      if (isMountedRef.current && paymentStatus === 'pending') {
        setPaymentStatus('timeout')
        tg?.HapticFeedback?.notificationOccurred('error')
      }
    }, POLL_TIMEOUT_MS)

    return () => {
      cancelled = true
      clearInterval(interval)
      clearTimeout(overallTimeout)
    }
  }, [paymentStatus, getInitData, tg, onBalanceUpdate])

  const handleQuickAmount = (value: number) => {
    tg?.HapticFeedback?.impactOccurred('light')
    setAmount(value.toString())
  }

  const handleTopUp = async () => {
    const amountValue = parseInt(amount)
    if (!amountValue || amountValue < 10) {
      tg?.HapticFeedback?.notificationOccurred('error')
      return
    }

    tg?.HapticFeedback?.impactOccurred('light')
    setIsProcessing(true)

    const amountKopecks = amountValue * 100
    const paymentData = await createPayment(amountKopecks)

    if (!isMountedRef.current) return

    if (paymentData && paymentData.payment_url) {
      setPaymentStatus('pending')
      window.open(paymentData.payment_url, '_blank')
    } else {
      setIsProcessing(false)
      tg?.HapticFeedback?.notificationOccurred('error')
    }
  }

  // Ручная отмена ожидания оплаты. Polling остановится через cleanup polling-эффекта.
  const handleCancelPending = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    setPaymentStatus('idle')
  }

  // Повторный запуск polling после таймаута.
  const handleRetryPending = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    setPaymentStatus('pending')
  }

  return (
    <motion.div
      className="balance-screen"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
    >
      <motion.div
        className="balance-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1 }}
      >
        <div className="balance-label">Текущий баланс</div>
        <div className="balance-amount">
          <motion.span
            className="balance-value"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6, delay: 0.3 }}
          >
            {(balance / 100).toFixed(2)}
          </motion.span>
          <span className="balance-currency">₽</span>
        </div>

        {paymentStatus === 'pending' && (
          <motion.div
            className="balance-pending"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <div className="pending-spinner" />
            <span>Ожидание подтверждения оплаты...</span>
            <button
              className="balance-pending-cancel"
              onClick={handleCancelPending}
              aria-label="Отменить ожидание оплаты"
            >
              Отменить
            </button>
          </motion.div>
        )}

        {paymentStatus === 'timeout' && (
          <motion.div
            className="balance-timeout"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            role="alert"
          >
            <span>Время ожидания истекло. Если оплата прошла, обновите экран.</span>
            <div className="balance-timeout-actions">
              <button
                className="balance-timeout-retry"
                onClick={handleRetryPending}
              >
                Повторить
              </button>
              <button
                className="balance-timeout-dismiss"
                onClick={handleCancelPending}
              >
                Закрыть
              </button>
            </div>
          </motion.div>
        )}

        {paymentStatus === 'success' && (
          <motion.div
            className="balance-success"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3 }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2">
              <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>Баланс пополнен!</span>
          </motion.div>
        )}
      </motion.div>

      <motion.div
        className="topup-section"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.2 }}
      >
        <h3 className="topup-title">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="2" y="5" width="20" height="14" rx="2" />
            <path d="M2 10H22" />
          </svg>
          Пополнить через СБП
        </h3>

        <div className="topup-input-wrapper">
          <input
            type="number"
            className="topup-input"
            placeholder="Введите сумму"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            min="10"
            step="10"
            disabled={isProcessing || paymentStatus !== 'idle'}
          />
          <span className="topup-input-suffix">₽</span>
        </div>

        <div className="topup-quick-amounts">
          {quickAmounts.map((value) => (
            <motion.button
              key={value}
              className={`topup-quick-button ${amount === value.toString() ? 'topup-quick-button-active' : ''}`}
              onClick={() => handleQuickAmount(value)}
              disabled={isProcessing || paymentStatus !== 'idle'}
              whileTap={{ scale: 0.96 }}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
            >
              {value} ₽
            </motion.button>
          ))}
        </div>

        <motion.button
          className="topup-button"
          onClick={handleTopUp}
          disabled={!amount || parseInt(amount) < 10 || isProcessing || paymentStatus !== 'idle'}
          whileTap={{ scale: 0.96 }}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.3 }}
        >
          {isProcessing ? 'Создание платежа...' : 'Пополнить'}
        </motion.button>
      </motion.div>

      <motion.div
        className="balance-info"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.4 }}
      >
        <div className="balance-info-item">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2">
            <path d="M13 2L3 14H12L11 22L21 10H12L13 2Z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div>
            <div className="balance-info-title">Мгновенное зачисление</div>
            <div className="balance-info-subtitle">Баланс пополняется сразу после оплаты</div>
          </div>
        </div>
        <div className="balance-info-item">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2">
            <path d="M12 22S8 18 8 12V6L12 2L16 6V12C16 18 12 22 12 22Z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div>
            <div className="balance-info-title">Безопасная оплата</div>
            <div className="balance-info-subtitle">Через систему быстрых платежей</div>
          </div>
        </div>
      </motion.div>

      <motion.div
        className="balance-cat-companion"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.5, ease: [0.32, 0.72, 0, 1] }}
        aria-hidden="true"
      >
        <img
          src="/cat-companion.png"
          alt=""
          className="balance-cat-image"
          draggable={false}
        />
      </motion.div>
    </motion.div>
  )
}
