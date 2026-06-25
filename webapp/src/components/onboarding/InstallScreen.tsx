import { motion } from 'framer-motion'
import { useTelegram } from '../../hooks/useTelegram'

interface InstallScreenProps {
  onInstalled: () => void
}

export function InstallScreen({ onInstalled }: InstallScreenProps) {
  const { tg } = useTelegram()

  const handleInstalled = () => {
    tg?.HapticFeedback?.impactOccurred('light')
    onInstalled()
  }

  const appStoreUrl = 'https://apps.apple.com/app/amnezia-vpn/id1600529900'
  const playStoreUrl = 'https://play.google.com/store/apps/details?id=org.amnezia.vpn'

  return (
    <motion.div
      className="onboarding-screen"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.4, ease: [0.32, 0.72, 0, 1] }}
    >
      <motion.div
        className="install-logo"
        initial={{ scale: 0, rotate: -180 }}
        animate={{ scale: 1, rotate: 0 }}
        transition={{ duration: 0.6, ease: [0.32, 0.72, 0, 1], delay: 0.1 }}
      >
        <svg width="100" height="100" viewBox="0 0 100 100" fill="none">
          <circle cx="50" cy="50" r="48" fill="#121214" stroke="rgba(255,255,255,0.06)" strokeWidth="2" />
          <path
            d="M50 25L30 65H40L45 55H55L60 65H70L50 25Z"
            fill="url(#amnezia-gradient)"
          />
          <defs>
            <linearGradient id="amnezia-gradient" x1="30" y1="25" x2="70" y2="65">
              <stop stopColor="#FFFFFF" />
              <stop offset="1" stopColor="#A0A0A0" />
            </linearGradient>
          </defs>
        </svg>
      </motion.div>

      <motion.h2
        className="install-title"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.2 }}
      >
        Установите Amnezia VPN
      </motion.h2>

      <motion.p
        className="install-description"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.3 }}
      >
        Для подключения к Onyx VPN потребуется приложение Amnezia VPN
      </motion.p>

      <motion.div
        className="platform-cards"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.4 }}
      >
        <a
          href={appStoreUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="platform-card"
          onClick={() => tg?.HapticFeedback?.impactOccurred('light')}
        >
          <svg width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
            <path d="M18.71 19.5C17.88 20.74 17 21.95 15.66 21.97C14.32 22 13.89 21.18 12.37 21.18C10.84 21.18 10.37 21.95 9.1 22C7.79 22.05 6.8 20.68 5.96 19.47C4.25 17 2.94 12.45 4.7 9.39C5.57 7.87 7.13 6.91 8.82 6.88C10.1 6.86 11.32 7.75 12.11 7.75C12.89 7.75 14.37 6.68 15.92 6.84C16.57 6.87 18.39 7.1 19.56 8.82C19.47 8.88 17.39 10.1 17.41 12.63C17.44 15.65 20.06 16.66 20.09 16.67C20.06 16.74 19.67 18.11 18.71 19.5ZM13 3.5C13.73 2.67 14.94 2.04 15.94 2C16.07 3.17 15.6 4.35 14.9 5.19C14.21 6.04 13.07 6.7 11.95 6.61C11.8 5.46 12.36 4.26 13 3.5Z" />
          </svg>
          <div className="platform-info">
            <div className="platform-label">Для iPhone и iPad</div>
            <div className="platform-name">App Store</div>
          </div>
        </a>

        <a
          href={playStoreUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="platform-card"
          onClick={() => tg?.HapticFeedback?.impactOccurred('light')}
        >
          <svg width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
            <path d="M3,20.5V3.5C3,2.91 3.34,2.39 3.84,2.15L13.69,12L3.84,21.85C3.34,21.6 3,21.09 3,20.5M16.81,15.12L6.05,21.34L14.54,12.85L16.81,15.12M20.16,10.81C20.5,11.08 20.75,11.5 20.75,12C20.75,12.5 20.53,12.9 20.18,13.18L17.89,14.5L15.39,12L17.89,9.5L20.16,10.81M6.05,2.66L16.81,8.88L14.54,11.15L6.05,2.66Z" />
          </svg>
          <div className="platform-info">
            <div className="platform-label">Для Android</div>
            <div className="platform-name">Google Play</div>
          </div>
        </a>
      </motion.div>

      <motion.button
        className="install-cta"
        onClick={handleInstalled}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.5 }}
        whileTap={{ scale: 0.96 }}
      >
        Я установил Amnezia VPN
      </motion.button>
    </motion.div>
  )
}
