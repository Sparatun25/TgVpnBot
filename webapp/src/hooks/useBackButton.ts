import { useEffect, useRef } from 'react'
import { useTelegram } from './useTelegram'

/**
 * Hook для управления Telegram BackButton.
 *
 * BackButton появляется в шапке Mini App слева от заголовка.
 * При нажатии вызывает переданный колбэк (например, шаг назад в onboarding).
 *
 * Скрывается автоматически при размонтировании, чтобы не дублировать
 * системную кнопку «Назад» Telegram после ухода с экрана.
 */
export function useBackButton(onClick: () => void, visible: boolean = true) {
  const { tg } = useTelegram()
  const onClickRef = useRef(onClick)
  onClickRef.current = onClick

  useEffect(() => {
    if (!tg?.BackButton) return

    if (!visible) {
      tg.BackButton.hide()
      return
    }

    const handler = () => {
      tg.HapticFeedback?.impactOccurred('light')
      onClickRef.current()
    }

    tg.BackButton.onClick(handler)
    tg.BackButton.show()

    return () => {
      tg.BackButton.offClick(handler)
      tg.BackButton.hide()
    }
  }, [tg, visible])
}
