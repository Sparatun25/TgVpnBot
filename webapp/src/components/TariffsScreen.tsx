import { useState } from 'react'
import { motion } from 'framer-motion'
import { useTelegram } from '../hooks/useTelegram'
import { useApi } from '../hooks/useApi'
import { TopUpBottomSheet } from './TopUpBottomSheet'

interface Tariff {
  id: string
  name: string
  price: number
  monthlyPrice?: number
  savings?: number
  period: string
  badge?: string
  popular?: boolean
}

const tariffs: Tariff[] = [
  {
    id: 'year',
    name: 'Год',
    price: 1490,
    monthlyPrice: 124,
    savings: 1498,
    period: '365 дней',
    badge: 'Лучшее предложение',
    popular: true,
  },
  {
    id: 'quarter',
    name: '3 месяца',
    price: 649,
    monthlyPrice: 216,
    savings: 98,
    period: '90 дней',
  },
  {
    id: 'monthly',
    name: 'Месяц',
    price: 249,
    period: '30 дней',
  },
]

interface TariffsScreenProps {
  balance: number
}

export function TariffsScreen({ balance }: TariffsScreenProps) {
  const { tg, getInitData } = useTelegram()
  const { purchaseSubscription } = useApi(getInitData)
  const [purchasing, setPurchasing] = useState<string | null>(null)
  const [showTopUp, setShowTopUp] = useState(false)
  const [requiredAmount, setRequiredAmount] = useState(0)

  const handleBuy = async (tariff: Tariff) => {
    tg?.HapticFeedback?.impactOccurred('light')

    if (balance < tariff.price * 100) {
      setRequiredAmount(tariff.price - balance / 100)
      setShowTopUp(true)
      return
    }

    setPurchasing(tariff.id)
    const result = await purchaseSubscription(tariff.id)
    setPurchasing(null)

    if (result) {
      tg?.HapticFeedback?.notificationOccurred('success')
      window.location.reload()
    }
  }

  const handlePaymentSuccess = () => {
    window.location.reload()
  }

  return (
    <motion.div
      className="tariffs-screen"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
    >
      <motion.div
        className="value-proposition"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1 }}
      >
        <h2 className="screen-title">Почему пользователи выбирают Onyx VPN</h2>
        <div className="value-points">
          <div className="value-point">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2">
              <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>Безлимитный трафик</span>
          </div>
          <div className="value-point">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2">
              <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>Высокая скорость</span>
          </div>
          <div className="value-point">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2">
              <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>Поддержка нескольких устройств</span>
          </div>
          <div className="value-point">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2">
              <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>Быстрое подключение</span>
          </div>
        </div>
      </motion.div>

      <div className="tariffs-grid">
        {tariffs.map((tariff, index) => (
          <motion.div
            key={tariff.id}
            className={`tariff-card ${tariff.popular ? 'tariff-card-popular' : ''}`}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.2 + index * 0.1 }}
          >
            {tariff.badge && <div className="tariff-badge">{tariff.badge}</div>}

            <div className="tariff-header">
              <h3 className="tariff-name">{tariff.name}</h3>
              <div className="tariff-period">{tariff.period}</div>
            </div>

            <div className="tariff-pricing">
              <div className="tariff-price">
                <span className="tariff-price-value">{tariff.price}</span>
                <span className="tariff-price-currency">₽</span>
              </div>
              {tariff.monthlyPrice && (
                <div className="tariff-monthly">{tariff.monthlyPrice} ₽ / месяц</div>
              )}
              {tariff.savings && (
                <div className="tariff-savings">Экономия {tariff.savings} ₽</div>
              )}
            </div>

            <motion.button
              className="tariff-button"
              onClick={() => handleBuy(tariff)}
              disabled={purchasing === tariff.id}
              whileTap={{ scale: 0.96 }}
            >
              {purchasing === tariff.id ? 'Подключение...' : 'Подключить'}
            </motion.button>
          </motion.div>
        ))}
      </div>

      <TopUpBottomSheet
        isOpen={showTopUp}
        onClose={() => setShowTopUp(false)}
        requiredAmount={requiredAmount}
        onPaymentSuccess={handlePaymentSuccess}
      />
    </motion.div>
  )
}
