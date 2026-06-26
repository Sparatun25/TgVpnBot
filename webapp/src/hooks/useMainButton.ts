import { useEffect, useRef } from 'react'
import { useTelegram } from './useTelegram'

interface UseMainButtonOptions {
  text: string
  onClick: () => void
  loading?: boolean
  active?: boolean
  color?: string
  textColor?: string
}

/**
 * Hook для управления Telegram MainButton.
 *
 * MainButton — нативная кнопка Telegram, рендерится клиентом в нижней части
 * экрана Mini App. Преимущества над кастомной:
 * - Автоматически адаптируется к теме пользователя.
 * - Не перекрывается клавиатурой.
 * - Поддерживает loading-состояние через showProgress().
 * - Скрывается/показывается без ререндера.
 *
 * Хук вызывает MainButton.show() при монтировании и MainButton.hide() при размонтировании,
 * чтобы не оставлять кнопку висеть после ухода с экрана.
 */
export function useMainButton({
  text,
  onClick,
  loading = false,
  active = true,
  color,
  textColor,
}: UseMainButtonOptions) {
  const { tg } = useTelegram()
  const onClickRef = useRef(onClick)
  onClickRef.current = onClick

  // Эффект 1: lifecycle (show / hide + подписка на onClick).
  useEffect(() => {
    if (!tg?.MainButton) return

    const handler = () => {
      tg.HapticFeedback?.impactOccurred('light')
      onClickRef.current()
    }

    tg.MainButton.onClick(handler)
    tg.MainButton.show()

    return () => {
      tg.MainButton.offClick(handler)
      tg.MainButton.hide()
    }
  }, [tg])

  // Эффект 2: текст.
  useEffect(() => {
    if (!tg?.MainButton) return
    if (tg.MainButton.text !== text) tg.MainButton.setText(text)
  }, [tg, text])

  // Эффект 3: цвет фона/текста.
  useEffect(() => {
    if (!tg?.MainButton) return
    if (color && tg.MainButton.color !== color) tg.MainButton.color = color
    if (textColor && tg.MainButton.textColor !== textColor) {
      tg.MainButton.textColor = textColor
    }
  }, [tg, color, textColor])

  // Эффект 4: активность (не путать с loading).
  useEffect(() => {
    if (!tg?.MainButton) return
    if (active) tg.MainButton.enable()
    else tg.MainButton.disable()
  }, [tg, active])

  // Эффект 5: loading / progress.
  useEffect(() => {
    if (!tg?.MainButton) return
    if (loading) tg.MainButton.showProgress(false)
    else tg.MainButton.hideProgress()
  }, [tg, loading])
}
