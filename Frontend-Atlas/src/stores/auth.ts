import { ref } from 'vue'

export const isAuthenticated = ref(false)
export const user = ref({ name: '', email: '' })

export function login(email: string, password: string) {
  // Simulation de connexion
  if (email && password) {
    isAuthenticated.value = true
    user.value = { name: 'John Doe', email }
    localStorage.setItem('isAuthenticated', 'true')
    localStorage.setItem('user', JSON.stringify(user.value))
    return true
  }
  return false
}

export function logout() {
  isAuthenticated.value = false
  user.value = { name: '', email: '' }
  localStorage.removeItem('isAuthenticated')
  localStorage.removeItem('user')
}

export function initAuth() {
  const saved = localStorage.getItem('isAuthenticated')
  const savedUser = localStorage.getItem('user')
  
  if (saved === 'true' && savedUser) {
    isAuthenticated.value = true
    user.value = JSON.parse(savedUser)
  }
}