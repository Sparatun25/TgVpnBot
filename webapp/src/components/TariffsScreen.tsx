interface Tariff {
  id: string
  name: string
  price: number
  period: string
  features: string[]
  popular?: boolean
}

const tariffs: Tariff[] = [
  {
    id: 'monthly',
    name: 'Месяц',
    price: 249,
    period: '30 дней',
    features: ['Безлимитный трафик', 'Все серверы', '1 устройство'],
  },
  {
    id: 'quarter',
    name: '3 месяца',
    price: 650,
    period: '90 дней',
    features: ['Безлимитный трафик', 'Все серверы', '2 устройства', 'Экономия 13%'],
    popular: true,
  },
  {
    id: 'year',
    name: 'Год',
    price: 1150,
    period: '365 дней',
    features: ['Безлимитный трафик', 'Все серверы', '3 устройства', 'Экономия 67%'],
  },
]

interface TariffsScreenProps {
  balance: number
}

export function TariffsScreen({ balance }: TariffsScreenProps) {
  const handleBuy = (tariff: Tariff) => {
    if (balance < tariff.price * 100) {
      alert('Недостаточно средств на балансе. Пополните через СБП.')
      return
    }
    // TODO: Логика покупки
    console.log('Покупка тарифа:', tariff)
  }

  return (
    <div className="tariffs-screen">
      <h2 className="screen-title">Тарифы</h2>
      <p className="screen-subtitle">Выберите подходящий план</p>

      <div className="tariffs-grid">
        {tariffs.map((tariff) => (
          <div
            key={tariff.id}
            className={`tariff-card ${tariff.popular ? 'tariff-card-popular' : ''}`}
          >
            {tariff.popular && (
              <div className="tariff-badge">Популярный</div>
            )}

            <div className="tariff-header">
              <h3 className="tariff-name">{tariff.name}</h3>
              <div className="tariff-period">{tariff.period}</div>
            </div>

            <div className="tariff-price">
              <span className="tariff-price-value">{tariff.price}</span>
              <span className="tariff-price-currency">₽</span>
            </div>

            <ul className="tariff-features">
              {tariff.features.map((feature, index) => (
                <li key={index} className="tariff-feature">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M20 6L9 17L4 12" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span>{feature}</span>
                </li>
              ))}
            </ul>

            <button
              className={`tariff-button ${balance < tariff.price * 100 ? 'tariff-button-disabled' : ''}`}
              onClick={() => handleBuy(tariff)}
              disabled={balance < tariff.price * 100}
            >
              {balance < tariff.price * 100 ? 'Недостаточно средств' : 'Купить'}
            </button>
          </div>
        ))}
      </div>

      <div className="tariffs-info">
        <div className="tariffs-info-item">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <path d="M8 21H16M12 17V21" strokeLinecap="round" />
          </svg>
          <span>YouTube, Instagram и другие сервисы</span>
        </div>
        <div className="tariffs-info-item">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 22S8 18 8 12V6L12 2L16 6V12C16 18 12 22 12 22Z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>Полная анонимность и безопасность</span>
        </div>
      </div>
    </div>
  )
}
