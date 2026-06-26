import { motion } from 'framer-motion'
import { useTelegram } from '../hooks/useTelegram'

type Tab = 'dashboard' | 'tariffs' | 'balance' | 'profile'

interface BottomNavProps {
  activeTab: Tab
  onTabChange: (tab: Tab) => void
}

const tabs: { id: Tab; label: string; icon: JSX.Element }[] = [
  {
    id: 'dashboard',
    label: 'VPN',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 2L2 7L12 12L22 7L12 2Z" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M2 17L12 22L22 17" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M2 12L12 17L22 12" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'tariffs',
    label: 'Тарифы',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 2V22M17 5H9.5C8.57174 5 7.6815 5.36875 7.02513 6.02513C6.36875 6.6815 6 7.57174 6 8.5C6 9.42826 6.36875 10.3185 7.02513 10.9749C7.6815 11.6313 8.57174 12 9.5 12H14.5C15.4283 12 16.3185 12.3687 16.9749 13.0251C17.6313 13.6815 18 14.5717 18 15.5C18 16.4283 17.6313 17.3185 16.9749 17.9749C16.3185 18.6313 15.4283 19 14.5 19H6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'balance',
    label: 'Баланс',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="2" y="6" width="20" height="12" rx="2" />
        <circle cx="12" cy="12" r="2" />
        <path d="M6 12H6.01M18 12H18.01" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'profile',
    label: 'Профиль',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M20 21V19C20 16.7909 18.2091 15 16 15H8C5.79086 15 4 16.7909 4 19V21" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="12" cy="7" r="4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
]

export function BottomNav({ activeTab, onTabChange }: BottomNavProps) {
  const { tg } = useTelegram()

  const handleTabClick = (tabId: Tab) => {
    tg?.HapticFeedback?.impactOccurred('light')
    onTabChange(tabId)
  }

  return (
    <motion.nav
      className="bottom-nav"
      aria-label="Основная навигация"
      initial={{ y: 100 }}
      animate={{ y: 0 }}
      transition={{ type: 'spring', damping: 25, stiffness: 200 }}
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={`nav-tab ${activeTab === tab.id ? 'active' : ''}`}
          onClick={() => handleTabClick(tab.id)}
          aria-current={activeTab === tab.id ? 'page' : undefined}
          aria-label={tab.label}
        >
          <div className="nav-tab-icon" aria-hidden="true">{tab.icon}</div>
          <span className="nav-tab-label">{tab.label}</span>
          {activeTab === tab.id && (
            <motion.div
              className="nav-tab-indicator"
              layoutId="nav-indicator"
              aria-hidden="true"
              transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            />
          )}
        </button>
      ))}
    </motion.nav>
  )
}
