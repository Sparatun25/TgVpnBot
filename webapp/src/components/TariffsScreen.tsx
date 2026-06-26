import { useState, useEffect, useRef, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useTelegram } from '../hooks/useTelegram'
import { useApi, BackendTariff } from '../hooks/useApi'
import { TopUpBottomSheet } from './TopUpBottomSheet'

interface TariffMeta {
  badge?: string
  popular?: boolean
  compact?: boolean
}

// UI-only metadata keyed by tariff id. Prices/days come from backend.
const TARIFF_META: Record<string, TariffMeta> = {
  year: { badge: 'Лучшее предложение', popular: true },
  quarter: { compact: true },
  monthly: { compact: true },
}

interface Tariff extends TariffMeta {
  id: string
  name: string
  price: number
  monthlyPrice?: number
  savings?: number
  period: string
}

const DAYS_IN_MONTH = 30

function enrichTariffs(tariffs: BackendTariff[]): Tariff[] {
  const monthlyPriceRef = tariffs.find(t => t.id === 'monthly')?.price_rubles ?? 0

  return tariffs.map(t => {
    const meta = TARIFF_META[t.id] ?? {}
    const months = t.days / DAYS_IN_MONTH
    const monthlyPrice = months > 1 ? Math.round(t.price_rubles / months) : undefined
    const savings = monthlyPriceRef > 0 && months > 1
      ? Math.round(monthlyPriceRef * months - t.price_rubles)
      : undefined

    return {
      id: t.id,
      name: t.name,
      price: t.price_rubles,
      monthlyPrice,
      savings: savings && savings > 0 ? savings : undefined,
      period: `${t.days} дней`,
      ...meta,
    }
  })
}

interface TariffsScreenProps {
  balance: number
  autoPlanId?: string | null
  onAutoPlanConsumed?: () => void
  // Колбэк после успешной покупки: родитель перезагрузит профиль и переключит
  // экран на дашборд. Это лучше, чем window.location.reload() — не теряем
  // стек состояний, нет вспышки полной перезагрузки страницы.
  onPurchaseComplete?: () => void
}

