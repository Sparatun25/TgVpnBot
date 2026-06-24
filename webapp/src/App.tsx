import { useEffect, useState } from 'react'
import { useTelegram } from './hooks/useTelegram'
import { useApi, ProfileData } from './hooks/useApi'
import { VpnScreen } from './components/VpnScreen'
import { TariffsScreen } from './components/TariffsScreen'
import { BalanceScreen } from './components/BalanceScreen'
import { ProfileScreen } from './components/ProfileScreen'

type Tab = 'vpn' | 'tariffs' | 'balance' | 'profile'

export default function App() {
  const { user, getInitData } = useTelegram()
  const { loading, error, getProfile, activateTrial } = useApi(getInitData)
  const [activeTab, setActiveTab] = useState<Tab>('vpn')
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [hasUsedTrial, setHasUsedTrial] = useState(false)

  useEffect(() => {
    loadProfile()
  }, [])

  const loadProfile = async () => {
    const data = await getProfile()
    if (data) {
      setProfile(data)
      setHasUsedTrial(data.subscription.plan_type === 'trial')
    }
  }

  const handleActivateTrial = async () => {
    const result = await activateTrial()
    if (result) {
      await loadProfile()
      setHasUsedTrial(true)
    }
  }

  if (loading && !profile) {
    return (
      <div className="loading-screen">
        <div className="loading-spinner" />
        <div className="loading-text">Загрузка...</div>
      </div>
    )
  }

  if (error && !profile) {
    return (
      <div className="error-screen">
        <div className="error-icon">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8V12M12 16H12.01" strokeLinecap="round" />
          </svg>
        </div>
        <div className="error-text">{error}</div>
        <button className="error-button" onClick={loadProfile}>
          Повторить
        </button>
      </div>
    )
  }

  return (
    <div className="app">
      <main className="app-content">
        {activeTab === 'vpn' && (
          <VpnScreen
            hasActiveSubscription={profile?.subscription.active ?? false}
            hasUsedTrial={hasUsedTrial}
            connectionUrl={profile?.subscription.connection_url ?? null}
            onActivateTrial={handleActivateTrial}
            trialExpiresAt={profile?.subscription.expires_at ?? null}
          />
        )}

        {activeTab === 'tariffs' && (
          <TariffsScreen balance={profile?.balance ?? 0} />
        )}

        {activeTab === 'balance' && (
          <BalanceScreen balance={profile?.balance ?? 0} />
        )}

        {activeTab === 'profile' && (
          <ProfileScreen
            user={user}
            subscriptionExpiresAt={profile?.subscription.expires_at ?? null}
            referralCode={profile?.referral_code}
          />
        )}
      </main>

      <nav className="tab-bar">
        <button
          className={`tab-button ${activeTab === 'vpn' ? 'tab-button-active' : ''}`}
          onClick={() => setActiveTab('vpn')}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2L2 7L12 12L22 7L12 2Z" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M2 17L12 22L22 17" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M2 12L12 17L22 12" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>VPN</span>
        </button>

        <button
          className={`tab-button ${activeTab === 'tariffs' ? 'tab-button-active' : ''}`}
          onClick={() => setActiveTab('tariffs')}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2V22M17 5H9.5C8.57174 5 7.6815 5.36875 7.02513 6.02513C6.36875 6.6815 6 7.57174 6 8.5C6 9.42826 6.36875 10.3185 7.02513 10.9749C7.6815 11.6313 8.57174 12 9.5 12H14.5C15.4283 12 16.3185 12.3687 16.9749 13.0251C17.6313 13.6815 18 14.5717 18 15.5C18 16.4283 17.6313 17.3185 16.9749 17.9749C16.3185 18.6313 15.4283 19 14.5 19H6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>Тарифы</span>
        </button>

        <button
          className={`tab-button ${activeTab === 'balance' ? 'tab-button-active' : ''}`}
          onClick={() => setActiveTab('balance')}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="2" y="6" width="20" height="12" rx="2" />
            <circle cx="12" cy="12" r="2" />
            <path d="M6 12H6.01M18 12H18.01" strokeLinecap="round" />
          </svg>
          <span>Баланс</span>
        </button>

        <button
          className={`tab-button ${activeTab === 'profile' ? 'tab-button-active' : ''}`}
          onClick={() => setActiveTab('profile')}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 21V19C20 16.7909 18.2091 15 16 15H8C5.79086 15 4 16.7909 4 19V21" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="12" cy="7" r="4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>Профиль</span>
        </button>
      </nav>
    </div>
  )
}
