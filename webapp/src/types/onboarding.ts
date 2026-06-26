export type OnboardingStep =
  | 'welcome'
  | 'install'
  | 'preparing'
  | 'connect'
  | 'waiting'
  | 'success'
  | 'dashboard'

export const ONBOARDING_STEPS: OnboardingStep[] = [
  'welcome',
  'install',
  'preparing',
  'connect',
  'waiting',
  'success',
  'dashboard',
]

export const STORAGE_KEY = 'onyx_onboarding_step'
