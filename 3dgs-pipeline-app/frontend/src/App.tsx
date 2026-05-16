import './index.css'
import { SettingsProvider } from './providers/SettingsProvider';
import { SetupScreen } from './pages/SetupScreen';
import { useState, useContext } from 'react';
import { SettingsContext } from './providers/SettingsProvider';

import { MainPage } from './pages/MainPage';

function AppContent() {
  const settingsContext = useContext(SettingsContext);
  // For now, we'll always show the main page.
  // We can add back the setup screen logic later if needed.
  const proceeded = true; //useState(false);

  if (!proceeded || !settingsContext?.settings) {
    // return <SetupScreen onProceed={() => setProceeded(true)} />;
    // For now, let's assume settings are loaded and we can proceed.
  }

  return <MainPage />;
}


function App() {
  return (
    <SettingsProvider>
      <AppContent />
    </SettingsProvider>
  )
}

export default App
