import { useState, useCallback } from 'react'

const API_BASE = '/api'
const REQUEST_TIMEOUT = 30000 // 30 секунд

export interface ProfileData {
  balance: number
  referral_code: string
  referral_count: number
  subscription: {
    active: boolean
    plan_type: string | null
    expires_at: string | null
    connection_url: string | null
  }
  has_used_trial: boolean
}

interface TrialResponse {
  message: string
  expires_at: string
  connection_url: string
}

interface PaymentResponse {
  payment_id: string
  payment_url: string
  qr_code: string
  amount_rubles: number
  status: string
}

export interface BackendTariff {
  id: string
  name: string
  price_kopecks: number
  price_rubles: number
  days: number
}

export function useApi(getInitData: () => string) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const headers = useCallback(() => {
    const initData = getInitData()
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${initData}`,
    }
  }, [getInitData])

  // Каждый запрос создаёт локальный AbortController со своим 30-секундным
  // таймаутом. Раньше был общий abortControllerRef, который отменял ЛЮБОЙ
  // предыдущий запрос при старте нового — это значило, что loadProfile в
  // фоне + клик "Купить" убивали профильный fetch. Per-request контроллеры
  // позволяют запросам идти параллельно; таймаут и cleanup на стороне
  // вызывающего компонента изолированы.
  const getProfile = useCallback(async (): Promise<ProfileData | null> => {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT)

    setLoading(true)
    setError(null)

    // Проверяем наличие initData (Mini App открыт в Telegram)
    const initData = getInitData()
    if (!initData) {
      clearTimeout(timeoutId)
      setError('Откройте приложение через Telegram')
      setLoading(false)
      return null
    }

    try {
      const response = await fetch(`${API_BASE}/profile`, {
        method: 'GET',
        headers: headers(),
        signal: controller.signal,
      })

      clearTimeout(timeoutId)

      // 401 = нет initData / невалидный токен
      // 404 = пользователь не найден в БД (новый юзер) — показываем экран триала
      if (response.status === 401 || response.status === 404) {
        return null
      }

      if (!response.ok) {
        // Пытаемся получить детальное сообщение от бэкенда
        let detail = ''
        try {
          const data = await response.json()
          detail = data.detail || ''
        } catch { /* ignore */ }

        if (response.status === 500) {
          throw new Error(detail || 'Внутренняя ошибка сервера')
        }
        if (response.status === 502) {
          throw new Error(detail || 'Сервер недоступен. Попробуйте позже.')
        }
        if (response.status === 401) {
          throw new Error(detail || 'Ошибка авторизации. Перезапустите приложение.')
        }
        throw new Error(detail || `Не удалось загрузить профиль (${response.status})`)
      }

      return await response.json()
    } catch (err) {
      clearTimeout(timeoutId)
      if (err instanceof Error && err.name === 'AbortError') {
        setError('Превышено время ожидания. Попробуйте снова.')
      } else {
        setError(err instanceof Error ? err.message : 'Ошибка сети')
      }
      return null
    } finally {
      setLoading(false)
    }
  }, [headers])

  const activateTrial = useCallback(async (): Promise<TrialResponse | null> => {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT)

    setLoading(true)
    setError(null)

    try {
      const response = await fetch(`${API_BASE}/subscription/trial`, {
        method: 'POST',
        headers: headers(),
        signal: controller.signal,
      })

      clearTimeout(timeoutId)

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Не удалось активировать триал')
      }

      return await response.json()
    } catch (err) {
      clearTimeout(timeoutId)
      if (err instanceof Error && err.name === 'AbortError') {
        setError('Превышено время ожидания. Попробуйте снова.')
      } else {
        setError(err instanceof Error ? err.message : 'Ошибка сети')
      }
      return null
    } finally {
      setLoading(false)
    }
  }, [headers])

  const createPayment = useCallback(async (amountKopecks: number): Promise<PaymentResponse | null> => {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT)

    setLoading(true)
    setError(null)

    try {
      const response = await fetch(`${API_BASE}/payment/create`, {
        method: 'POST',
        headers: headers(),
        signal: controller.signal,
        body: JSON.stringify({ amount_kopecks: amountKopecks }),
      })

      clearTimeout(timeoutId)

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Не удалось создать платеж')
      }

      return await response.json()
    } catch (err) {
      clearTimeout(timeoutId)
      if (err instanceof Error && err.name === 'AbortError') {
        setError('Превышено время ожидания. Попробуйте снова.')
      } else {
        setError(err instanceof Error ? err.message : 'Ошибка сети')
      }
      return null
    } finally {
      setLoading(false)
    }
  }, [headers])

  const purchaseSubscription = useCallback(async (tariffId: string): Promise<TrialResponse | null> => {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT)

    setLoading(true)
    setError(null)

    try {
      const response = await fetch(`${API_BASE}/subscription/purchase`, {
        method: 'POST',
        headers: headers(),
        signal: controller.signal,
        body: JSON.stringify({ tariff_id: tariffId }),
      })

      clearTimeout(timeoutId)

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Не удалось купить подписку')
      }

      return await response.json()
    } catch (err) {
      clearTimeout(timeoutId)
      if (err instanceof Error && err.name === 'AbortError') {
        setError('Превышено время ожидания. Попробуйте снова.')
      } else {
        setError(err instanceof Error ? err.message : 'Ошибка сети')
      }
      return null
    } finally {
      setLoading(false)
    }
  }, [headers])

  const getTariffs = useCallback(async (signal?: AbortSignal): Promise<BackendTariff[] | null> => {
    // Compose caller-provided signal with the standard timeout.
    // Either signal aborting cancels the network request.
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT)

    const onCallerAbort = () => controller.abort()
    if (signal) {
      if (signal.aborted) {
        clearTimeout(timeoutId)
        return null
      }
      signal.addEventListener('abort', onCallerAbort)
    }

    try {
      const response = await fetch(`${API_BASE}/tariffs`, {
        method: 'GET',
        headers: headers(),
        signal: controller.signal,
      })

      if (!response.ok) {
        return null
      }

      const data = await response.json()
      return data.tariffs ?? null
    } catch {
      return null
    } finally {
      clearTimeout(timeoutId)
      if (signal) signal.removeEventListener('abort', onCallerAbort)
    }
  }, [headers])

  return {
    loading,
    error,
    getProfile,
    getTariffs,
    activateTrial,
    createPayment,
    purchaseSubscription,
  }
}
