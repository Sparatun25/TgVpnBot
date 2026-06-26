import { motion } from 'framer-motion'
import { useTelegram } from '../../hooks/useTelegram'
import { useMainButton } from '../../hooks/useMainButton'

interface InstallScreenProps {
  onInstalled: () => void
}

const easeOut = [0.22, 1, 0.36, 1] as const

export function InstallScreen({ onInstalled }: InstallScreenProps) {
  const { tg } = useTelegram()

  const handleInstalled = () => {
    tg?.HapticFeedback?.impactOccurred('medium')
    onInstalled()
  }

  const openExternal = (url: string) => {
    tg?.HapticFeedback?.impactOccurred('light')
    if (tg?.openLink) {
      tg.openLink(url)
    } else {
      window.open(url, '_blank', 'noopener,noreferrer')
    }
  }

  const appStoreUrl = 'https://apps.apple.com/app/amnezia-vpn/id1600529900'
  const playStoreUrl = 'https://play.google.com/store/apps/details?id=org.amnezia.vpn'

  useMainButton({
    text: 'Я установил Amnezia VPN',
    onClick: handleInstalled,
  })

  return (
    <motion.div
      className="onboarding-screen install-screen"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
    >
      {/* Прогресс-индикатор: 1 → 2 → 3 шага онбординга */}
      <motion.div
        className="install-steps"
        aria-hidden="true"
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: easeOut }}
      >
        <span className="install-steps__dot install-steps__dot--done" />
        <span className="install-steps__line install-steps__line--done" />
        <span className="install-steps__dot install-steps__dot--active" />
        <span className="install-steps__line" />
        <span className="install-steps__dot" />
      </motion.div>

      <motion.div
        className="install-logo"
        initial={{ scale: 0.6, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.7, ease: easeOut, delay: 0.1 }}
      >
        {/* Pulsing rings — "ищем устройство" */}
        <div className="install-logo__pulse">
          <span className="install-logo__pulse-ring" />
          <span className="install-logo__pulse-ring install-logo__pulse-ring--delay" />
        </div>
        <svg width="92" height="92" viewBox="0 0 100 100" fill="none" aria-hidden="true">
          <defs>
            <linearGradient id="amnezia-grad" x1="30" y1="25" x2="70" y2="65">
              <stop stopColor="#FFFFFF" />
              <stop offset="1" stopColor="#A0A0A0" />
            </linearGradient>
          </defs>
          <circle cx="50" cy="50" r="46" fill="#121214" stroke="rgba(255,255,255,0.08)" strokeWidth="1.5" />
          {/* Stylized "A" for Amnezia */}
          <path
            d="M50 22L28 70H40L43 62H57L60 70H72L50 22Z"
            fill="url(#amnezia-grad)"
          />
          <path
            d="M46 50L50 38L54 50H46Z"
            fill="#0B0B0C"
            opacity="0.4"
          />
        </svg>
      </motion.div>

      {/* HEADLINE — editorial typography вместо «продающего» centered заголовка */}
      <motion.div
        className="install-headline"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: easeOut, delay: 0.2 }}
      >
        <div className="eyebrow">Шаг 2 из 3</div>
        <h2 className="display-headline display-headline--m install-headline__title">
          Установите<br />
          <em className="display-headline--italic">Amnezia VPN</em>
        </h2>
        <p className="install-headline__subtitle">
          Откройте магазин, установите приложение и&nbsp;вернитесь сюда.
        </p>
      </motion.div>

      {/* PLATFORMS — editorial rows вместо platform-cards.
          Каждая строка: цифра + название + subtitle + arrow.
          Минимум визуального шума — просто список с разделителями. */}
      <motion.ul
        className="install-platforms"
        initial="hidden"
        animate="visible"
        variants={{
          hidden: {},
          visible: { transition: { staggerChildren: 0.1, delayChildren: 0.4 } },
        }}
      >
        <PlatformRow
          number="01"
          title="App Store"
          subtitle="Для iPhone и iPad"
          icon={<AppleIcon />}
          onClick={() => openExternal(appStoreUrl)}
        />
        <PlatformRow
          number="02"
          title="Google Play"
          subtitle="Для Android"
          icon={<PlayIcon />}
          onClick={() => openExternal(playStoreUrl)}
        />
      </motion.ul>

      <motion.div
        className="install-hint"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5, delay: 0.8 }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.6" />
          <path d="M12 8 V12 M12 16 H12.01" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        <span>Не устанавливайте AmneziaWG — только Amnezia&nbsp;VPN</span>
      </motion.div>
    </motion.div>
  )
}

/* ─── Подкомпоненты ─── */

function PlatformRow({
  number,
  title,
  subtitle,
  icon,
  onClick,
}: {
  number: string
  title: string
  subtitle: string
  icon: React.ReactNode
  onClick: () => void
}) {
  return (
    <motion.li
      className="install-platform-row"
      variants={{
        hidden: { opacity: 0, y: 8 },
        visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: easeOut } },
      }}
    >
      <motion.button
        type="button"
        className="install-platform-button"
        onClick={onClick}
        whileTap={{ scale: 0.985 }}
        aria-label={`${title} — ${subtitle}`}
      >
        <span className="install-platform-row__number">{number}</span>
        <span className="install-platform-row__icon">{icon}</span>
        <span className="install-platform-row__text">
          <span className="install-platform-row__title">{title}</span>
          <span className="install-platform-row__subtitle">{subtitle}</span>
        </span>
        <span className="install-platform-row__arrow" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path d="M7 17 L17 7 M9 7 H17 V15" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </motion.button>
    </motion.li>
  )
}

function AppleIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M18.71 19.5C17.88 20.74 17 21.95 15.66 21.97C14.32 22 13.89 21.18 12.37 21.18C10.84 21.18 10.37 21.95 9.1 22C7.79 22.05 6.8 20.68 5.96 19.47C4.25 17 2.94 12.45 4.7 9.39C5.57 7.87 7.13 6.91 8.82 6.88C10.1 6.86 11.32 7.75 12.11 7.75C12.89 7.75 14.37 6.68 15.92 6.84C16.57 6.87 18.39 7.1 19.56 8.82C19.47 8.88 17.39 10.1 17.41 12.63C17.44 15.65 20.06 16.66 20.09 16.67C20.06 16.74 19.67 18.11 18.71 19.5ZM13 3.5C13.73 2.67 14.94 2.04 15.94 2C16.07 3.17 15.6 4.35 14.9 5.19C14.21 6.04 13.07 6.7 11.95 6.61C11.8 5.46 12.36 4.26 13 3.5Z" />
    </svg>
  )
}

function PlayIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M3,20.5V3.5C3,2.91 3.34,2.39 3.84,2.15L13.69,12L3.84,21.85C3.34,21.6 3,21.09 3,20.5M16.81,15.12L6.05,21.34L14.54,12.85L16.81,15.12M20.16,10.81C20.5,11.08 20.75,11.5 20.75,12C20.75,12.5 20.53,12.9 20.18,13.18L17.89,14.5L15.39,12L17.89,9.5L20.16,10.81M6.05,2.66L16.81,8.88L14.54,11.15L6.05,2.66Z" />
    </svg>
  )
}
