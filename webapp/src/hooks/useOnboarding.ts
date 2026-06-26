import { useState, useEffect, useCallback } from 'react'
import { OnboardingStep, ONBOARDING_STEPS, STORAGE_KEY } from '../types/onboarding'

export function useOnboarding() {
  const [step, setStepState] = useState<OnboardingStep>(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && isValidStep(saved)) {
      return saved as OnboardingStep
    }
    return 'welcome'
  })

  const setStep = useCallback((newStep: OnboardingStep) => {
    setStepState(newStep)
    localStorage.setItem(STORAGE_KEY, newStep)
  }, [])

  const goNext = useCallback(() => {
    const currentIndex = ONBOARDING_STEPS.indexOf(step)
    if (currentIndex < ONBOARDING_STEPS.length - 1) {
      setStep(ONBOARDING_STEPS[currentIndex + 1])
    }
  }, [step, setStep])

  const goBack = useCallback(() => {
    const currentIndex = ONBOARDING_STEPS.indexOf(step)
    if (currentIndex > 0) {
      setStep(ONBOARDING_STEPS[currentIndex - 1])
    }
  }, [step, setStep])

  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && e.newValue && isValidStep(e.newValue)) {
        setStepState(e.newValue as OnboardingStep)
      }
    }
    window.addEventListener('storage', handleStorageChange)
    return () => window.removeEventListener('storage', handleStorageChange)
  }, [])

  return {
    step,
    setStep,
    goNext,
    goBack,
  }
}

function isValidStep(value: string): boolean {
  return ONBOARDING_STEPS.includes(value as OnboardingStep)
}
