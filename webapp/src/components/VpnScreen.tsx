import { useState } from 'react'

interface VpnScreenProps {
  hasActiveSubscription: boolean
  hasUsedTrial: boolean
  connectionUrl: string | null
  onActivateTrial: () => Promise<void>
  trialExpiresAt: string | null
}

export function VpnScreen({
  hasActiveSubscription,
  hasUsedTrial,
  connectionUrl,
  onActivateTrial,
  trialExpiresAt,
}: VpnScreenProps) {
  const [showInstructions, setShowInstructions] = useState(false)

  const handleActivateTrial = async () => {
    await onActivateTrial()
    setShowInstructions(true)
  }

  const handleConnect = () => {
    if (!connectionUrl) {
      const step1 = document.querySelector('.stepper-step')
      if (step1) {
        step1.classList.add('stepper-step-shake')
        setTimeout(() => step1.classList.remove('stepper-step-shake'), 2000)
      }
      return
    }

    // Открываем Amnezia через vpn:// диплинк
    window.location.href = connectionUrl
  }

  // Экран предложения триала (новый пользователь, ни разу не активировал)
  if (!hasActiveSubscription && !hasUsedTrial && !showInstructions) {
    return (
      <div className="vpn-screen">
        <div className="trial-banner">
          <div className="trial-banner-icon">
            <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
              <circle cx="32" cy="32" r="30" stroke="url(#trial-gradient)" strokeWidth="2" fill="none" />
              <path d="M20 32C20 25.373 25.373 20 32 20C38.627 20 44 25.373 44 32C44 38.627 38.627 44 32 44" stroke="url(#trial-gradient)" strokeWidth="2" strokeLinecap="round" />
              <circle cx="32" cy="32" r="4" fill="url(#trial-gradient)" />
              <defs>
                <linearGradient id="trial-gradient" x1="20" y1="20" x2="44" y2="44">
                  <stop stopColor="#A78BFA" />
                  <stop offset="1" stopColor="#60A5FA" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <h2 className="trial-banner-title">Попробуйте OnyxVpn</h2>
          <p className="trial-banner-subtitle">3 дня бесплатно, без ограничений</p>
          <button className="trial-button" onClick={handleActivateTrial}>
            Попробовать 3 дня бесплатно
          </button>
          <p className="trial-banner-note">Один триал на аккаунт</p>
        </div>
      </div>
    )
  }

  // Триал закончился, подписки нет — предлагаем оплатить
  if (!hasActiveSubscription && hasUsedTrial && !showInstructions) {
    return (
      <div className="vpn-screen">
        <div className="trial-expired">
          <div className="trial-expired-icon">🐱</div>
          <h2 className="trial-expired-title">Триал закончился</h2>
          <p className="trial-expired-subtitle">
            Бесплатный период завершился. Оформите подписку, чтобы продолжить пользоваться OnyxVpn.
          </p>
          <button className="trial-expired-button" onClick={() => {
            // Переключаем на вкладку тарифов через кастомное событие
            window.dispatchEvent(new CustomEvent('switch-tab', { detail: 'tariffs' }))
          }}>
            Выбрать тариф
          </button>
        </div>
      </div>
    )
  }

  // Экран инструкций после активации
  return (
    <div className={`vpn-screen ${showInstructions ? 'vpn-screen-active' : ''}`}>
      <div className="stepper">
        {/* Шаг 1: Скачать Amnezia */}
        <div className="stepper-step">
          <div className="stepper-number">1</div>
          <div className="stepper-content">
            <h3 className="stepper-title">Скачайте Amnezia VPN</h3>
            <p className="stepper-description">
              Бесплатное приложение для подключения
            </p>
            <div className="store-buttons">
              <a
                href="https://apps.apple.com/app/amnezia-vpn"
                target="_blank"
                rel="noopener noreferrer"
                className="store-button"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18.71 19.5C17.88 20.74 17 21.95 15.66 21.97C14.32 22 13.89 21.18 12.37 21.18C10.84 21.18 10.37 21.95 9.1 22C7.79 22.05 6.8 20.68 5.96 19.47C4.25 17 2.94 12.45 4.7 9.39C5.57 7.87 7.13 6.91 8.82 6.88C10.1 6.86 11.32 7.75 12.11 7.75C12.89 7.75 14.37 6.68 15.92 6.84C16.57 6.87 18.39 7.1 19.56 8.82C19.47 8.88 17.39 10.1 17.41 12.63C17.44 15.65 20.06 16.66 20.09 16.67C20.06 16.74 19.67 18.11 18.71 19.5ZM13 3.5C13.73 2.67 14.94 2.04 15.94 2C16.07 3.17 15.6 4.35 14.9 5.19C14.21 6.04 13.07 6.7 11.95 6.61C11.8 5.46 12.36 4.26 13 3.5Z" />
                </svg>
                <span>App Store</span>
              </a>
              <a
                href="https://play.google.com/store/apps/details?id=org.amnezia.vpn"
                target="_blank"
                rel="noopener noreferrer"
                className="store-button"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M3,20.5V3.5C3,2.91 3.34,2.39 3.84,2.15L13.69,12L3.84,21.85C3.34,21.6 3,21.09 3,20.5M16.81,15.12L6.05,21.34L14.54,12.85L16.81,15.12M20.16,10.81C20.5,11.08 20.75,11.5 20.75,12C20.75,12.5 20.53,12.9 20.18,13.18L17.89,14.5L15.39,12L17.89,9.5L20.16,10.81M6.05,2.66L16.81,8.88L14.54,11.15L6.05,2.66Z" />
                </svg>
                <span>Google Play</span>
              </a>
            </div>
          </div>
        </div>

        {/* Шаг 2: Подключить OnyxVpn */}
        <div className="stepper-step">
          <div className="stepper-number">2</div>
          <div className="stepper-content">
            <h3 className="stepper-title">Подключите OnyxVpn</h3>
            <p className="stepper-description">
              Нажмите кнопку — Amnezia откроется автоматически
            </p>

            <button className="connect-button" onClick={handleConnect}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M13 2L3 14H12L11 22L21 10H12L13 2Z" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Подключить OnyxVpn
            </button>
          </div>
        </div>
      </div>

      {trialExpiresAt && (
        <div className="trial-info">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 6V12L16 14" strokeLinecap="round" />
          </svg>
          <span>Триал до {new Date(trialExpiresAt).toLocaleDateString('ru-RU')}</span>
        </div>
      )}
    </div>
  )
}
