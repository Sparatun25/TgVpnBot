import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useTelegram } from '../hooks/useTelegram'
import { useApi } from '../hooks/useApi'

interface TopUpBottomSheetProps {
  isOpen: boolean
  onClose: () => void
  requiredAmount: number
  onPaymentSuccess: () => void
}

const POLL_INTERVAL_MS = 2000
const POLL_TIMEOUT_MS = 120000
const FETCH_TIMEOUT_MS = 8000
const SUCCESS_DISMISS_MS = 1500

// Собираем фокусируемые элементы внутри контейнера. Используется для
// автофокуса первого элемента и зацикливания Tab/Shift+Tab внутри шторки.
// aria-hidden и disabled отсекаются явно — disabled-кнопки не должны ловить Tab.
function getFocusableElements(root: HTMLElement | null): HTMLElement[] {
  if (!root) return []
  return Array.from(
    root.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  )
}

export function TopUpBottomSheet({
  isOpen,
  onClose,
  requiredAmount,
  onPaymentSuccess,
}: TopUpBottomSheetProps) {
  const { tg, getInitData } = useTelegram()
  const { createPayment } = useApi(getInitData)
  const [isProcessing, setIsProcessing] = useState(false)
  const [paymentStatus, setPaymentStatus] = useState<'idle' | 'pending' | 'success' | 'timeout'>('idle')
  // Inline-ошибка при сбое createPayment (бэкенд не вернул payment_url).
  // Без неё юзер кликает «Пополнить», получает только вибро-отклик и
  // не понимает, что платёж не создан. role="alert" на рендере ниже.
  const [paymentError, setPaymentError] = useState<string | null>(null)

  const deficit = requiredAmount
  // Refs for cleanup so async callbacks don't fire on unmounted components.
  const isMountedRef = useRef(true)
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const sheetRef = useRef<HTMLDivElement>(null)
  const previouslyFocusedRef = useRef<HTMLElement | null>(null)

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
    if (!isOpen) {
      setPaymentStatus('idle')
      setIsProcessing(false)
      setPaymentError(null)
    }
  }, [isOpen])

  // Автофокус первого элемента при открытии. requestAnimationFrame даёт
  // framer-motion один кадр на маунт, иначе querySelector вернёт пустой
  // список, и пользователь потеряет контекст.
  useEffect(() => {
    if (!isOpen) return
    previouslyFocusedRef.current = document.activeElement as HTMLElement
    const id = window.requestAnimationFrame(() => {
      const focusables = getFocusableElements(sheetRef.current)
      focusables[0]?.focus()
    })
    return () => window.cancelAnimationFrame(id)
  }, [isOpen])

  // Возвращаем фокус на элемент, открывший шторку — иначе клавиатурный
  // пользователь теряет контекст. contains() защищает от попытки
  // сфокусировать удалённый из DOM элемент.
  useEffect(() => {
    if (isOpen) return
    const previouslyFocused = previouslyFocusedRef.current
    if (previouslyFocused && document.body.contains(previouslyFocused)) {
      previouslyFocused.focus()
    }
    previouslyFocusedRef.current = null
  }, [isOpen])

  // Esc закрывает шторку (кроме момента создания платежа), Tab/Shift+Tab
  // зацикливает фокус внутри — не даёт ему утечь за пределы модалки.
  useEffect(() => {
    if (!isOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isProcessing) {
        onClose()
        return
      }
      if (e.key !== 'Tab') return
      const focusables = getFocusableElements(sheetRef.current)
      if (focusables.length === 0) {
        e.preventDefault()
        return
      }
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      const active = document.activeElement as HTMLElement
      const focusInsideSheet = sheetRef.current?.contains(active) ?? false
      if (!focusInsideSheet) {
        e.preventDefault()
        first.focus()
        return
      }
      if (e.shiftKey && active === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && active === last) {
        e.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, isProcessing, onClose])

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

        if (!response.ok) return
        const data = await response.json()
        if (cancelled || !isMountedRef.current) return

        if (data.status === 'succeeded') {
          setPaymentStatus('success')
          tg?.HapticFeedback?.notificationOccurred('success')
          successTimerRef.current = setTimeout(() => {
            successTimerRef.current = null
            if (!isMountedRef.current) return
            onPaymentSuccess()
            onClose()
          }, SUCCESS_DISMISS_MS)
        }
      } catch {
        clearTimeout(timeoutId)
      }
    }

    const interval = setInterval(pollPaymentStatus, POLL_INTERVAL_MS)
    const overallTimeout = setTimeout(() => {
      cancelled = true
      clearInterval(interval)
      // Polling провисел POLL_TIMEOUT_MS без успеха — переводим в timeout,
      // иначе юзер будет бесконечно смотреть на спиннер внутри модалки.
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
  }, [paymentStatus, getInitData, tg, onPaymentSuccess, onClose])

  // tg.openLink открывает СБП-форму ЮKassa в Telegram in-app browser и
  // возвращает юзера обратно в Mini App после оплаты. window.open напрямую
  // вырывает из Telegram-контекста — flow рвётся, polling теряет сессию.
  const openExternal = (url: string) => {
    if (tg?.openLink) {
      tg.openLink(url)
    } else {
      window.open(url, '_blank', 'noopener,noreferrer')
    }
  }

  const handleTopUp = async () => {
    tg?.HapticFeedback?.impactOccurred('light')
    setIsProcessing(true)
    setPaymentError(null)

    const amountKopecks = deficit * 100
    const paymentData = await createPayment(amountKopecks)

    if (!isMountedRef.current) return

    if (paymentData && paymentData.payment_url) {
      setPaymentStatus('pending')
      setIsProcessing(false)
      openExternal(paymentData.payment_url)
    } else {
      setIsProcessing(false)
      tg?.HapticFeedback?.notificationOccurred('error')
      setPaymentError('Не удалось создать платёж. Попробуйте ещё раз.')
    }
  }

  // Повторный запуск polling после таймаута.
  const handleRetryPending = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    setPaymentStatus('pending')
  }

  // Close is allowed once the payment-creation request finishes.
  // While isProcessing is true, the user must wait for the request to resolve
  // so they don't lose track of a payment that may have been created.
  const canClose = !isProcessing
  const handleClose = useCallback(() => {
    if (!canClose) return
    tg?.HapticFeedback?.impactOccurred('light')
    onClose()
  }, [canClose, tg, onClose])

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            className="pay-sheet-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            onClick={handleClose}
            style={{ pointerEvents: canClose ? 'auto' : 'none' }}
          />
          <motion.div
            ref={sheetRef}
            className="pay-sheet"
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            drag="y"
            dragConstraints={{ top: 0, bottom: 0 }}
            dragElastic={canClose ? 0.2 : 0}
            dragListener={canClose}
            onDragEnd={(_, info) => {
              if (canClose && info.offset.y > 100) {
                handleClose()
              }
            }}
            role="dialog"
            aria-modal="true"
            aria-label="Пополнение баланса"
          >
            <div className="pay-sheet-handle" />

            <button
              className="pay-sheet-close"
              onClick={handleClose}
              disabled={!canClose}
              aria-label="Закрыть"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6L18 18" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>

            <div className="pay-sheet-content">
              <div>
                <div className="pay-sheet-eyebrow">Не хватает</div>
                <div className="pay-sheet-amount">
                  <motion.span
                    className="pay-sheet-amount__value"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.5, delay: 0.15 }}
                  >
                    {deficit}
                  </motion.span>
                  <motion.span
                    className="pay-sheet-amount__currency"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.5, delay: 0.2 }}
                  >
                    ₽
                  </motion.span>
                </div>
              </div>

              <hr className="pay-sheet-divider" aria-hidden="true" />

              <p className="pay-sheet-subtitle">
                Пополнить через СБП для оплаты этого тарифа.
              </p>

              {paymentStatus === 'pending' && (
                <motion.div
                  className="pay-sheet-status pay-sheet-status--pending"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                  role="status"
                  aria-live="polite"
                >
                  <span className="pay-sheet-status__dot" aria-hidden="true" />
                  <span className="pay-sheet-status__text">Ожидание подтверждения оплаты…</span>
                  <button
                    className="pay-sheet-status__btn"
                    onClick={handleClose}
                    aria-label="Отменить ожидание оплаты"
                  >
                    Отменить
                  </button>
                </motion.div>
              )}

              {paymentStatus === 'timeout' && (
                <motion.div
                  className="pay-sheet-status pay-sheet-status--timeout"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                  role="alert"
                >
                  <span className="pay-sheet-status__dot" aria-hidden="true" />
                  <span className="pay-sheet-status__text">
                    Время ожидания истекло. Если оплата прошла, попробуйте ещё раз.
                  </span>
                  <button className="pay-sheet-status__btn" onClick={handleRetryPending}>
                    Повторить
                  </button>
                </motion.div>
              )}

              {paymentStatus === 'success' && (
                <motion.div
                  className="pay-sheet-status pay-sheet-status--success"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                  role="status"
                  aria-live="polite"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    aria-hidden="true"
                  >
                    <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span className="pay-sheet-status__text">Оплата подтверждена</span>
                </motion.div>
              )}

              {paymentError && (
                <div className="pay-sheet-error" role="alert">
                  {paymentError}
                </div>
              )}

              <motion.button
                className="pay-sheet-cta"
                onClick={handleTopUp}
                disabled={isProcessing || paymentStatus !== 'idle'}
                whileTap={{ scale: 0.985 }}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.2 }}
              >
                {isProcessing ? 'Создание платежа…' : `Пополнить на ${deficit} ₽`}
              </motion.button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
