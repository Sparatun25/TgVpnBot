import { motion } from 'framer-motion'
import { useTelegram } from '../../hooks/useTelegram'
import { useMainButton } from '../../hooks/useMainButton'

// Маскот на Welcome-экране: переключатель между PNG-версией (актуальная, рисованная)
// и SVG-фоллбэком (старая стилизованная версия манэки-нэко с VPN-щитом).
// Чтобы откатиться на SVG — поменяй 'png' на 'svg' ниже.
// Сама SVG-функция CatMascot() живёт в этом же файле ниже и не удаляется,
// чтобы переключение было мгновенным без потери кода.
const MASCOT_MODE: 'png' | 'svg' = 'png'

interface WelcomeScreenProps {
  onStart: () => void
}

export function WelcomeScreen({ onStart }: WelcomeScreenProps) {
  const { tg } = useTelegram()

  const handleStart = () => {
    tg?.HapticFeedback?.impactOccurred('medium')
    onStart()
  }

  useMainButton({
    text: 'Начать бесплатно →',
    onClick: handleStart,
  })

  // Easing для "материальных" микро-взаимодействий (Эмиль Ковальски):
  // небольшой overshoot без потери ощущения управляемости.
  const easeOut = [0.22, 1, 0.36, 1] as const

  return (
    <motion.div
      className="onboarding-screen welcome-screen"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5 }}
    >
      {/* HERO — котик-маскот в "облаке защиты".
          Это наш сигнатурный элемент, который делает Onyx VPN запоминающимся. */}
      <div className="welcome-hero">
        <motion.div
          className="welcome-orb"
          initial={{ scale: 0.4, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.9, ease: easeOut, delay: 0.05 }}
        >
          {/* Дышащий glow halo — привлекает внимание к маскоту */}
          <motion.div
            className="welcome-orb__halo"
            animate={{ scale: [1, 1.18, 1], opacity: [0.55, 0.15, 0.55] }}
            transition={{ duration: 3.2, repeat: Infinity, ease: 'easeInOut' }}
          />

          {/* Концентрические "сигналы" — намёк на защиту данных */}
          <svg className="welcome-orb__rings" viewBox="0 0 200 200" fill="none" aria-hidden="true">
            <motion.circle
              cx="100" cy="100" r="92"
              stroke="rgba(255,255,255,0.10)"
              strokeWidth="1"
              strokeDasharray="2 6"
              animate={{ rotate: 360 }}
              transition={{ duration: 40, repeat: Infinity, ease: 'linear' }}
              style={{ transformOrigin: '100px 100px' }}
            />
            <motion.circle
              cx="100" cy="100" r="74"
              stroke="rgba(255,255,255,0.06)"
              strokeWidth="1"
              strokeDasharray="1 4"
              animate={{ rotate: -360 }}
              transition={{ duration: 28, repeat: Infinity, ease: 'linear' }}
              style={{ transformOrigin: '100px 100px' }}
            />
          </svg>

          {/* Сам маскот: PNG-картинка или SVG-фоллбэк — переключается через MASCOT_MODE выше */}
          <motion.div
            className={`welcome-orb__core${MASCOT_MODE === 'png' ? ' welcome-orb__core--image' : ''}`}
            initial={{ scale: 0.6, rotate: -12 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ duration: 0.7, ease: easeOut, delay: 0.25 }}
          >
            {MASCOT_MODE === 'png' ? (
              <motion.div
                className="welcome-orb__image-wrap"
                animate={{ y: [0, -3, 0] }}
                transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
              >
                <img
                  src="/cat-mascot.png"
                  alt="Onyx VPN кот-маскот"
                  className="welcome-orb__image"
                  draggable={false}
                />
              </motion.div>
            ) : (
              <motion.div
                animate={{ y: [0, -3, 0] }}
                transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
              >
                <CatMascot />
              </motion.div>
            )}
          </motion.div>
        </motion.div>

        <motion.div
          className="welcome-eyebrow"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.45 }}
        >
          <span className="welcome-eyebrow__dot" />
          Onyx VPN
        </motion.div>

        <motion.h1
          className="welcome-title"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: easeOut, delay: 0.55 }}
        >
          Свобода интернета<br />
          <span className="welcome-title__accent">под защитой котика</span>
        </motion.h1>

        <motion.p
          className="welcome-subtitle"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: easeOut, delay: 0.7 }}
        >
          Премиальный VPN на&nbsp;AmneziaWG. 3&nbsp;дня бесплатно — без карты и&nbsp;смс.
        </motion.p>
      </div>

      {/* Преимущества — три карточки с собственными иконками.
          Здесь нет эмодзи, только рукотворные SVG под эстетику бренда. */}
      <motion.ul
        className="welcome-benefits"
        initial="hidden"
        animate="visible"
        variants={{
          hidden: {},
          visible: { transition: { staggerChildren: 0.09, delayChildren: 0.85 } },
        }}
      >
        <BenefitCard
          title="Скрытность"
          hint="DPI-обход"
          icon={<ShieldIcon />}
          variant="primary"
        />
        <BenefitCard
          title="Скорость"
          hint="без потерь"
          icon={<BoltIcon />}
        />
        <BenefitCard
          title="Границы"
          hint="не для нас"
          icon={<GlobeIcon />}
        />
      </motion.ul>

      {/* Карточка триала — визуально показывает ценность и следующий шаг */}
      <motion.div
        className="welcome-trial-card"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: easeOut, delay: 1.15 }}
      >
        {/* "Shimmer" пробегает по карточке, чтобы привлечь взгляд */}
        <motion.div
          className="welcome-trial-card__shimmer"
          animate={{ x: ['-100%', '220%'] }}
          transition={{ duration: 3.5, repeat: Infinity, ease: 'easeInOut', repeatDelay: 1.2 }}
        />

        <div className="welcome-trial-card__head">
          <div className="welcome-trial-card__badge">
            <SparkleIcon />
            <span>3 дня</span>
          </div>
          <div className="welcome-trial-card__price">
            <span className="welcome-trial-card__price-old">299 ₽</span>
            <span className="welcome-trial-card__price-new">0 ₽</span>
          </div>
        </div>

        <ul className="welcome-trial-card__list">
          <TrialFeature delay={1.25}>Без привязки карты</TrialFeature>
          <TrialFeature delay={1.32}>Без скрытых платежей</TrialFeature>
          <TrialFeature delay={1.39}>Активация за 1 минуту</TrialFeature>
        </ul>

        <div className="welcome-trial-card__progress" aria-hidden="true">
          <motion.div
            className="welcome-trial-card__progress-bar"
            initial={{ width: '0%' }}
            animate={{ width: '100%' }}
            transition={{ duration: 2.4, ease: easeOut, delay: 1.5 }}
          />
        </div>
      </motion.div>

      {/* Тонкий hint к MainButton внизу — анимированная стрелка-намёк,
          что следующий шаг ждёт внизу. */}
      <motion.div
        className="welcome-hint"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: [0, 0.7, 0.7], y: [8, 0, 0] }}
        transition={{ duration: 2.4, delay: 2.0, times: [0, 0.4, 1] }}
      >
        <span>Нажмите кнопку ниже</span>
        <motion.div
          animate={{ y: [0, 4, 0] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
        >
          <ChevronDownIcon />
        </motion.div>
      </motion.div>
    </motion.div>
  )
}

