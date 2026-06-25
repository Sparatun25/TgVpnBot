# Onyx VPN — Project Context

## Project Overview
Telegram Mini App для VPN-сервиса Onyx VPN на базе AmneziaWG.

## Tech Stack

### Frontend (webapp/)
- **Framework**: React 18.3.1 + TypeScript 5.5.3
- **Build Tool**: Vite 5.4.1
- **Animations**: framer-motion 12.42.0
- **Styling**: CSS Variables
- **Integration**: Telegram WebApp SDK

### Backend (api/, bot/, services/)
- **Framework**: FastAPI + aiogram 3.x
- **Database**: PostgreSQL + SQLAlchemy 2.x (async)
- **VPN Engine**: AmneziaWG (Docker container)
- **Payments**: ЮKassa СБП

## Architecture

### Frontend Structure
```
webapp/src/
├── components/
│   ├── onboarding/          # Onboarding flow (Steps 0-5)
│   │   ├── WelcomeScreen.tsx
│   │   ├── InstallScreen.tsx
│   │   ├── PreparingScreen.tsx
│   │   ├── ConnectScreen.tsx
│   │   ├── WaitingScreen.tsx
│   │   └── SuccessScreen.tsx
│   ├── DashboardScreen.tsx  # Main dashboard after onboarding
│   ├── TariffsScreen.tsx    # Subscription plans
│   ├── BalanceScreen.tsx    # Balance & top-up
│   ├── ProfileScreen.tsx    # User profile & referrals
│   ├── BottomNav.tsx        # Bottom navigation (hidden during onboarding)
│   └── TopUpBottomSheet.tsx # Quick top-up modal
├── hooks/
│   ├── useTelegram.ts       # Telegram WebApp SDK integration
│   ├── useApi.ts           # API client with auth
│   └── useOnboarding.ts    # Onboarding state machine
├── types/
│   └── onboarding.ts       # Onboarding step types
├── App.tsx                  # Main app with routing
├── main.tsx                 # Entry point
└── index.css               # Global styles
```

## Key Features Implemented

### Onboarding Flow (State Machine)
- **Step 0**: Welcome screen with value proposition
- **Step 1**: Install Amnezia VPN (platform selection)
- **Step 2**: Preparing access (animated loading)
- **Step 3**: Connect Onyx VPN (clipboard + deep link)
- **Step 4**: Waiting for activation (45s timeout)
- **Step 5**: Success celebration
- **Dashboard**: Main app with VPN status, stats, insights

### State Persistence
- Onboarding step saved in `localStorage`
- Restored on app reload
- BottomNav hidden during onboarding

### Telegram Integration
- Haptic feedback on all interactions
- Theme params integration (dark mode)
- initData authentication
- Deep links for Amnezia VPN

### Payment Flow
- Quick top-up bottom sheet
- Payment status polling
- Auto-redirect after successful payment

### Animations
- iOS-style easing curves
- Framer Motion for page transitions
- 60 FPS optimized
- Reduced motion support

## Design System

### Colors
- Background: `#0B0B0C` (canvas)
- Cards: `#121214` (slate dark)
- Accent: `#FFFFFF` (primary CTA)
- Success: `#10B981` (emerald)
- Warning: `#F59E0B` (amber)
- Border: `rgba(255, 255, 255, 0.06)`

### Motion
- Duration: 250-450ms
- Easing: `cubic-bezier(0.32, 0.72, 0, 1)` (iOS)
- Scale on tap: 0.96

## Edge Cases Handled

1. **Clipboard API fallback** — manual copy textarea
2. **Amnezia launch failure** — calm error card (no red)
3. **45s activation timeout** — help button appears
4. **Insufficient balance** — auto-open top-up sheet
5. **Payment polling** — background status check
6. **Onboarding persistence** — localStorage restore

## Recent Changes

### 2026-06-25
- Complete frontend redesign with new onboarding flow
- State machine for onboarding (6 steps)
- Framer Motion animations
- Bottom navigation (hidden during onboarding)
- Top-up bottom sheet
- Dashboard with stats cards
- Updated design system (Onyx Premium Dark)
- Telegram SDK integration (haptics, theme)