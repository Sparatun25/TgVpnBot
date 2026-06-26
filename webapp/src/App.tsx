import { useEffect, useState, useCallback, useRef } from 'react'
import { AnimatePresence, MotionConfig } from 'framer-motion'
import { useTelegram } from './hooks/useTelegram'
import { useApi, ProfileData } from './hooks/useApi'
import { useOnboarding } from './hooks/useOnboarding'
import { useBackButton } from './hooks/useBackButton'
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

type MainTab = 'dashboard' | 'tariffs' | 'balance' | 'profile'

export default function App() {
  const { user, getInitData, tg } = useTelegram()
  const { loading, error, getProfile, activateTrial } = useApi(getInitData)
  const { step, setStep, goNext, goBack } = useOnboarding()

  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [activeTab, setActiveTab] = useState<MainTab>('dashboard')
  const [autoPlanId, setAutoPlanId] = useState<string | null>(null)
  // Ошибка активации триала. Сбрасывается при старте новой попытки.
  // Без этого юзер, нажав «Продолжить» при сбое сети, не получал бы обратной связи —
  // кнопка просто ничего не делала, и он застревал на preparing-экране.
  const [trialError, setTrialError] = useState<string | null>(null)
  // Успех активации триала — true только когда API реально вернул 200.
  // Отдельный флаг от trialError, чтобы UI не врал о готовности ключа.
  const [trialSuccess, setTrialSuccess] = useState(false)
  // Флаг «запрос уже отправлен» — чтобы PreparingScreen не моргал success-иконкой
  // в начальный момент (до первого вызова activateTrial isLoading ещё false).
  const [trialHasStarted, setTrialHasStarted] = useState(false)
  // Ref-гард от двойного вызова activateTrial при повторном mount/re-render.
  const trialStartedRef = useRef(false)

  // Deep link routing: parse URL params once on mount, store in ref.
  // Split into two effects so that `plan` (which needs balance from profile)
  // doesn't race against loadProfile. screen/step are applied immediately.
  const deepLinkRef = useRef<{ plan: string | null; screen: string | null; step: string | null } | null>(null)
  if (deepLinkRef.current === null) {
    const params = new URLSearchParams(window.location.search)
    deepLinkRef.current = {
      plan: params.get('plan'),
      screen: params.get('screen'),
      step: params.get('step'),
    }
    if (deepLinkRef.current.plan || deepLinkRef.current.screen || deepLinkRef.current.step) {
      window.history.replaceState({}, '', window.location.pathname)
    }
  }

  useEffect(() => {
    const dl = deepLinkRef.current
    if (!dl) return

    if (dl.screen === 'tariffs') {
      setActiveTab('tariffs')
      setStep('dashboard')
    }
    if (dl.step === 'connect') {
      setStep('connect')
    }
  }, [setStep])

  // Apply plan only after profile is loaded — otherwise auto-buy fires with
  // balance=0 and opens the top-up sheet for users who actually have funds.
  useEffect(() => {
    const dl = deepLinkRef.current
    if (!dl?.plan || !profile) return

    setActiveTab('tariffs')
    setStep('dashboard')
    setAutoPlanId(dl.plan)
    deepLinkRef.current = { ...dl, plan: null }
  }, [profile, setStep])

  // Telegram theme integration.
  // Биндим themeParams в CSS-переменные и подписываемся на themeChanged —
  // пользователь может переключать тему в настройках Telegram на лету.
  useEffect(() => {
    if (!tg) return

    const applyTheme = () => {
      const themeParams = tg.themeParams
      if (!themeParams) return
      const root = document.documentElement
      if (themeParams.bg_color) root.style.setProperty('--tg-bg', themeParams.bg_color)
      if (themeParams.text_color) root.style.setProperty('--tg-text', themeParams.text_color)
      if (themeParams.hint_color) root.style.setProperty('--tg-hint', themeParams.hint_color)
      if (themeParams.button_color) root.style.setProperty('--tg-button', themeParams.button_color)
      if (themeParams.button_text_color) root.style.setProperty('--tg-button-text', themeParams.button_text_color)
      if (themeParams.secondary_bg_color) root.style.setProperty('--tg-secondary-bg', themeParams.secondary_bg_color)
    }

    applyTheme()
    tg.onEvent?.('themeChanged', applyTheme)

    return () => {
      tg.offEvent?.('themeChanged', applyTheme)
    }
  }, [tg])

  // Telegram BackButton: показываем на всех шагах onboarding кроме welcome
  // (там нет предыдущего шага — goBack был бы no-op).
  useBackButton(goBack, step !== 'welcome' && step !== 'dashboard')

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

  const handleActivateTrial = useCallback(async () => {
    // Сбрасываем предыдущее состояние — каждая новая попытка стартует с чистого листа.
    setTrialError(null)
    setTrialSuccess(false)
    setTrialHasStarted(true)
    const result = await activateTrial()
    if (result) {
      setTrialSuccess(true)
      await loadProfile()
      return
    }
    // activateTrial вернул null — это либо сетевая ошибка, либо 4xx/5xx.
    // useApi уже положил текст ошибки в свой error; берём его, чтобы не выдумывать своё.
    tg?.HapticFeedback?.notificationOccurred('error')
    setTrialError(error ?? 'Не удалось активировать триал. Попробуйте ещё раз.')
  }, [activateTrial, error, tg])

  const handlePreparingContinue = useCallback(() => {
    // Переход к следующему шагу. Сбрасываем trialSuccess, чтобы при возврате
    // preparing-экран не показал stale success.
    setTrialSuccess(false)
    goNext() // preparing -> connect
  }, [goNext])

  const handlePreparingRetry = useCallback(() => {
    handleActivateTrial()
  }, [handleActivateTrial])

  // Сбрасываем состояние preparing при уходе с этого шага.
  // Сам auto-trigger активации делает PreparingScreen через свой useEffect + onActivate.
  // Здесь только lifecycle: при повторном заходе на preparing экран смонтируется заново
  // (AnimatePresence + key="preparing") и useEffect вызовет onActivate автоматически.
  useEffect(() => {
    if (step !== 'preparing') {
      setTrialError(null)
      setTrialSuccess(false)
      setTrialHasStarted(false)
      trialStartedRef.current = false
    }
  }, [step])

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
      <div className="loading-screen" role="status" aria-live="polite">
        <div className="loading-spinner" aria-hidden="true" />
        <div className="loading-text">Загрузка...</div>
      </div>
    )
  }

  // Error state
  if (error && !profile) {
    return (
      <div className="error-screen" role="alert">
        <div className="error-icon" aria-hidden="true">
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
    <MotionConfig reducedMotion="user">
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
                  isLoading={loading}
                  error={trialError}
                  hasStarted={trialHasStarted}
                  onActivate={handleActivateTrial}
                  onContinue={handlePreparingContinue}
                  onBack={goBack}
                  onRetry={handlePreparingRetry}
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
                <TariffsScreen
                  key="tariffs"
                  balance={profile?.balance ?? 0}
                  autoPlanId={autoPlanId}
                  onAutoPlanConsumed={() => setAutoPlanId(null)}
                />
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
                  referralCount={profile?.referral_count ?? 0}
                  referralLink={profile?.referral_link ?? null}
                />
              )}
            </>
          )}
        </AnimatePresence>
      </main>

      {!isOnboarding && (
        <BottomNav activeTab={activeTab} onTabChange={setActiveTab} />
      )}
    </div>
    </MotionConfig>
  )
}
