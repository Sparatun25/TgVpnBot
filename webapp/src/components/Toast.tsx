import { useEffect, useState } from 'react'

interface ToastProps {
  message: string
  visible: boolean
  onHide: () => void
}

export function Toast({ message, visible, onHide }: ToastProps) {
  const [show, setShow] = useState(false)

  useEffect(() => {
    if (visible) {
      setShow(true)
      const timer = setTimeout(() => {
        setShow(false)
        setTimeout(onHide, 300)
      }, 2500)
      return () => clearTimeout(timer)
    }
  }, [visible, onHide])

  if (!visible && !show) return null

  return (
    <div className={`toast ${show ? 'toast-visible' : 'toast-hidden'}`}>
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10" r="10" fill="#10B981" />
        <path d="M6 10L9 13L14 7" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span>{message}</span>
    </div>
  )
}
