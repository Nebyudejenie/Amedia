/** UI store: sidebar state, theme, toasts. */
import { create } from 'zustand';

export interface Toast {
  id: number;
  message: string;
  type: 'success' | 'error' | 'info';
}

interface UiState {
  sidebarOpen: boolean;
  theme: 'light' | 'dark';
  toasts: Toast[];
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleTheme: () => void;
  addToast: (message: string, type?: Toast['type']) => void;
  removeToast: (id: number) => void;
}

let toastId = 0;

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: false,
  theme: 'light',
  toasts: [],

  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),

  toggleTheme: () =>
    set((s) => {
      const theme = s.theme === 'light' ? 'dark' : 'light';
      document.documentElement.classList.toggle('dark', theme === 'dark');
      return { theme };
    }),

  addToast: (message, type = 'info') => {
    const id = ++toastId;
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }));
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, 5000);
  },

  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
