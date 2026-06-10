import { ref, computed, onMounted, onUnmounted } from 'vue'

export type Breakpoint = 'mobile' | 'tablet' | 'desktop' | 'wide'

export function useResponsive() {
  const windowWidth = ref(window.innerWidth)

  function updateWidth() {
    windowWidth.value = window.innerWidth
  }

  onMounted(() => {
    window.addEventListener('resize', updateWidth)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', updateWidth)
  })

  const breakpoint = computed<Breakpoint>(() => {
    if (windowWidth.value < 768) return 'mobile'
    if (windowWidth.value < 1024) return 'tablet'
    if (windowWidth.value < 1440) return 'desktop'
    return 'wide'
  })

  const isMobile = computed(() => breakpoint.value === 'mobile')
  const isTablet = computed(() => breakpoint.value === 'tablet')
  const isDesktop = computed(() => breakpoint.value === 'desktop')
  const isWide = computed(() => breakpoint.value === 'wide')
  const isMobileOrTablet = computed(() => isMobile.value || isTablet.value)

  return {
    windowWidth,
    breakpoint,
    isMobile,
    isTablet,
    isDesktop,
    isWide,
    isMobileOrTablet,
  }
}