export function TariffsScreen({
  balance,
  autoPlanId,
  onAutoPlanConsumed,
  onPurchaseComplete,
}: TariffsScreenProps) {
  const { tg, getInitData } = useTelegram()
  const { purchaseSubscription, getTariffs, error: apiError } = useApi(getInitData)
  const [tariffs, setTariffs] = useState<Tariff[]>([])
  const [tariffsLoading, setTariffsLoading] = useState(true)
  const [purchasing, setPurchasing] = useState<string | null>(null)
  const [purchaseError, setPurchaseError] = useState<string | null>(null)
  const [showTopUp, setShowTopUp] = useState(false)
  const [requiredAmount, setRequiredAmount] = useState(0)
  const handledAutoPlanRef = useRef<string | null>(null)
  const isMountedRef = useRef(true)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  const loadTariffs = useCallback(() => {
    const controller = new AbortController()
    setTariffsLoading(true)
    setPurchaseError(null)
    getTariffs(controller.signal).then((data) => {
      if (controller.signal.aborted || !isMountedRef.current) return
      if (data) {
        setTariffs(enrichTariffs(data))
      }
      setTariffsLoading(false)
    })
    return () => controller.abort()
  }, [getTariffs])

  useEffect(() => {
    const cleanup = loadTariffs()
    return cleanup
  }, [loadTariffs])

  const handleBuy = useCallback(async (tariff: Tariff) => {
    tg?.HapticFeedback?.impactOccurred('light')

    if (balance < tariff.price * 100) {
      setRequiredAmount(tariff.price - balance / 100)
      setShowTopUp(true)
      return
    }

    setPurchaseError(null)
    setPurchasing(tariff.id)
    const result = await purchaseSubscription(tariff.id)

    if (!isMountedRef.current) return

    setPurchasing(null)

    if (result) {
      tg?.HapticFeedback?.notificationOccurred('success')
      // Передаём управление родителю: он перезагрузит профиль и переключит
      // экран. Никакого window.location.reload() — иначе теряется стек
      // анимаций/состояний и мигает вся страница.
      onPurchaseComplete?.()
    } else {
      tg?.HapticFeedback?.notificationOccurred('error')
      // Показываем реальную причину от useApi (сетевая, 4xx, 5xx),
      // а не generic-сообщение — иначе юзер не понимает, retry'ить или чинить сеть.
      setPurchaseError(apiError ?? 'Не удалось купить подписку. Попробуйте ещё раз.')
    }
  }, [balance, purchaseSubscription, tg, onPurchaseComplete, apiError])

  // Auto-buy from deep link (after tariffs + profile are loaded).
  useEffect(() => {
    if (!autoPlanId || handledAutoPlanRef.current === autoPlanId) return
    if (tariffsLoading) return

    // Тарифы не загрузились — нельзя автоматически купить. НЕ помечаем
    // autoPlanId как обработанный, чтобы при retry загрузки (или следующем
    // рендере после успешного fetch) попробовать снова. Иначе deep-link
    // "съедался" молча, и юзер видел экран тарифов без фидбэка.
    if (tariffs.length === 0) {
      setPurchaseError('Не удалось загрузить тарифы. Нажмите «Повторить», чтобы продолжить покупку.')
      return
    }

    const tariff = tariffs.find(t => t.id === autoPlanId)
    if (tariff) {
      // Помечаем ТОЛЬКО когда реально стартуем покупку. Если бы пометили
      // ДО if (тариф не найден), handledAutoPlanRef.current === autoPlanId
      // и при следующем ре-рендере useEffect вышел бы через ранний return —
      // юзер остался бы с молча «съеденным» deep-link без фидбэка.
      // Сейчас поведение симметрично ветке tariffs.length === 0 (тоже не помечаем).
      handledAutoPlanRef.current = autoPlanId
      handleBuy(tariff)
    } else {
      // Тариф из ссылки не найден в загруженном списке — устаревшая ссылка или
      // план снят с продажи. Показываем явную ошибку, чтобы юзер не гадал,
      // почему «ничего не произошло».
      setPurchaseError('Тариф из ссылки больше не доступен. Выберите тариф вручную.')
    }
    onAutoPlanConsumed?.()
  }, [autoPlanId, balance, tariffsLoading, tariffs, handleBuy, onAutoPlanConsumed])

  const handlePaymentSuccess = () => {
    // Родитель сам перезагрузит профиль и оставит юзера на экране тарифов,
    // чтобы он мог повторить покупку уже с пополненным балансом.
    onPurchaseComplete?.()
  }

  return (
    <motion.div
      className="tariffs-screen"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
    >
      <motion.div
        className="tariffs-header"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.05 }}
      >
        <div className="eyebrow">Подписка</div>
        <h2 className="tariffs-title">Выберите план</h2>
        <p className="tariffs-subtitle">
          Безлимитный трафик, AmneziaWG и&nbsp;защита от&nbsp;DPI на&nbsp;всех устройствах.
        </p>
      </motion.div>

      {tariffsLoading && (
        <div className="tariffs-status" role="status" aria-live="polite">
          <div className="tariffs-status__spinner" aria-hidden="true" />
          <div className="tariffs-status__text">Загружаем тарифы…</div>
        </div>
      )}

      {!tariffsLoading && tariffs.length === 0 && (
        <div className="tariffs-status" role="alert">
          <div className="tariffs-status__text">Не удалось загрузить тарифы</div>
          <button className="tariffs-status__retry" onClick={loadTariffs}>
            Повторить
          </button>
        </div>
      )}

      {!tariffsLoading && tariffs.length > 0 && (
        <motion.div
          className="tariffs-list"
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.08, delayChildren: 0.15 } },
          }}
        >
          {tariffs.map((tariff) => (
            <motion.button
              key={tariff.id}
              type="button"
              className={`tariff-row ${tariff.popular ? 'tariff-row--featured' : ''}`}
              onClick={() => handleBuy(tariff)}
              disabled={purchasing === tariff.id}
              aria-label={
                purchasing === tariff.id
                  ? `Подключение тарифа ${tariff.name}`
                  : `Подключить тариф ${tariff.name} за ${tariff.price} ₽`
              }
              variants={{
                hidden: { opacity: 0, y: 8 },
                visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] } },
              }}
            >
              <div className="tariff-row__left">
                <div className="tariff-row__name-row">
                  <span className="tariff-row__name">{tariff.name}</span>
                  {tariff.badge && <span className="tariff-row__badge">{tariff.badge}</span>}
                </div>
                <div className="tariff-row__meta">
                  {tariff.period}
                  {tariff.monthlyPrice && (
                    <> · <span className="tariff-row__meta--accent">{tariff.monthlyPrice} ₽/мес</span></>
                  )}
                  {tariff.savings && tariff.savings > 0 && (
                    <> · Экономия {tariff.savings} ₽</>
                  )}
                </div>
              </div>
              <div className="tariff-row__right">
                <div className="tariff-row__price">
                  <span className="tariff-row__price-value">{tariff.price}</span>
                  <span className="tariff-row__price-currency">₽</span>
                </div>
                <span className="tariff-row__period">{tariff.period}</span>
              </div>
            </motion.button>
          ))}
        </motion.div>
      )}

      {purchaseError && (
        <motion.div
          className="tariffs-purchase-error"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          role="alert"
        >
          <span>{purchaseError}</span>
          <button
            className="tariffs-purchase-error-dismiss"
            onClick={() => setPurchaseError(null)}
            aria-label="Закрыть ошибку"
          >
            ×
          </button>
        </motion.div>
      )}

      <TopUpBottomSheet
        isOpen={showTopUp}
        onClose={() => setShowTopUp(false)}
        requiredAmount={requiredAmount}
        onPaymentSuccess={handlePaymentSuccess}
      />
    </motion.div>
  )
}
