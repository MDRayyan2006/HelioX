import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
import { getAuth, GoogleAuthProvider } from "firebase/auth";
import { getFirestore } from "firebase/firestore";

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyDxjdS5JoBaklHnpXcHSFxswgP4on3jXms",
  authDomain: "heliox-56439.firebaseapp.com",
  projectId: "heliox-56439",
  storageBucket: "heliox-56439.firebasestorage.app",
  messagingSenderId: "934502696445",
  appId: "1:934502696445:web:01f86a77c92956f7668594",
  measurementId: "G-PEV339C2RZ"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = typeof window !== 'undefined' ? getAnalytics(app) : null;
export const auth = getAuth(app);
export const db = getFirestore(app);

// Google Auth Provider setup with forced consent screen for switching accounts
export const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({
  prompt: 'select_account'
});

export default app;
