import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { useTelegram } from '../../hooks/useTelegram'

interface PreparingScreenProps {
  isLoading: boolean
  error?: string | null
  hasStarted: boolean
  onActivate: () => void
  onContinue: () => void
  onBack: () => void
  onRetry?: () => void
}

const loadingMessages = [
  'Создаем VPN-доступ...',
  'Готовим персональный ключ...',
  'Почти готово...',
]

const easeOut = [0.22, 1, 0.36, 1] as const

export function PreparingScreen({
  isLoading,
  error,
  hasStarted,
  onActivate,
  onContinue,
  onBack,
  onRetry,
}: PreparingScreenProps) {
  const { tg } = useTelegram()
  const [messageIndex, setMessageIndex] = useState(0)
  // Ref-гард: onActivate зовём ровно один раз за mount, даже если React strict mode
  // дёрнет useEffect дважды. Retry идёт через отдельный onRetry prop.
  const activatedRef = useRef(false)

  // Auto-trigger API on mount — реальный вызов, никаких фейковых таймеров.
  useEffect(() => {
    if (!activatedRef.current) {
      activatedRef.current = true
      onActivate()
    }
  }, [onActivate])

  // Цикл сообщений крутится только пока реально идёт загрузка.
  useEffect(() => {
    if (!isLoading) return

    const interval = setInterval(() => {
      setMessageIndex((prev) => {
        if (prev < loadingMessages.length - 1) {
          return prev + 1
        }
        return prev
      })
    }, 1500)

    return () => clearInterval(interval)
  }, [isLoading])

  // Success haptic — только когда API реально вернул успех.
  useEffect(() => {
    if (!isLoading && !error && hasStarted) {
      tg?.HapticFeedback?.notificationOccurred('success')
    }
  }, [isLoading, error, hasStarted, tg])

  const handleContinue = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    onContinue()
  }

  const handleBack = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    onBack()
  }

  // Сбрасываем messageIndex перед новой попыткой — иначе юзер после ошибки
  // видит «Почти готово...» с первой секунды retry, а не «Создаём VPN-доступ...».
  // Цикл сообщений (ниже) инкрементирует от текущего значения, и без сброса
  // пользователь теряет ощущение «новой попытки».
  const handleRetry = () => {
    setMessageIndex(0)
    onRetry?.()
  }

  const isSuccess = hasStarted && !isLoading && !error

  return (
    <motion.div
      className="onboarding-screen preparing-screen"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.4, ease: [0.32, 0.72, 0, 1] }}
    >
      <button className="back-button" onClick={handleBack} aria-label="Назад">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M19 12H5M12 19L5 12L12 5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {/* ANIMATION — спиннер для loading, галочка для success.
          В error-состоянии спиннер скрывается — остаётся только текст и CTA retry. */}
      <motion.div
        className="preparing-animation"
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ duration: 0.6, ease: [0.32, 0.72, 0, 1] }}
      >
        {isSuccess ? (
          <motion.div
            className="preparing-icon preparing-icon--success"
            initial={{ scale: 0, rotate: -180 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ duration: 0.5, ease: [0.32, 0.72, 0, 1] }}
          >
            <svg width="80" height="80" viewBox="0 0 80 80" fill="none" aria-hidden="true">
              <circle cx="40" cy="40" r="38" stroke="currentColor" strokeWidth="2" fill="none" />
              <motion.path
                d="M25 40L35 50L55 30"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="round"
                strokeLinejoin="round"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 0.5, delay: 0.2 }}
              />
            </svg>
          </motion.div>
        ) : !error ? (
          <motion.div
            className="preparing-icon preparing-icon--loading"
            animate={{ rotate: 360 }}
            transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
          >
            <svg width="80" height="80" viewBox="0 0 80 80" fill="none" aria-hidden="true">
              <circle cx="40" cy="40" r="38" stroke="rgba(255,255,255,0.1)" strokeWidth="2" fill="none" />
              <circle
                cx="40"
                cy="40"
                r="38"
                stroke="url(#preparing-spinner-grad)"
                strokeWidth="2"
                fill="none"
                strokeLinecap="round"
                strokeDasharray="60 180"
              />
              <defs>
                <linearGradient id="preparing-spinner-grad" x1="0" y1="0" x2="80" y2="80">
                  <stop stopColor="#A78BFA" />
                  <stop offset="1" stopColor="#7C3AED" />
                </linearGradient>
              </defs>
            </svg>
          </motion.div>
        ) : null}
      </motion.div>

      {/* HEADLINE — editorial: eyebrow + display headline с italic акцентом.
          Тот же ритм, что welcome/install/connect — единый визуальный язык.
          В error-состоянии headline остаётся таким же, меняется только eyebrow. */}
      <motion.div
        className="preparing-headline"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: easeOut, delay: 0.2 }}
        role={error ? 'alert' : undefined}
      >
        <div className="eyebrow">
          {error ? 'Ошибка активации' : isSuccess ? 'Готово' : 'Создаём ключ'}
        </div>
        <h2 className="display-headline display-headline--m preparing-headline__title">
          {error ? (
            <>Что-то пошло<br /><em className="display-headline--italic">не так</em></>
          ) : isSuccess ? (
            <>VPN-доступ<br /><em className="display-headline--italic">открыт</em></>
          ) : (
            <>Подготавливаем<br /><em className="display-headline--italic">ваш доступ</em></>
          )}
        </h2>
      </motion.div>

      <motion.p
        className="preparing-subtitle"
        key={messageIndex}
        initial={{ opacity: 0, y: 5 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -5 }}
        transition={{ duration: 0.3 }}
      >
        {error ? error : isSuccess ? 'Ваш персональный ключ создан и готов к импорту.' : loadingMessages[messageIndex]}
      </motion.p>

      {error && (
        <motion.button
          className="preparing-cta"
          onClick={handleRetry}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.3 }}
          whileTap={{ scale: 0.985 }}
        >
          Попробовать снова
        </motion.button>
      )}

      {isSuccess && (
        <motion.button
          className="preparing-cta"
          onClick={handleContinue}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.3 }}
          whileTap={{ scale: 0.985 }}
        >
          Продолжить
        </motion.button>
      )}
    </motion.div>
  )
}
