import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider, createRouter, createRoute, createRootRoute } from '@tanstack/react-router'
import './index.css'
import App from './App.jsx'
import ReactBitsScreen from './features/react-bits/components/ReactBitsScreen.jsx'
import LandingPage from './features/landing/components/LandingPage.tsx'

const rootRoute = createRootRoute()

const landingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: LandingPage,
})

const dashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/dashboard',
  component: App,
})

const reactBitsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/react-bits',
  component: ReactBitsScreen,
})

const routeTree = rootRoute.addChildren([landingRoute, dashboardRoute, reactBitsRoute])
const router = createRouter({ routeTree })

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
