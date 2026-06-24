import { useState, useCallback, useRef } from 'react'

const API_BASE = '/api'
const REQUEST_TIMEOUT = 30000 // 30 секунд

export interface ProfileData {
  balance: number
  referral_code: string
  subscription: {
    active: boolean
    plan_type: string | null
    expires_at: string | null
    connection_url: string | null
  }
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

export function useApi(getInitData: () => string) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const headers = useCallback(() => {
    const initData = getInitData()
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${initData}`,
    }
  }, [getInitData])

  const cancelRequest = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
  }, [])

  const getProfile = useCallback(async (): Promise<ProfileData | null> => {
    cancelRequest()
    const controller = new AbortController()
    abortControllerRef.current = controller

    setLoading(true)
    setError(null)

    const timeoutId = setTimeout(() => {
      controller.abort()
    }, REQUEST_TIMEOUT)

    try {
      const response = await fetch(`${API_BASE}/profile`, {
        method: 'GET',
        headers: headers(),
        signal: controller.signal,
      })

      clearTimeout(timeoutId)

      if (!response.ok) {
        throw new Error('Не удалось загрузить профиль')
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
      abortControllerRef.current = null
    }
  }, [headers, cancelRequest])

  const activateTrial = useCallback(async (): Promise<TrialResponse | null> => {
    cancelRequest()
    const controller = new AbortController()
    abortControllerRef.current = controller

    setLoading(true)
    setError(null)

    const timeoutId = setTimeout(() => {
      controller.abort()
    }, REQUEST_TIMEOUT)

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
      abortControllerRef.current = null
    }
  }, [headers, cancelRequest])

  const createPayment = useCallback(async (amountKopecks: number): Promise<PaymentResponse | null> => {
    cancelRequest()
    const controller = new AbortController()
    abortControllerRef.current = controller

    setLoading(true)
    setError(null)

    const timeoutId = setTimeout(() => {
      controller.abort()
    }, REQUEST_TIMEOUT)

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
      abortControllerRef.current = null
    }
  }, [headers, cancelRequest])

  return {
    loading,
    error,
    getProfile,
    activateTrial,
    createPayment,
    cancelRequest,
  }
}
