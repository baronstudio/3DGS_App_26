import './index.css'
import { SettingsProvider } from './providers/SettingsProvider';
import { SetupScreen } from './pages/SetupScreen';
import { useState, useContext } from 'react';
import { SettingsContext } from './providers/SettingsProvider';

function AppContent() {
  const settingsContext = useContext(SettingsContext);
  const [proceeded, setProceeded] = useState(false);

  if (!proceeded || !settingsContext?.settings) {
    return <SetupScreen onProceed={() => setProceeded(true)} />;
  }

  return (
    <>
      <h1 className="text-3xl font-bold underline">
        3DGS Pipeline App
      </h1>
      {/* The main app would go here */}
    </>
  );
}


function App() {
  return (
    <SettingsProvider>
      <AppContent />
    </SettingsProvider>
  )
}

export default App
