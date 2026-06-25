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
  MainButton: {
    text: string
    color: string
    textColor: string
    isVisible: boolean
    isActive: boolean
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
  const platform = (() => {
    const ua = navigator.userAgent.toLowerCase()
    if (/iphone|ipad|ipod/.test(ua)) return 'ios'
    if (/android/.test(ua)) return 'android'
    return 'desktop'
  })()

  return { tg, user, getInitData, sdkReady, platform }
}
