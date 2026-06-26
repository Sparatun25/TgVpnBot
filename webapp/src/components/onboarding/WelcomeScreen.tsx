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

const easeOut = [0.22, 1, 0.36, 1] as const

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

  return (
    <motion.div
      className="onboarding-screen welcome-screen"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5 }}
    >
      {/* MASCOT — сигнатурный элемент бренда в верхней части экрана.
          Маленький (110px), с дышащим violet halo. Задаёт тон, не доминирует. */}
      <motion.div
        className="welcome-mascot"
        initial={{ scale: 0.4, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.9, ease: easeOut, delay: 0.05 }}
      >
        <motion.div
          className="welcome-mascot__halo"
          animate={{ scale: [1, 1.18, 1], opacity: [0.5, 0.12, 0.5] }}
          transition={{ duration: 3.2, repeat: Infinity, ease: 'easeInOut' }}
        />

        <svg className="welcome-mascot__rings" viewBox="0 0 200 200" fill="none" aria-hidden="true">
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

        <motion.div
          className={`welcome-mascot__core${MASCOT_MODE === 'png' ? ' welcome-mascot__core--image' : ''}`}
          initial={{ scale: 0.6, rotate: -12 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ duration: 0.7, ease: easeOut, delay: 0.25 }}
        >
          {MASCOT_MODE === 'png' ? (
            <motion.div
              className="welcome-mascot__image-wrap"
              animate={{ y: [0, -3, 0] }}
              transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
            >
              <img
                src="/cat-mascot.png"
                alt="Onyx VPN кот-маскот"
                className="welcome-mascot__image"
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

      {/* HEADLINE — editorial typography. Eyebrow + display headline с italic акцентом.
          Лево-выровнено (override дефолтного onboarding-screen text-align: center).
          Это задаёт ритм всему экрану — никаких «продающих» centered заголовков. */}
      <motion.div
        className="welcome-headline"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: easeOut, delay: 0.5 }}
      >
        <div className="eyebrow eyebrow--accent">Onyx VPN</div>
        <h1 className="display-headline display-headline--l welcome-headline__title">
          Свобода интернета<br />
          <em className="display-headline--italic">в тишине котика</em>
        </h1>
        <p className="welcome-headline__subtitle">
          Премиальный VPN на&nbsp;AmneziaWG. 3&nbsp;дня бесплатно — без карты и&nbsp;смс.
        </p>
      </motion.div>

      <motion.hr
        className="hairline welcome-divider"
        aria-hidden="true"
        initial={{ opacity: 0, scaleX: 0 }}
        animate={{ opacity: 1, scaleX: 1 }}
        transition={{ duration: 0.6, delay: 0.7, ease: easeOut }}
        style={{ transformOrigin: 'left center' }}
      />

      {/* BENEFITS — нумерованный editorial list. Не карточки — строки с цифрами.
          Как список содержания в журнале: 01 / название / намёк справа.
          Каждая строка отделена hairline'ом. Никаких emoji-иконок, никаких bg-карточек. */}
      <motion.ul
        className="welcome-benefits"
        initial="hidden"
        animate="visible"
        variants={{
          hidden: {},
          visible: { transition: { staggerChildren: 0.08, delayChildren: 0.8 } },
        }}
      >
        <BenefitRow number="01" title="Скрытность" hint="DPI-обход" />
        <BenefitRow number="02" title="Скорость" hint="без потерь" />
        <BenefitRow number="03" title="Границы" hint="не для нас" />
      </motion.ul>

      <motion.hr
        className="hairline welcome-divider"
        aria-hidden="true"
        initial={{ opacity: 0, scaleX: 0 }}
        animate={{ opacity: 1, scaleX: 1 }}
        transition={{ duration: 0.6, delay: 1.05, ease: easeOut }}
        style={{ transformOrigin: 'left center' }}
      />

      {/* TRIAL — editorial row вместо карточки. Тонкая типографика: слева serif "Триал",
          справа ценa (старая зачёркнута, новая violet). Никакого shimmer, никакого gradient bg.
          Meta-строка снизу подсказывает, что входит. */}
      <motion.div
        className="welcome-trial"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: easeOut, delay: 1.15 }}
      >
        <div className="welcome-trial__top">
          <div className="welcome-trial__name">
            Триал на&nbsp;<em>3&nbsp;дня</em>
          </div>
          <div className="welcome-trial__price">
            <span className="welcome-trial__price-old">299 ₽</span>
            <span className="welcome-trial__price-new">0&nbsp;₽</span>
          </div>
        </div>
        <div className="welcome-trial__meta">
          Без карты · Без скрытых платежей · Активация за минуту
        </div>
      </motion.div>

      {/* Тонкий hint к MainButton — без анимированной стрелки, просто текст-намёк.
          Главная кнопка внизу сама привлекает внимание через haptic feedback при появлении. */}
      <motion.div
        className="welcome-hint"
        initial={{ opacity: 0 }}
        animate={{ opacity: [0, 0.5, 0.5] }}
        transition={{ duration: 2.4, delay: 2.0, times: [0, 0.4, 1] }}
      >
        Нажмите кнопку ниже
      </motion.div>
    </motion.div>
  )
}

/* ─── Подкомпоненты (компактно, чтобы не плодить файлы) ─── */

function BenefitRow({
  number,
  title,
  hint,
}: {
  number: string
  title: string
  hint: string
}) {
  return (
    <motion.li
      className="welcome-benefit"
      variants={{
        hidden: { opacity: 0, x: -8 },
        visible: { opacity: 1, x: 0, transition: { duration: 0.4, ease: easeOut } },
      }}
    >
      <span className="welcome-benefit__number">{number}</span>
      <span className="welcome-benefit__title">{title}</span>
      <span className="welcome-benefit__hint">{hint}</span>
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
