import { useEffect, useState } from 'react'

export interface TelegramUser {
  id: number
  first_name: string
  last_name?: string
  username?: string
  photo_url?: string
  language_code?: string
}

interface TelegramWebApp {
  initData: string
  initDataUnsafe: {
    user?: TelegramUser
    query_id?: string
  }
  ready: () => void
  expand: () => void
  close: () => void
  openLink: (url: string) => void
  openTelegramLink: (url: string) => void
  MainButton: {
    text: string
    color: string
    textColor: string
    isVisible: boolean
    isActive: boolean
    isProgressVisible: boolean
    setText: (text: string) => void
    show: () => void
    hide: () => void
    enable: () => void
    disable: () => void
    onClick: (cb: () => void) => void
    offClick: (cb: () => void) => void
    showProgress: (leaveActive?: boolean) => void
    hideProgress: () => void
  }
  BackButton: {
    isVisible: boolean
    show: () => void
    hide: () => void
    onClick: (cb: () => void) => void
    offClick: (cb: () => void) => void
  }
  HapticFeedback: {
    impactOccurred: (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => void
    notificationOccurred: (type: 'error' | 'success' | 'warning') => void
  }
  themeParams: Record<string, string>
  colorScheme: 'light' | 'dark'
  /**
   * TG 7.7+: габариты safe-area внутри WebView, перекрытые Telegram UI
   * (MainButton, BottomBar, top panel). top/left/right/bottom в px.
   * Используем contentSafeAreaInset.bottom как источник истины для нижнего
   * отступа контента, иначе MainButton перекрывает последние строки.
   */
  contentSafeAreaInset?: { top: number; bottom: number; left: number; right: number }
  /** TG 7.7+: высота WebView с учётом всех chrome-элементов Telegram. */
  viewportStableHeight?: number
  /** Текущая высота WebView (сокращается при показе MainButton/клавиатуры). */
  viewportHeight?: number
  onEvent: (event: string, handler: () => void) => void
  offEvent: (event: string, handler: () => void) => void
}

declare global {
  interface Window {
    Telegram?: {
      WebApp: TelegramWebApp
    }
  }
}

export function useTelegram() {
  const [tg, setTg] = useState<TelegramWebApp | null>(null)
  const [user, setUser] = useState<TelegramUser | null>(null)
  const [sdkReady, setSdkReady] = useState(false)
  const [retryCount, setRetryCount] = useState(0)

  useEffect(() => {
    const checkSdk = () => {
      const webApp = window.Telegram?.WebApp

      if (webApp) {
        webApp.ready()
        webApp.expand()
        setTg(webApp)
        setUser(webApp.initDataUnsafe.user || null)
        setSdkReady(true)
      } else if (retryCount < 3) {
        // SDK не загрузился — пробуем ещё раз (до 3 раз)
        const timer = setTimeout(() => {
          setRetryCount(prev => prev + 1)
        }, 500)
        return () => clearTimeout(timer)
      } else {
        setSdkReady(true)
      }
    }

    checkSdk()
  }, [retryCount])

  const getInitData = () => window.Telegram?.WebApp?.initData || ''

  // Определяем платформу для deep links
  const platform: 'ios' | 'android' | 'desktop' = (() => {
    const ua = navigator.userAgent.toLowerCase()
    if (/iphone|ipad|ipod/.test(ua)) return 'ios'
    if (/android/.test(ua)) return 'android'
    return 'desktop'
  })()

  return { tg, user, getInitData, sdkReady, platform }
}
