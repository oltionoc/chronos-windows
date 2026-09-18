import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import './index.css';
import './i18n';
import App from './App.tsx';
import { AuthProvider } from './auth/AuthContext';
import { LicenseProvider } from './auth/LicenseContext';
import { ToastProvider } from './components/ui/Toast';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <LicenseProvider>
            <App />
          </LicenseProvider>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>
);
