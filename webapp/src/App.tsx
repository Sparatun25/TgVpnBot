import { useEffect, useState, useCallback } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useTelegram } from './hooks/useTelegram'
import { useApi, ProfileData } from './hooks/useApi'
import { useOnboarding } from './hooks/useOnboarding'
import { WelcomeScreen } from './components/onboarding/WelcomeScreen'
import { InstallScreen } from './components/onboarding/InstallScreen'
import { PreparingScreen } from './components/onboarding/PreparingScreen'
import { ConnectScreen } from './components/onboarding/ConnectScreen'
import { WaitingScreen } from './components/onboarding/WaitingScreen'
import { SuccessScreen } from './components/onboarding/SuccessScreen'
import { DashboardScreen } from './components/DashboardScreen'
import { TariffsScreen } from './components/TariffsScreen'
import { BalanceScreen } from './components/BalanceScreen'
import { ProfileScreen } from './components/ProfileScreen'
import { BottomNav } from './components/BottomNav'
import { TopUpBottomSheet } from './components/TopUpBottomSheet'

type MainTab = 'dashboard' | 'tariffs' | 'balance' | 'profile'

export default function App() {
  const { user, getInitData, tg } = useTelegram()
  const { loading, error, getProfile, activateTrial } = useApi(getInitData)
  const { step, setStep, goNext, goBack } = useOnboarding()

  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [activeTab, setActiveTab] = useState<MainTab>('dashboard')
  const [showTopUp, setShowTopUp] = useState(false)
  const [requiredAmount] = useState(0)

  // Telegram theme integration
  useEffect(() => {
    const themeParams = tg?.themeParams
    if (themeParams) {
      const root = document.documentElement
      if (themeParams.bg_color) root.style.setProperty('--tg-bg', themeParams.bg_color)
      if (themeParams.text_color) root.style.setProperty('--tg-text', themeParams.text_color)
      if (themeParams.hint_color) root.style.setProperty('--tg-hint', themeParams.hint_color)
      if (themeParams.button_color) root.style.setProperty('--tg-button', themeParams.button_color)
      if (themeParams.button_text_color) root.style.setProperty('--tg-button-text', themeParams.button_text_color)
      if (themeParams.secondary_bg_color) root.style.setProperty('--tg-secondary-bg', themeParams.secondary_bg_color)
    }
  }, [tg])

  // Load profile
  useEffect(() => {
    loadProfile()
  }, [])

  const loadProfile = async () => {
    const data = await getProfile()
    if (data) {
      setProfile(data)
      // If user has active subscription or completed trial, skip to dashboard
      if (data.subscription.active || data.has_used_trial) {
        if (step === 'welcome' || step === 'install' || step === 'preparing') {
          setStep('dashboard')
        }
      }
    }
  }

  const handleStartOnboarding = useCallback(() => {
    goNext() // welcome -> install
  }, [goNext])

  const handleInstalled = useCallback(() => {
    goNext() // install -> preparing
  }, [goNext])

  const handlePreparingComplete = useCallback(async () => {
    // Activate trial on backend
    const result = await activateTrial()
    if (result) {
      await loadProfile()
      goNext() // preparing -> connect
    }
  }, [activateTrial, goNext])

  const handleConnect = useCallback(() => {
    goNext() // connect -> waiting
  }, [goNext])

  const handleActivated = useCallback(() => {
    goNext() // waiting -> success
  }, [goNext])

  const handleSuccessComplete = useCallback(() => {
    setStep('dashboard')
  }, [setStep])

  const handleBuySubscription = useCallback(() => {
    setActiveTab('tariffs')
  }, [])

  const handlePaymentSuccess = useCallback(() => {
    loadProfile()
  }, [])

  // Loading state
  if (loading && !profile) {
    return (
      <div className="loading-screen">
        <div className="loading-spinner" />
        <div className="loading-text">Загрузка...</div>
      </div>
    )
  }

  // Error state
  if (error && !profile) {
    return (
      <div className="error-screen">
        <div className="error-icon">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8V12M12 16H12.01" strokeLinecap="round" />
          </svg>
        </div>
        <div className="error-text">{error}</div>
        <button className="error-button" onClick={() => loadProfile()}>
          Повторить
        </button>
      </div>
    )
  }

  // Onboarding flow
  const isOnboarding = step !== 'dashboard'

  return (
    <div className={`app ${isOnboarding ? 'app-onboarding' : ''}`}>
      <main className="app-content">
        <AnimatePresence mode="wait">
          {isOnboarding ? (
            <>
              {step === 'welcome' && (
                <WelcomeScreen key="welcome" onStart={handleStartOnboarding} />
              )}
              {step === 'install' && (
                <InstallScreen key="install" onInstalled={handleInstalled} />
              )}
              {step === 'preparing' && (
                <PreparingScreen
                  key="preparing"
                  onComplete={handlePreparingComplete}
                  onBack={goBack}
                />
              )}
              {step === 'connect' && (
                <ConnectScreen
                  key="connect"
                  connectionUrl={profile?.subscription.connection_url || ''}
                  onConnect={handleConnect}
                />
              )}
              {step === 'waiting' && (
                <WaitingScreen
                  key="waiting"
                  connectionUrl={profile?.subscription.connection_url || ''}
                  onActivated={handleActivated}
                />
              )}
              {step === 'success' && (
                <SuccessScreen key="success" onComplete={handleSuccessComplete} />
              )}
            </>
          ) : (
            <>
              {activeTab === 'dashboard' && (
                <DashboardScreen
                  key="dashboard"
                  trialExpiresAt={profile?.subscription.expires_at ?? null}
                  onBuySubscription={handleBuySubscription}
                />
              )}
              {activeTab === 'tariffs' && (
                <TariffsScreen key="tariffs" balance={profile?.balance ?? 0} />
              )}
              {activeTab === 'balance' && (
                <BalanceScreen
                  key="balance"
                  balance={profile?.balance ?? 0}
                  onBalanceUpdate={handlePaymentSuccess}
                />
              )}
              {activeTab === 'profile' && (
                <ProfileScreen
                  key="profile"
                  user={user}
                  subscriptionExpiresAt={profile?.subscription.expires_at ?? null}
                  referralCode={profile?.referral_code}
                />
              )}
            </>
          )}
        </AnimatePresence>
      </main>

      {!isOnboarding && (
        <BottomNav activeTab={activeTab} onTabChange={setActiveTab} />
      )}

      <TopUpBottomSheet
        isOpen={showTopUp}
        onClose={() => setShowTopUp(false)}
        requiredAmount={requiredAmount}
        onPaymentSuccess={handlePaymentSuccess}
      />
    </div>
  )
}
