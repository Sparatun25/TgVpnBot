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

export const ONBOARDING_STEP_INDEX: Record<OnboardingStep, number> = {
  welcome: 0,
  install: 1,
  preparing: 2,
  connect: 3,
  waiting: 4,
  success: 5,
  dashboard: 6,
}

export const STORAGE_KEY = 'onyx_onboarding_step'

export const isOnboardingStep = (step: OnboardingStep): boolean => {
  return step !== 'dashboard'
}

export const canGoBack = (step: OnboardingStep): boolean => {
  return step === 'preparing'
}
