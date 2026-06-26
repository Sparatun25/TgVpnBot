import { motion } from 'framer-motion'
import { useTelegram } from '../../hooks/useTelegram'

interface SuccessScreenProps {
  onComplete: () => void
}

export function SuccessScreen({ onComplete }: SuccessScreenProps) {
  const { tg } = useTelegram()

  const handleComplete = () => {
    tg?.HapticFeedback?.notificationOccurred('success')
    onComplete()
  }

  return (
    <motion.div
      className="onboarding-screen success-screen"
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.5, ease: [0.32, 0.72, 0, 1] }}
    >
      <motion.div
        className="success-animation"
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ duration: 0.6, ease: [0.32, 0.72, 0, 1], delay: 0.1 }}
      >
        <motion.div
          className="success-glow"
          animate={{ scale: [1, 1.2, 1], opacity: [0.3, 0.5, 0.3] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        />
        <motion.div
          className="success-cat-wrap"
          initial={{ scale: 0.6, rotate: -8 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ duration: 0.7, ease: [0.32, 0.72, 0, 1], delay: 0.2 }}
        >
          <img
            src="/cat-success.png"
            alt="Котик празднует успешное подключение"
            className="success-cat-image"
            draggable={false}
          />
        </motion.div>
      </motion.div>

      <motion.h2
        className="success-title"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.4 }}
      >
        VPN успешно подключен
      </motion.h2>

      <motion.p
        className="success-subtitle"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.5 }}
      >
        Пробный период уже активирован
      </motion.p>

      <motion.button
        className="success-cta"
        onClick={handleComplete}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.6 }}
        whileTap={{ scale: 0.96 }}
      >
        Перейти в приложение
      </motion.button>
    </motion.div>
  )
}
