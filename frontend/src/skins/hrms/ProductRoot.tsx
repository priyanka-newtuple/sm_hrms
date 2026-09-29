import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { AuthProvider } from './auth/AuthContext';
import './product.css';

/** Compatibility product shell: preserves all legacy routes and role-scoped journeys. */
export default function ProductRoot() {
  return <BrowserRouter><AuthProvider><div className="hrms-product"><App /></div></AuthProvider></BrowserRouter>;
}
