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
const MIN_TOPUP_RUBLES = 10

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
      // Используем функциональную форму setPaymentStatus, чтобы проверить
      // АКТУАЛЬНОЕ состояние, а не snapshot из closure. Без этого, если за
      // 120 с polling успел перевести status в 'success', эффект
      // перерендерился с новым значением, но старый overallTimeout всё
      // ещё в очереди — он бы перезаписал 'success' обратно в 'timeout'.
      if (!isMountedRef.current) return
      setPaymentStatus(prev => {
        if (prev === 'pending') {
          tg?.HapticFeedback?.notificationOccurred('error')
          return 'timeout'
        }
        return prev
      })
    }, POLL_TIMEOUT_MS)

    return () => {
      cancelled = true
      clearInterval(interval)
      clearTimeout(overallTimeout)
    }
  }, [paymentStatus, getInitData, tg, onBalanceUpdate])

  // Открытие внешней ссылки через Telegram in-app browser если доступен,
  // иначе через window.open. window.open напрямую открывает СБП-страницу
  // ЮKassa ВНЕ Telegram-контекста — это разрывает flow и пользователь теряет
  // состояние приложения. tg.openLink возвращает его обратно после оплаты.
  const openExternal = (url: string) => {
    if (tg?.openLink) {
      tg.openLink(url)
    } else {
      window.open(url, '_blank', 'noopener,noreferrer')
    }
  }

  const handleQuickAmount = (value: number) => {
    tg?.HapticFeedback?.impactOccurred('light')
    setAmount(value.toString())
  }

  const handleTopUp = async () => {
    const amountValue = parseInt(amount)
    if (!amountValue || amountValue < MIN_TOPUP_RUBLES) {
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
      openExternal(paymentData.payment_url)
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

  const formattedBalance = (balance / 100).toLocaleString('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })

  const amountValue = parseInt(amount)
  const isAmountInvalid = amount !== '' && (!amountValue || amountValue < MIN_TOPUP_RUBLES)
  const isSubmitDisabled =
    !amount ||
    !amountValue ||
    amountValue < MIN_TOPUP_RUBLES ||
    isProcessing ||
    paymentStatus !== 'idle'

  const inputDisabled = isProcessing || paymentStatus !== 'idle'

  return (
    <motion.div
      className="balance-screen"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
    >
      <motion.div
        className="balance-hero"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1 }}
      >
        <div className="balance-hero__label">Текущий баланс</div>
        <div className="balance-hero__amount">
          <motion.span
            className="balance-hero__value"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.25 }}
          >
            {formattedBalance}
          </motion.span>
          <span className="balance-hero__currency">₽</span>
        </div>
      </motion.div>

      {paymentStatus === 'pending' && (
        <motion.div
          className="balance-status balance-status--pending"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          role="status"
          aria-live="polite"
        >
          <span className="balance-status__dot" aria-hidden="true" />
          <span className="balance-status__text">Ожидание подтверждения оплаты…</span>
          <div className="balance-status__actions">
            <button
              className="balance-status__btn"
              onClick={handleCancelPending}
              aria-label="Отменить ожидание оплаты"
            >
              Отменить
            </button>
          </div>
        </motion.div>
      )}

      {paymentStatus === 'timeout' && (
        <motion.div
          className="balance-status balance-status--timeout"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          role="alert"
        >
          <span className="balance-status__dot" aria-hidden="true" />
          <span className="balance-status__text">
            Время ожидания истекло. Если оплата прошла, обновите экран.
          </span>
          <div className="balance-status__actions">
            <button className="balance-status__btn" onClick={handleRetryPending}>
              Повторить
            </button>
            <button className="balance-status__btn" onClick={handleCancelPending}>
              Закрыть
            </button>
          </div>
        </motion.div>
      )}

      {paymentStatus === 'success' && (
        <motion.div
          className="balance-status balance-status--success"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          role="status"
          aria-live="polite"
        >
          <span className="balance-status__dot" aria-hidden="true" />
          <span className="balance-status__text">Баланс пополнен</span>
        </motion.div>
      )}

      <motion.div
        className="balance-topup"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.2 }}
      >
        <div className="balance-topup__header">
          <h2 className="balance-topup__title">Пополнить через СБП</h2>
          <p className="balance-topup__subtitle">От {MIN_TOPUP_RUBLES} ₽</p>
        </div>

        <div>
          <label htmlFor="topup-amount" className="visually-hidden">
            Сумма пополнения в рублях
          </label>
          <div className="balance-input-wrapper">
            <input
              id="topup-amount"
              type="number"
              inputMode="numeric"
              className="balance-input"
              placeholder="0"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              min={MIN_TOPUP_RUBLES}
              step={10}
              disabled={inputDisabled}
              aria-describedby={isAmountInvalid ? 'topup-amount-hint' : undefined}
              aria-invalid={isAmountInvalid ? true : undefined}
            />
            <span className="balance-input-suffix" aria-hidden="true">₽</span>
          </div>
          {isAmountInvalid && (
            <div id="topup-amount-hint" className="balance-amount-hint">
              Минимальная сумма пополнения — {MIN_TOPUP_RUBLES} ₽
            </div>
          )}
        </div>

        <div className="balance-quick-amounts">
          {quickAmounts.map((value) => (
            <motion.button
              key={value}
              type="button"
              className={`balance-quick-btn ${amount === value.toString() ? 'balance-quick-btn--active' : ''}`}
              onClick={() => handleQuickAmount(value)}
              disabled={inputDisabled}
              whileTap={{ scale: 0.96 }}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
            >
              {value} ₽
            </motion.button>
          ))}
        </div>

        <motion.button
          type="button"
          className="balance-submit"
          onClick={handleTopUp}
          disabled={isSubmitDisabled}
          whileTap={{ scale: 0.985 }}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.1 }}
        >
          {isProcessing ? 'Создание платежа…' : 'Пополнить'}
        </motion.button>
      </motion.div>

      <motion.div
        className="balance-mascot"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.4, ease: [0.32, 0.72, 0, 1] }}
        aria-hidden="true"
      >
        <img
          src="/cat-companion.png"
          alt=""
          className="balance-mascot__img"
          draggable={false}
        />
      </motion.div>
    </motion.div>
  )
}
