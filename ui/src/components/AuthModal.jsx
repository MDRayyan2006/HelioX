import { useState } from 'react';
import { auth, googleProvider } from '../firebase';
import { createUserWithEmailAndPassword, signInWithEmailAndPassword, signInWithPopup } from 'firebase/auth';

export default function AuthModal({ isOpen, onClose }) {
  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    
    try {
      if (isSignUp) {
        await createUserWithEmailAndPassword(auth, email, password);
      } else {
        await signInWithEmailAndPassword(auth, email, password);
      }
      onClose(); // Close modal on success
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setError(null);
    setIsLoading(true);
    try {
      await signInWithPopup(auth, googleProvider);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in font-plus-jakarta">
      <div className="glass-panel p-8 rounded-3xl w-full max-w-sm relative border border-outline-variant/20 shadow-[0_0_40px_-15px_rgba(0,240,255,0.2)]">
        <button onClick={onClose} className="absolute top-4 right-5 text-xl font-bold text-helio-text-muted hover:text-white transition-colors cursor-pointer">
          ✕
        </button>
        <h2 className="text-3xl font-extrabold text-white mb-6 text-center tracking-tight">
          {isSignUp ? 'Create Account' : 'Welcome Back'}
        </h2>
        
        {error && <p className="text-red-400 text-sm mb-6 text-center bg-red-500/10 p-2 rounded-lg">{error}</p>}
        
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email address"
            className="w-full bg-surface-container-highest/50 border border-outline-variant/30 text-white rounded-2xl px-5 py-3.5 focus:outline-none focus:border-helio-primary focus:ring-1 focus:ring-helio-primary transition-all placeholder:text-zinc-500"
            required
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            className="w-full bg-surface-container-highest/50 border border-outline-variant/30 text-white rounded-2xl px-5 py-3.5 focus:outline-none focus:border-helio-primary focus:ring-1 focus:ring-helio-primary transition-all placeholder:text-zinc-500"
            required
          />
          <button
            type="submit"
            disabled={isLoading}
            className="w-full mt-2 bg-primary-container text-on-primary-container font-black tracking-tight py-4 rounded-full hover:scale-95 transition-transform shadow-[0_10px_20px_-10px_rgba(0,240,255,0.3)] disabled:opacity-50 cursor-pointer"
          >
            {isLoading ? 'Processing...' : (isSignUp ? 'SIGN UP' : 'SIGN IN')}
          </button>
        </form>

        <div className="flex items-center gap-4 my-6">
          <div className="flex-1 h-px bg-white/10"></div>
          <span className="text-zinc-500 text-xs font-bold tracking-widest uppercase">Or</span>
          <div className="flex-1 h-px bg-white/10"></div>
        </div>

        <button
          onClick={handleGoogleSignIn}
          disabled={isLoading}
          className="w-full bg-white/5 hover:bg-white/10 border border-white/10 text-white font-semibold py-3.5 rounded-2xl flex items-center justify-center gap-3 transition-colors disabled:opacity-50 cursor-pointer"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
            <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
          </svg>
          Continue with Google
        </button>
        
        <p className="text-zinc-400 text-sm text-center mt-6">
          {isSignUp ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button onClick={() => { setIsSignUp(!isSignUp); setError(null); }} className="text-helio-primary font-bold hover:underline cursor-pointer">
            {isSignUp ? 'Sign In' : 'Sign Up'}
          </button>
        </p>
      </div>
    </div>
  );
}
