import { useState, useEffect, useCallback } from 'react'
import { OnboardingStep, STORAGE_KEY } from '../types/onboarding'

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

  const resetOnboarding = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setStepState('welcome')
  }, [])

  const goNext = useCallback(() => {
    const stepOrder: OnboardingStep[] = [
      'welcome',
      'install',
      'preparing',
      'connect',
      'waiting',
      'success',
      'dashboard',
    ]
    const currentIndex = stepOrder.indexOf(step)
    if (currentIndex < stepOrder.length - 1) {
      setStep(stepOrder[currentIndex + 1])
    }
  }, [step, setStep])

  const goBack = useCallback(() => {
    const stepOrder: OnboardingStep[] = [
      'welcome',
      'install',
      'preparing',
      'connect',
      'waiting',
      'success',
      'dashboard',
    ]
    const currentIndex = stepOrder.indexOf(step)
    if (currentIndex > 0) {
      setStep(stepOrder[currentIndex - 1])
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
    resetOnboarding,
  }
}

function isValidStep(value: string): boolean {
  return ['welcome', 'install', 'preparing', 'connect', 'waiting', 'success', 'dashboard'].includes(value)
}
