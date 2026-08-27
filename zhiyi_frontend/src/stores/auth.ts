import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { login, logout } from '@/api'
import type { UserProfile, UserRole } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const role = ref<UserRole>('doctor')
  const user = ref<UserProfile | null>(null)
  const loggedIn = computed(() => Boolean(user.value))

  async function signIn(nextRole: UserRole = role.value) {
    role.value = nextRole
    user.value = await login(nextRole)
    localStorage.setItem('zhiyi-role', nextRole)
  }

  async function signOut() {
    try { await logout() } catch { /* 忽略网络错误 */ }
    user.value = null
    localStorage.removeItem('zhiyi-role')
    localStorage.removeItem('zhiyi-token')
    localStorage.removeItem('zhiyi-user')
  }

  function restore() {
    const storedRole = localStorage.getItem('zhiyi-role')
    if (storedRole === 'doctor' || storedRole === 'patient' || storedRole === 'admin') {
      void signIn(storedRole)
      return
    }
    if (storedRole) localStorage.removeItem('zhiyi-role')
  }

  return { role, user, loggedIn, signIn, signOut, restore }
})
