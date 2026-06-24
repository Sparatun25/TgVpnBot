import { useState } from 'react'
import { useApi } from '../hooks/useApi'
import { useTelegram } from '../hooks/useTelegram'

interface BalanceScreenProps {
  balance: number
  onBalanceUpdate?: () => void
}

export function BalanceScreen({ balance }: BalanceScreenProps) {
  const { getInitData } = useTelegram()
  const { createPayment, loading, error } = useApi(getInitData)
  const [amount, setAmount] = useState('')
  const [paymentUrl, setPaymentUrl] = useState<string | null>(null)

  const quickAmounts = [100, 300, 500, 1000]

  const handleQuickAmount = (value: number) => {
    setAmount(value.toString())
  }

  const handleTopUp = async () => {
    const amountValue = parseInt(amount)
    if (!amountValue || amountValue < 10) {
      alert('Минимальная сумма пополнения: 10 рублей')
      return
    }

    const amountKopecks = amountValue * 100

    const paymentData = await createPayment(amountKopecks)

    if (paymentData && paymentData.payment_url) {
      setPaymentUrl(paymentData.payment_url)
      // Открываем платежную ссылку в новой вкладке
      window.open(paymentData.payment_url, '_blank')
    }
  }

  const handleCancel = () => {
    setPaymentUrl(null)
    setAmount('')
  }

  return (
    <div className="balance-screen">
      <h2 className="screen-title">Баланс</h2>

      <div className="balance-card">
        <div className="balance-label">Текущий баланс</div>
        <div className="balance-amount">
          <span className="balance-value">{(balance / 100).toFixed(2)}</span>
          <span className="balance-currency">₽</span>
        </div>
      </div>

      {paymentUrl && (
        <div className="payment-pending">
          <div className="payment-pending-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6V12L16 14" strokeLinecap="round" />
            </svg>
          </div>
          <div className="payment-pending-text">
            <div className="payment-pending-title">Ожидается оплата</div>
            <div className="payment-pending-subtitle">
              Платёж открыт в новой вкладке. После оплаты баланс обновится автоматически.
            </div>
          </div>
          <button className="payment-cancel-button" onClick={handleCancel}>
            Отмена
          </button>
        </div>
      )}

      <div className="topup-section">
        <h3 className="topup-title">Пополнить через СБП</h3>

        <div className="topup-input-wrapper">
          <input
            type="number"
            className="topup-input"
            placeholder="Введите сумму"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            min="10"
            step="10"
            disabled={loading || !!paymentUrl}
          />
          <span className="topup-input-suffix">₽</span>
        </div>

        <div className="topup-quick-amounts">
          {quickAmounts.map((value) => (
            <button
              key={value}
              className={`topup-quick-button ${amount === value.toString() ? 'topup-quick-button-active' : ''}`}
              onClick={() => handleQuickAmount(value)}
              disabled={loading || !!paymentUrl}
            >
              {value} ₽
            </button>
          ))}
        </div>

        {error && <div className="topup-error">{error}</div>}

        <button
          className="topup-button"
          onClick={handleTopUp}
          disabled={!amount || parseInt(amount) < 10 || loading || !!paymentUrl}
        >
          {loading ? 'Создание платежа...' : 'Пополнить'}
        </button>
      </div>

      <div className="balance-info">
        <div className="balance-info-item">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2L2 7L12 12L22 7L12 2Z" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M2 17L12 22L22 17" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M2 12L12 17L22 12" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div>
            <div className="balance-info-title">Мгновенное зачисление</div>
            <div className="balance-info-subtitle">Баланс пополняется сразу после оплаты</div>
          </div>
        </div>
        <div className="balance-info-item">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 22S8 18 8 12V6L12 2L16 6V12C16 18 12 22 12 22Z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div>
            <div className="balance-info-title">Безопасная оплата</div>
            <div className="balance-info-subtitle">Через систему быстрых платежей</div>
          </div>
        </div>
      </div>
    </div>
  )
}
