import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { MemoriesProvider } from './state/MemoriesContext';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <MemoriesProvider>
        <App />
      </MemoriesProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
