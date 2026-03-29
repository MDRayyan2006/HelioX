import { useState, useCallback, useEffect, useRef } from 'react';
import { Link } from '@tanstack/react-router';
import QueryInput from './components/QueryInput';
import AnswerDisplay from './components/AnswerDisplay';
import ConfidenceMeter from './components/ConfidenceMeter';
import PipelineFlow from './components/PipelineFlow';
import DocumentUpload from './components/DocumentUpload';
import Sidebar from './components/Sidebar';
import AuthModal from './components/AuthModal';
import { queryPipeline, fetchTelemetry, fetchLearning } from './services/api';
import { onAuthStateChanged, signInWithPopup, signOut } from 'firebase/auth';
import { collection, addDoc, doc, updateDoc, onSnapshot, query, orderBy, serverTimestamp } from 'firebase/firestore';
import { auth, db, googleProvider } from './firebase';

export default function App() {
  const [user, setUser] = useState(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

  const [chats, setChats] = useState([]);
  const [currentChatId, setCurrentChatId] = useState(null);
  const [uploadedDocs, setUploadedDocs] = useState([]); // docs for the current chat

  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentQuery, setCurrentQuery] = useState('');
  const [result, setResult] = useState(null); // result for the current chat
  const [error, setError] = useState(null);
  const [telemetry, setTelemetry] = useState(null);
  const [learning, setLearning] = useState(null);
  const [showTelemetry, setShowTelemetry] = useState(false);

  // Fetch telemetry + learning data on mount and after each query
  const loadIntelligenceData = useCallback(async () => {
    const [t, l] = await Promise.all([fetchTelemetry(), fetchLearning()]);
    if (t) setTelemetry(t);
    if (l) setLearning(l);
  }, []);

  useEffect(() => { loadIntelligenceData(); }, [loadIntelligenceData]);

  const hasInitialized = useRef(false);

  // Auth & Chats Snapshot
  useEffect(() => {
    const unsubscribeAuth = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser);
      if (!currentUser) {
        setChats([]);
        setCurrentChatId(null);
        setResult(null);
        setUploadedDocs([]);
        hasInitialized.current = false;
      } else {
        if (!hasInitialized.current) {
          hasInitialized.current = true;
          addDoc(collection(db, 'users', currentUser.uid, 'chats'), {
            title: 'New Conversation',
            documents: [],
            result: null,
            createdAt: serverTimestamp(),
            updatedAt: serverTimestamp()
          }).then(docRef => {
            setCurrentChatId(docRef.id);
          });
        }
      }
    });
    return () => unsubscribeAuth();
  }, []);

  useEffect(() => {
    if (!user) return;
    const q = query(collection(db, 'users', user.uid, 'chats'), orderBy('updatedAt', 'desc'));
    const unsubscribe = onSnapshot(q, (snapshot) => {
      const chatList = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
      setChats(chatList);
    });
    return () => unsubscribe();
  }, [user]);

  // Handle switching chats
  const handleSelectChat = (chatId) => {
    const chat = chats.find(c => c.id === chatId);
    if (chat) {
      setCurrentChatId(chatId);
      setResult(chat.result || null);
      setUploadedDocs(chat.documents || []);
      setError(null);
    }
  };

  const handleNewChat = useCallback(async () => {
    if (!user) {
      setCurrentChatId(null);
      setResult(null);
      setUploadedDocs([]);
      setError(null);
      return;
    }
    const docRef = await addDoc(collection(db, 'users', user.uid, 'chats'), {
      title: 'New Conversation',
      documents: [],
      result: null,
      createdAt: serverTimestamp(),
      updatedAt: serverTimestamp()
    });
    setCurrentChatId(docRef.id);
    setResult(null);
    setUploadedDocs([]);
    setError(null);
  }, [user]);

  const handleSwitchAccount = async () => {
    try {
      await signOut(auth);
      await signInWithPopup(auth, googleProvider);
    } catch (err) {
      console.error("Account switch aborted or failed:", err);
    }
  };

  const handleUploadSuccess = useCallback(async (docInfo) => {
    const newDocsList = [...uploadedDocs, docInfo];
    setUploadedDocs(newDocsList);

    if (user && currentChatId) {
      await updateDoc(doc(db, 'users', user.uid, 'chats', currentChatId), {
        documents: newDocsList,
        updatedAt: serverTimestamp()
      });
    }
  }, [user, currentChatId, uploadedDocs]);

  const handleQuery = useCallback(async (queryStr, mode) => {
    setIsLoading(true);
    setResult(null);
    setError(null);
    setIsStreaming(false);
    setCurrentQuery(queryStr);

    try {
      const modeStr = mode === 'legacy' ? 'legacy' : 'multi-agent';
      const data = await queryPipeline(queryStr, modeStr);

      setResult(data);
      setIsLoading(false);
      setIsStreaming(true);
      setShowTelemetry(true);

      // Save to Firebase
      if (user && currentChatId) {
        const title = queryStr.substring(0, 40) + (queryStr.length > 40 ? '...' : '');

        await updateDoc(doc(db, 'users', user.uid, 'chats', currentChatId), {
          result: data,
          query: queryStr,
          title: title,
          documents: uploadedDocs,
          updatedAt: serverTimestamp()
        });
      }

      setTimeout(() => setIsStreaming(false), 3000);
      loadIntelligenceData();
    } catch (err) {
      setIsLoading(false);
      setError(err.message || 'Something went wrong.');
    }
  }, [user, currentChatId, uploadedDocs, loadIntelligenceData]);

  return (
    <div className={`bg-surface text-on-surface font-plus-jakarta relative overflow-hidden ${user ? 'flex h-screen' : 'min-h-screen'}`}>
      <AuthModal isOpen={isAuthModalOpen} onClose={() => setIsAuthModalOpen(false)} />

      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] rounded-full bg-helio-primary/[.04] blur-[120px]" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full bg-helio-accent-2/[.03] blur-[120px]" />
        <div className="absolute top-[40%] right-[20%] w-[30%] h-[30%] rounded-full bg-helio-accent/[.02] blur-[100px]" />
      </div>

      <Sidebar
        chats={chats}
        currentChatId={currentChatId}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChat}
        user={user}
        onSwitchAccount={handleSwitchAccount}
      />

      <div className={`flex-1 relative z-10 ${user ? 'overflow-y-auto h-screen' : ''}`}>
        {/* Top Navigation */}
        <nav className={`fixed top-0 z-50 bg-zinc-950/60 backdrop-blur-xl no-line bg-zinc-900/10 shadow-[0_0_40px_-15px_rgba(0,240,255,0.1)] transition-all duration-300 ${user ? 'w-[calc(100%-18rem)] right-0' : 'w-full'}`}>
          <div className="flex justify-between items-center px-8 py-4 max-w-screen-2xl mx-auto">
            {/* <Link to="/" className="text-xl font-bold tracking-tighter text-white uppercase font-plus-jakarta cursor-pointer hover:text-cyan-400 transition-colors">HelioX Dashboard ←</Link> */}
            <div className="hidden lg:flex items-center gap-10">
              <a className="text-cyan-400 font-semibold border-b border-cyan-400 pb-1 font-plus-jakarta text-sm tracking-tight hover:bg-white/5 transition-all duration-300" href="#" >Basic</a>
              <a className="text-zinc-400 hover:text-white transition-colors font-plus-jakarta text-sm tracking-tight hover:bg-white/5 transition-all duration-300" href="#" >Pro</a>
              <a className="text-zinc-400 hover:text-white transition-colors font-plus-jakarta text-sm tracking-tight hover:bg-white/5 transition-all duration-300" href="#" >Showcase</a>
              <a className="text-zinc-400 hover:text-white transition-colors font-plus-jakarta text-sm tracking-tight hover:bg-white/5 transition-all duration-300" href="#" >Docs</a>
            </div>
            <div className="flex items-center gap-6">
              {!user && (
                <>
                  <button onClick={() => setIsAuthModalOpen(true)} className="text-zinc-400 hover:text-white transition-colors font-plus-jakarta text-sm tracking-tight cursor-pointer" >Sign In</button>
                  <button onClick={() => setIsAuthModalOpen(true)} className="bg-primary-container text-on-primary-container px-6 py-2.5 rounded-full font-plus-jakarta text-sm font-bold tracking-tight hover:scale-95 duration-200 transition-all cursor-pointer" >
                    Get Access
                  </button>
                </>
              )}
            </div>
          </div>
        </nav>

        <main className="pt-32 relative z-10 flex-1 flex flex-col min-h-screen">
          <section className="px-8 max-w-screen-2xl mx-auto w-full transition-all duration-500 flex-1">
            <div className="flex flex-col items-center justify-center text-center">


              <span className="label-md uppercase tracking-widest text-primary-container mb-6 font-semibold" >Intelligence as a Material</span>
              <h1 className={`font-extrabold tracking-tighter leading-[0.9] text-white max-w-5xl transition-all duration-500 ${result ? 'text-[3rem] md:text-[4rem] mb-8' : 'text-[5rem] md:text-[7rem] mb-12'}`} >
                HelioX <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-secondary" >RAG System</span>
              </h1>

              <div className="w-full max-w-3xl relative mb-12">
                {uploadedDocs.length > 0 && (
                  <div className="flex flex-wrap gap-2 justify-center mb-4 animate-fade-in-up">
                    {uploadedDocs.map((doc, i) => (
                      <span key={i} className="text-xs bg-white/5 border border-white/10 px-3 py-1.5 rounded-full text-zinc-300 flex items-center gap-2">
                        <span className="material-symbols-outlined text-sm">description</span> {doc.name}
                      </span>
                    ))}
                  </div>
                )}
                <QueryInput onSubmit={handleQuery} isLoading={isLoading} hideTitle={true} onUploadSuccess={handleUploadSuccess} />
              </div>

              {error && (
                <div className="w-full max-w-2xl mx-auto mt-4 mb-8 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-sm animate-fade-in-up">
                  <strong>Error:</strong> {error}
                </div>
              )}

              {isLoading && (
                <div className="flex flex-col items-center mb-12 animate-fade-in-up">
                  <div className="flex gap-1.5 mb-3">
                    {[0, 1, 2].map(i => (
                      <div
                        key={i}
                        className="w-2 h-2 rounded-full bg-helio-primary"
                        style={{ animation: `typing-dot 1.4s ease-in-out ${i * 0.2}s infinite` }}
                      />
                    ))}
                  </div>
                  <p className="text-xs text-helio-text-muted">
                    Running multi-agent pipeline...
                  </p>
                </div>
              )}

              {result && (
                <div className="w-full text-left animate-fade-in-up mb-20 max-w-screen-xl mx-auto pb-20">
                  <div className="flex flex-col lg:flex-row gap-6">
                    <div className="flex-1">
                      <AnswerDisplay
                        answer={result.answer}
                        citations={result.citations}
                        isStreaming={isStreaming}
                        queryText={currentQuery}
                      />
                    </div>
                    <div className="flex-shrink-0 w-full lg:w-48 xl:w-64 mt-6">
                      <ConfidenceMeter
                        confidence={result.calibrated_confidence}
                        breakdown={result.confidence_breakdown}
                      />
                    </div>
                  </div>

                  <div className="mt-12 w-full">
                    <PipelineFlow trace={result.pipeline_trace} />
                  </div>
                </div>
              )}

              {!result && !isLoading && (
                <div className="w-full aspect-[21/9] rounded-full overflow-hidden relative group animate-fade-in-up mb-40">
                  <img alt="Abstract digital craft" className="w-full h-full object-cover grayscale opacity-50 group-hover:grayscale-0 group-hover:opacity-80 transition-all duration-700" data-alt="Abstract 3D rendering of iridescent fluid glass shards floating in a dark obsidian void with cyan neon light pulses" src="https://lh3.googleusercontent.com/aida-public/AB6AXuAV_l1OX6CbY4lU7YflI_lLI8dQidmJIqnICQBjh8l1ELJy57aJPQZUV99W0_eYOd9ZAfwYqKFSjEImi-AHrREz7M2GK_Cont629iEvuY27rJwo9WoOm2ZNTVNQbXdJbAUytza_12x-ggV0kADe23WfHhDz2bsXnpilPlGzSDpRoD7LW_85fr6mXqWGWynKVBA1vsbopgi4SZARYDDv6BZmVi7pRh4LfjPP4H6deJbBjIicK6vOT2y5wZ95UFPgcVo6eelwvtK21FU" />
                  <div className="absolute inset-0 bg-gradient-to-t from-surface via-transparent to-transparent"></div>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="glass-panel p-8 rounded-xl max-w-md text-left border-primary-container/20">
                      <p className="text-on-surface-variant font-medium leading-relaxed italic" >
                        "Where fragments of data find their meaning,and intelligence awakens in motion,shaping answers before questions fade."
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </section>

          {!result && !isLoading && (
            <>
              {/* Sections (The grid, etc.) omitted from main code view for brevity, assuming standard rendering logic down below */}
              <section className="px-8 max-w-screen-2xl mx-auto mb-60 animate-fade-in-up">
                <div className="grid grid-cols-12 gap-12">
                  <div className="col-span-12 md:col-span-5 flex flex-col justify-center">
                    <span className="label-md uppercase tracking-widest text-on-surface-variant mb-4" >Foundation 01</span>
                    <h2 className="text-5xl font-extrabold tracking-tighter text-white mb-8" >The Grid</h2>
                    <p className="text-on-surface-variant text-lg leading-relaxed mb-12 max-w-md" >
                      Our structured layout system adapts to context and content.Optimized for clarity, scalability, and intelligent data flow.
                    </p>
                    <div className="flex gap-4">
                      <button className="text-on-surface border-b-2 border-primary-container pb-1 font-bold hover:text-primary-container transition-colors" >Explore Layouts</button>
                    </div>
                  </div>
                  <div className="col-span-12 md:col-span-7 grid grid-cols-2 gap-6 items-end">
                    <div className="h-[400px] bg-surface-container-low rounded-xl p-8 flex flex-col justify-end relative overflow-hidden group">
                      <img alt="Cyber grid" className="absolute inset-0 w-full h-full object-cover opacity-20 group-hover:opacity-40 transition-all duration-500" data-alt="High-tech digital interface mockup showing a dark minimalist code editor with glowing cyan syntax highlighting" src="https://lh3.googleusercontent.com/aida-public/AB6AXuB3oaKTD7KLq_cahnly-ZaqsTBZV1nlUPZsn5Dl1vX1kjJMBqWpVHpdSRew5CoWtap-wsGExOwovwCSwJzj71NBMj6EYbZvDHt1mWiktRm3DL8n9ABc9_jp7kpnTEwLVHLJg7_N7R-89Cp9bzOCjUqFklbJiH7FmJBYYxSF4vvuUYZ44ymplfoaCQCL5-xYPBrajzoJ86RxRsSLRIoSlqpkoypONkJ7rV1a9JlYzquwVQkwDdsLFN07IuDdjm3D2EqjPt44_WX4PC8" />
                      <div className="relative z-10">
                        <span className="text-primary-container font-black text-4xl" >01</span>
                        <h4 className="text-xl font-bold text-white mt-2" >HelioLite</h4>
                      </div>
                    </div>
                    <div className="h-[550px] bg-surface-container-high rounded-xl p-8 flex flex-col justify-end border-l-4 border-secondary/30 relative overflow-hidden group">
                      <img alt="Deep space data" className="absolute inset-0 w-full h-full object-cover opacity-20 group-hover:opacity-40 transition-all duration-500" data-alt="A detailed digital visualization of neural network connections glowing in deep indigo and electric cyan on a black background" src="https://lh3.googleusercontent.com/aida-public/AB6AXuATzTQWvs96N6GwGuraVvLYdCDRDnWUTkeKpPMFkog6sdqnKc-zhxDUoIuM6ZMj8A617gLWNqA2BvT7295s7o7sCbnB59cyCPJ_ONlARU2FV4ZkHrAw5P4vC2PsbCroxik8S3sCYfIFDveBo5oELyESl2pq6J6YUo6seHIGqSgM_O2rV5VyneXBoMODQikgNXccikTJoxPjxawkt3tl1TNfA7knihP5HjvMmttItld6SuofHLPVXyB_ww76YMCYMfGUm_wFplaIMZI" />
                      <div className="relative z-10">
                        <span className="text-secondary font-black text-4xl" >02</span>
                        <h4 className="text-xl font-bold text-white mt-2" >Adaptive Agent Mesh</h4>
                      </div>
                    </div>
                  </div>
                </div>
              </section>

              <section className="bg-surface-container-lowest py-40 mb-40 relative overflow-hidden">
                <div className="absolute -top-40 -right-40 w-96 h-96 bg-primary-container/10 blur-[120px] rounded-full"></div>
                <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-secondary/10 blur-[120px] rounded-full"></div>
                <div className="px-8 max-w-screen-2xl mx-auto flex flex-col md:flex-row items-center gap-20">
                  <div className="w-full md:w-1/2 relative">
                    <div className="glass-panel p-1 rounded-3xl glow-primary">
                      <div className="bg-surface p-12 rounded-[1.4rem] border border-outline-variant/10">
                        <div className="flex items-center gap-4 mb-10">
                          <div className="w-3 h-3 rounded-full bg-red-500/50"></div>
                          <div className="w-3 h-3 rounded-full bg-yellow-500/50"></div>
                          <div className="w-3 h-3 rounded-full bg-green-500/50"></div>
                        </div>
                        <div className="space-y-6">
                          <div className="h-4 w-3/4 bg-surface-container-highest rounded"></div>
                          <div className="h-4 w-1/2 bg-surface-container-highest rounded opacity-50"></div>
                          <div className="h-40 w-full glass-panel rounded-xl mt-8 flex items-center justify-center">
                            <span className="text-primary-container font-mono text-sm tracking-tighter" >&lt; HELIOX RAG : Where Precision Meets Performance   /&gt;</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="w-full md:w-1/2">
                    <span className="label-md uppercase tracking-widest text-primary-container mb-4 font-semibold" >Optical Precision</span>
                    <h2 className="text-5xl font-extrabold tracking-tighter text-white mb-8" >Clarity by Design</h2>
                    <p className="text-on-surface-variant text-lg leading-relaxed mb-10 max-w-lg" >
                      Built for precision, readability, and seamless visual interaction,ensuring consistent clarity and performance across all interface states and environments.
                    </p>
                    <ul className="space-y-4">
                      <li className="flex items-center gap-3 text-on-surface" >
                        <span className="material-symbols-outlined text-primary-container" >check_circle</span>
                        Context-Aware Backdrop Filtering
                      </li>
                      <li className="flex items-center gap-3 text-on-surface" >
                        <span className="material-symbols-outlined text-primary-container" >check_circle</span>
                        Chromatic Aberration Correction
                      </li>
                      <li className="flex items-center gap-3 text-on-surface" >
                        <span className="material-symbols-outlined text-primary-container" >check_circle</span>
                        Parallel Agent Pipeline
                      </li>
                    </ul>
                  </div>
                </div>
              </section>

              {/* Footer rendered below all content only if in default static state */}
            </>
          )}

          <footer className="mt-auto bg-zinc-950 w-full py-20 px-8 border-t border-zinc-900/50 tonal-shift from-zinc-900 to-zinc-950 flat no shadows relative z-10 w-full">
            <div className="flex flex-col md:flex-row justify-between items-center gap-8 w-full max-w-screen-2xl mx-auto">
              <div className="flex flex-col items-center md:items-start gap-4">
                <div className="text-lg font-black text-white font-plus-jakarta" >HelioX RAG</div>
                <p className="font-plus-jakarta text-xs uppercase tracking-widest text-zinc-500" >© 2026. HelioX -From data to decisions — instantly.</p>
              </div>
              <div className="flex gap-10">
                <a className="font-plus-jakarta text-xs uppercase tracking-widest text-zinc-600 hover:text-cyan-400 transition-colors" href="#" >Twitter</a>
                <a className="font-plus-jakarta text-xs uppercase tracking-widest text-zinc-600 hover:text-cyan-400 transition-colors" href="#" >GitHub</a>
                <a className="font-plus-jakarta text-xs uppercase tracking-widest text-zinc-600 hover:text-cyan-400 transition-colors" href="#" >Discord</a>
                <a className="font-plus-jakarta text-xs uppercase tracking-widest text-zinc-600 hover:text-cyan-400 transition-colors" href="#" >Terms</a>
                <a className="font-plus-jakarta text-xs uppercase tracking-widest text-zinc-600 hover:text-cyan-400 transition-colors" href="#" >Privacy</a>
              </div>
            </div>
          </footer>
        </main>
      </div>
    </div>
  );
}
