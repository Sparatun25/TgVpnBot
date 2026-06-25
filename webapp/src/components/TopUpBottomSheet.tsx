import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useTelegram } from '../hooks/useTelegram'
import { useApi } from '../hooks/useApi'

interface TopUpBottomSheetProps {
  isOpen: boolean
  onClose: () => void
  requiredAmount: number
  onPaymentSuccess: () => void
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
  const [paymentStatus, setPaymentStatus] = useState<'idle' | 'pending' | 'success'>('idle')

  const deficit = requiredAmount

  useEffect(() => {
    if (!isOpen) {
      setPaymentStatus('idle')
      setIsProcessing(false)
    }
  }, [isOpen])

  useEffect(() => {
    if (paymentStatus !== 'pending') return

    const pollPaymentStatus = async () => {
      try {
        const response = await fetch('/api/payment/status', {
          headers: {
            'Authorization': `Bearer ${getInitData()}`,
          },
        })

        if (response.ok) {
          const data = await response.json()
          if (data.status === 'succeeded') {
            setPaymentStatus('success')
            tg?.HapticFeedback?.notificationOccurred('success')
            setTimeout(() => {
              onPaymentSuccess()
              onClose()
            }, 1500)
          }
        }
      } catch {
        // Ignore errors
      }
    }

    const interval = setInterval(pollPaymentStatus, 2000)
    const timeout = setTimeout(() => {
      clearInterval(interval)
    }, 120000)

    return () => {
      clearInterval(interval)
      clearTimeout(timeout)
    }
  }, [paymentStatus, getInitData, tg, onPaymentSuccess, onClose])

  const handleTopUp = async () => {
    tg?.HapticFeedback?.impactOccurred('light')
    setIsProcessing(true)

    const amountKopecks = deficit * 100
    const paymentData = await createPayment(amountKopecks)

    if (paymentData && paymentData.payment_url) {
      setPaymentStatus('pending')
      window.open(paymentData.payment_url, '_blank')
    } else {
      setIsProcessing(false)
      tg?.HapticFeedback?.notificationOccurred('error')
    }
  }

  const handleClose = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    onClose()
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            className="bottom-sheet-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            onClick={handleClose}
          />
          <motion.div
            className="bottom-sheet"
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            drag="y"
            dragConstraints={{ top: 0, bottom: 0 }}
            dragElastic={0.2}
            onDragEnd={(_, info) => {
              if (info.offset.y > 100) {
                handleClose()
              }
            }}
          >
            <div className="bottom-sheet-handle" />

            <div className="bottom-sheet-content">
              <h3 className="bottom-sheet-title">Недостаточно средств</h3>
              <p className="bottom-sheet-subtitle">
                Дл�� покупки не хватает {deficit} ₽. Пополнить баланс через СБП?
              </p>

              {paymentStatus === 'pending' && (
                <motion.div
                  className="payment-pending"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <div className="pending-spinner" />
                  <span>Ожидание подтверждения оплаты...</span>
                </motion.div>
              )}

              {paymentStatus === 'success' && (
                <motion.div
                  className="payment-success"
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.3 }}
                >
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2">
                    <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span>Оплата подтверждена!</span>
                </motion.div>
              )}

              <motion.button
                className="bottom-sheet-cta"
                onClick={handleTopUp}
                disabled={isProcessing || paymentStatus !== 'idle'}
                whileTap={{ scale: 0.96 }}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.2 }}
              >
                {isProcessing ? 'Создание платежа...' : `Пополнить на ${deficit} ₽`}
              </motion.button>

              <button
                className="bottom-sheet-cancel"
                onClick={handleClose}
                disabled={isProcessing}
              >
                Отмена
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