/* ─── Подкомпоненты (компактно, чтобы не плодить файлы) ─── */

function BenefitCard({
  title,
  hint,
  icon,
  variant,
}: {
  title: string
  hint: string
  icon: React.ReactNode
  variant?: 'primary'
}) {
  return (
    <motion.li
      className={`benefit-card${variant === 'primary' ? ' benefit-card--primary' : ''}`}
      variants={{
        hidden: { opacity: 0, y: 14 },
        visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } },
      }}
      whileHover={{ y: -2 }}
      whileTap={{ scale: 0.98 }}
    >
      <div className="benefit-card__icon">{icon}</div>
      <div className="benefit-card__text">
        <div className="benefit-card__title">{title}</div>
        <div className="benefit-card__hint">{hint}</div>
      </div>
    </motion.li>
  )
}

function TrialFeature({ children, delay }: { children: React.ReactNode; delay: number }) {
  return (
    <motion.li
      className="welcome-trial-card__feature"
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4, delay }}
    >
      <CheckIcon />
      <span>{children}</span>
    </motion.li>
  )
}

/* ─── Иконки (custom, в стиле минимализма бренда) ─── */

function CatMascot() {
  // SVG-фоллбэк маскота: стилизованный манэки-нэко с VPN-щитом.
  // Используется, когда MASCOT_MODE === 'svg'.
  // Визуальный стиль соответствует аватарке бота: outline + закрытые ^ ^ глаза + фиолетовый щит.
  return (
    <svg width="120" height="120" viewBox="0 0 120 120" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="shield-grad" x1="40" y1="72" x2="80" y2="110" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#A78BFA" />
          <stop offset="1" stopColor="#7C3AED" />
        </linearGradient>
      </defs>

      {/* Ушки (внешние) — рисуем ДО тела, чтобы тело перекрыло основания */}
      <path
        d="M 38 24 L 32 50 L 52 44 Z"
        fill="#0B0B0C"
        stroke="#FFFFFF"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path
        d="M 82 24 L 88 50 L 68 44 Z"
        fill="#0B0B0C"
        stroke="#FFFFFF"
        strokeWidth="2"
        strokeLinejoin="round"
      />

      {/* Внутренняя деталь ушек — листочек-акцент (фиолетовый) */}
      <path d="M 39 32 L 41 44 L 47 39 Z" fill="rgba(167,139,250,0.5)" />
      <path d="M 81 32 L 79 44 L 73 39 Z" fill="rgba(167,139,250,0.5)" />

      {/* Тело — круглое, пухлое, как у манэки-нэко */}
      <path
        d="M 30 80 Q 28 102 42 108 L 78 108 Q 92 102 90 80 Q 90 70 60 70 Q 30 70 30 80 Z"
        fill="#0B0B0C"
        stroke="#FFFFFF"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />

      {/* Голова — круглая, поверх тела */}
      <ellipse
        cx="60"
        cy="50"
        rx="26"
        ry="24"
        fill="#0B0B0C"
        stroke="#FFFFFF"
        strokeWidth="2.2"
      />

      {/* Маленький листочек/корона на голове — как в аватарке бота */}
      <g transform="translate(60 18)">
        <path
          d="M 0 0 Q -3 -4 -7 -2 Q -5 4 0 2 Q 5 4 7 -2 Q 3 -4 0 0 Z"
          fill="#7C3AED"
          stroke="#FFFFFF"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
        <line x1="0" y1="2" x2="0" y2="6" stroke="#FFFFFF" strokeWidth="1.2" />
      </g>

      {/* Глаза — закрытые, улыбающиеся ^ ^ */}
      <path
        d="M 47 50 Q 52 45 57 50"
        stroke="#FFFFFF"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
      <path
        d="M 63 50 Q 68 45 73 50"
        stroke="#FFFFFF"
        strokeWidth="2.2"
        strokeLinecap="round"
      />

      {/* Носик — маленький треугольник */}
      <path
        d="M 58 57 L 62 57 L 60 60 Z"
        fill="#FFFFFF"
      />

      {/* Улыбка — характерная кошачья w-форма */}
      <path
        d="M 60 60 Q 56 65 53 63"
        stroke="#FFFFFF"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <path
        d="M 60 60 Q 64 65 67 63"
        stroke="#FFFFFF"
        strokeWidth="1.6"
        strokeLinecap="round"
      />

      {/* Усы — по две с каждой стороны */}
      <line x1="34" y1="58" x2="46" y2="59" stroke="#FFFFFF" strokeWidth="1" strokeLinecap="round" opacity="0.7" />
      <line x1="34" y1="62" x2="46" y2="62" stroke="#FFFFFF" strokeWidth="1" strokeLinecap="round" opacity="0.5" />
      <line x1="86" y1="58" x2="74" y2="59" stroke="#FFFFFF" strokeWidth="1" strokeLinecap="round" opacity="0.7" />
      <line x1="86" y1="62" x2="74" y2="62" stroke="#FFFFFF" strokeWidth="1" strokeLinecap="round" opacity="0.5" />

      {/* Лапки — держат щит снизу */}
      <ellipse cx="48" cy="98" rx="5" ry="4" fill="#0B0B0C" stroke="#FFFFFF" strokeWidth="1.6" />
      <ellipse cx="72" cy="98" rx="5" ry="4" fill="#0B0B0C" stroke="#FFFFFF" strokeWidth="1.6" />

      {/* Щит — главный brand-элемент в лапах */}
      <path
        d="M 46 76 L 74 76 L 74 92 Q 74 102 60 108 Q 46 102 46 92 Z"
        fill="url(#shield-grad)"
        stroke="#FFFFFF"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />

      {/* Замочек на щите */}
      <g transform="translate(60 84)">
        <rect x="-4" y="-1" width="8" height="6" rx="1.5" fill="#FFFFFF" />
        <path
          d="M -2.5 -1 V -3 Q -2.5 -5 0 -5 Q 2.5 -5 2.5 -3 V -1"
          stroke="#FFFFFF"
          strokeWidth="1.2"
          fill="none"
          strokeLinecap="round"
        />
      </g>

      {/* "VPN" текст на щите */}
      <text
        x="60"
        y="101"
        textAnchor="middle"
        fontFamily="var(--font-display), Georgia, serif"
        fontSize="9"
        fontWeight="700"
        fill="#FFFFFF"
        letterSpacing="0.5"
      >
        VPN
      </text>
    </svg>
  )
}

function ShieldIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 2 L20 5 V11 C20 16 16 20.5 12 22 C8 20.5 4 16 4 11 V5 Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M9 12 L11 14 L15 10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function BoltIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M13 2 L4 14 H11 L9 22 L20 9 H13 Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  )
}

function GlobeIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
      <path d="M3 12 H21 M12 3 C15 7 15 17 12 21 C9 17 9 7 12 3" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 12.5 L10 17.5 L19 7.5" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function SparkleIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 0 L14 10 L24 12 L14 14 L12 24 L10 14 L0 12 L10 10 Z" />
    </svg>
  )
}

function ChevronDownIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 9 L12 15 L18 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
