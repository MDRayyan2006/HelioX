import React from 'react';
import { Link } from '@tanstack/react-router';


// Converted from Stitch MCP HTML Generation
export const ReactBitsScreen = () => {
  return (
    <div className="bg-surface text-on-surface font-plus-jakarta min-h-screen">
      {/* Original Body Content */}

      {/* Top Navigation */}
      <nav className="fixed top-0 w-full z-50 bg-zinc-950/60 backdrop-blur-xl no-line bg-zinc-900/10 shadow-[0_0_40px_-15px_rgba(0,240,255,0.1)]">
        <div className="flex justify-between items-center px-8 py-4 max-w-screen-2xl mx-auto">
          <Link to="/" className="text-xl font-bold tracking-tighter text-white uppercase font-plus-jakarta cursor-pointer hover:text-cyan-400 transition-colors">HelioX Dashboard ←</Link>
          <div className="hidden md:flex items-center gap-10">
            <a className="text-cyan-400 font-semibold border-b border-cyan-400 pb-1 font-plus-jakarta text-sm tracking-tight hover:bg-white/5 transition-all duration-300" href="#" >Components</a>
            <a className="text-zinc-400 hover:text-white transition-colors font-plus-jakarta text-sm tracking-tight hover:bg-white/5 transition-all duration-300" href="#" >Pro</a>
            <a className="text-zinc-400 hover:text-white transition-colors font-plus-jakarta text-sm tracking-tight hover:bg-white/5 transition-all duration-300" href="#" >Showcase</a>
            <a className="text-zinc-400 hover:text-white transition-colors font-plus-jakarta text-sm tracking-tight hover:bg-white/5 transition-all duration-300" href="#" >Docs</a>
          </div>
          <div className="flex items-center gap-6">
            <button className="text-zinc-400 hover:text-white transition-colors font-plus-jakarta text-sm tracking-tight" >Sign In</button>
            <button className="bg-primary-container text-on-primary-container px-6 py-2.5 rounded-full font-plus-jakarta text-sm font-bold tracking-tight hover:scale-95 duration-200 transition-all" >
              Get Access
            </button>
          </div>
        </div>
      </nav>
      <main className="pt-32">
        {/* Hero Section */}
        <section className="px-8 max-w-screen-2xl mx-auto mb-40">
          <div className="flex flex-col items-center text-center">
            <span className="label-md uppercase tracking-widest text-primary-container mb-6 font-semibold" >Intelligence as a Material</span>
            <h1 className="text-[5rem] md:text-[7rem] font-extrabold tracking-tighter leading-[0.9] text-white max-w-5xl mb-12" >
              The Next-Gen <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-secondary" >UI Library</span>
            </h1>
            {/* Perplexity-style Command Bar */}
            <div className="w-full max-w-2xl relative mb-20">
              <div className="glass-panel rounded-full p-2 flex items-center pr-4 border-outline-variant/20 glow-primary">
                <div className="pl-6 pr-4 flex items-center text-primary-container">
                  <span className="material-symbols-outlined" data-icon="auto_awesome" >auto_awesome</span>
                </div>
                <input className="w-full bg-transparent border-none focus:ring-0 text-on-surface placeholder:text-on-surface-variant/40 py-4 font-plus-jakarta" placeholder="Ask for a component... 'a glass dashboard for finance'" type="text" />
                <kbd className="hidden md:block px-2 py-1 bg-surface-container-highest rounded text-[10px] font-bold text-on-surface-variant mr-3">⌘ K</kbd>
                <button className="bg-primary-container text-on-primary-container p-3 rounded-full hover:scale-105 transition-transform" >
                  <span className="material-symbols-outlined" data-icon="arrow_forward" >arrow_forward</span>
                </button>
              </div>
            </div>
            {/* Hero Visual */}
            <div className="w-full aspect-[21/9] rounded-full overflow-hidden relative group">
              <img alt="Abstract digital craft" className="w-full h-full object-cover grayscale opacity-50 group-hover:grayscale-0 group-hover:opacity-80 transition-all duration-700" data-alt="Abstract 3D rendering of iridescent fluid glass shards floating in a dark obsidian void with cyan neon light pulses" src="https://lh3.googleusercontent.com/aida-public/AB6AXuAV_l1OX6CbY4lU7YflI_lLI8dQidmJIqnICQBjh8l1ELJy57aJPQZUV99W0_eYOd9ZAfwYqKFSjEImi-AHrREz7M2GK_Cont629iEvuY27rJwo9WoOm2ZNTVNQbXdJbAUytza_12x-ggV0kADe23WfHhDz2bsXnpilPlGzSDpRoD7LW_85fr6mXqWGWynKVBA1vsbopgi4SZARYDDv6BZmVi7pRh4LfjPP4H6deJbBjIicK6vOT2y5wZ95UFPgcVo6eelwvtK21FU" />
              <div className="absolute inset-0 bg-gradient-to-t from-surface via-transparent to-transparent"></div>
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="glass-panel p-8 rounded-xl max-w-md text-left border-primary-container/20">
                  <p className="text-on-surface-variant font-medium leading-relaxed italic" >
                    "We don't just build components; we curate the digital matter that forms the backbone of the world's most intelligent interfaces."
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
        {/* The Grid (Asymmetrical Editorial) */}
        <section className="px-8 max-w-screen-2xl mx-auto mb-60">
          <div className="grid grid-cols-12 gap-12">
            <div className="col-span-12 md:col-span-5 flex flex-col justify-center">
              <span className="label-md uppercase tracking-widest text-on-surface-variant mb-4" >Foundation 01</span>
              <h2 className="text-5xl font-extrabold tracking-tighter text-white mb-8" >The Grid</h2>
              <p className="text-on-surface-variant text-lg leading-relaxed mb-12 max-w-md" >
                Our layout engine treats whitespace as a structural component. No more claustrophobic grids—only expansive, intentional compositions that breathe.
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
                  <h4 className="text-xl font-bold text-white mt-2" > Adaptive Agent Mesh</h4>
                </div>
              </div>
            </div>
          </div>
        </section>
        {/* Crystal Clear (Glassmorphism & Precision) */}
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
                      <span className="text-primary-container font-mono text-sm tracking-tighter" >&lt;GlassCard blur={20} transparency={0.6} /&gt;</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div className="w-full md:w-1/2">
              <span className="label-md uppercase tracking-widest text-primary-container mb-4 font-semibold" >Optical Precision</span>
              <h2 className="text-5xl font-extrabold tracking-tighter text-white mb-8" >Crystal Clear</h2>
              <p className="text-on-surface-variant text-lg leading-relaxed mb-10 max-w-lg" >
                We use sub-pixel rendering and mathematically perfect blurs to create interfaces that feel like physical objects carved from light. Every component is tested for legibility across 100+ different background textures.
              </p>
              <ul className="space-y-4">
                <li className="flex items-center gap-3 text-on-surface" >
                  <span className="material-symbols-outlined text-primary-container" data-icon="check_circle" >check_circle</span>
                  Adaptive Backdrop Filtering
                </li>
                <li className="flex items-center gap-3 text-on-surface" >
                  <span className="material-symbols-outlined text-primary-container" data-icon="check_circle" >check_circle</span>
                  Chromatic Abberation Control
                </li>
                <li className="flex items-center gap-3 text-on-surface" >
                  <span className="material-symbols-outlined text-primary-container" data-icon="check_circle" >check_circle</span>
                  High-Contrast Overlay Logic
                </li>
              </ul>
            </div>
          </div>
        </section>
        {/* Modular by Design (Bento Grid) */}
        <section className="px-8 max-w-screen-2xl mx-auto mb-60">
          <div className="text-center mb-24">
            <span className="label-md uppercase tracking-widest text-on-surface-variant mb-4" >Architecture</span>
            <h2 className="text-6xl font-extrabold tracking-tighter text-white" >Modular by Design</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 grid-rows-2 gap-6 h-auto md:h-[800px]">
            <div className="md:col-span-2 md:row-span-2 bg-surface-container-low rounded-3xl p-12 flex flex-col justify-between border border-outline-variant/5 group hover:bg-surface-container transition-colors duration-500">
              <div>
                <span className="material-symbols-outlined text-5xl text-primary-container mb-8" data-icon="category" >category</span>
                <h3 className="text-3xl font-bold text-white mb-4" >Atomic Components</h3>
                <p className="text-on-surface-variant text-lg max-w-sm" >Every button, input, and toggle is a standalone masterpiece, engineered with TypeScript first principles.</p>
              </div>
              <div className="relative h-48 overflow-hidden rounded-xl bg-surface/50 p-4 border border-outline-variant/10">
                <div className="grid grid-cols-4 gap-2">
                  <div className="h-8 bg-primary/20 rounded-full animate-pulse"></div>
                  <div className="h-8 bg-secondary/20 rounded-full"></div>
                  <div className="h-8 bg-primary-container/20 rounded-full"></div>
                  <div className="h-8 bg-surface-container-highest rounded-full"></div>
                </div>
              </div>
            </div>
            <div className="md:col-span-2 bg-surface-container-high rounded-3xl p-12 border border-outline-variant/5 group hover:border-primary-container/30 transition-all">
              <span className="material-symbols-outlined text-4xl text-secondary mb-6" data-icon="dynamic_form" >dynamic_form</span>
              <h3 className="text-2xl font-bold text-white mb-2" >Infinite Composition</h3>
              <p className="text-on-surface-variant" >Stack, nest, and extend without losing visual consistency. Our theme engine handles the complexity.</p>
            </div>
            <div className="bg-surface-container-low rounded-3xl p-10 border border-outline-variant/5 flex flex-col items-center justify-center text-center">
              <span className="material-symbols-outlined text-5xl text-on-surface-variant mb-4" data-icon="speed" >speed</span>
              <h4 className="text-xl font-bold text-white" >0.2ms</h4>
              <p className="text-xs text-on-surface-variant uppercase tracking-widest mt-1" >Render Speed</p>
            </div>
            <div className="bg-primary-container rounded-3xl p-10 flex flex-col items-center justify-center text-center text-on-primary-container">
              <span className="material-symbols-outlined text-5xl mb-4" data-icon="workspace_premium" style={{ fontVariationSettings: "'FILL' 1" }}>workspace_premium</span>
              <h4 className="text-xl font-black italic" >ELITE</h4>
              <p className="text-xs uppercase tracking-widest mt-1 font-bold opacity-70" >Design Grade</p>
            </div>
          </div>
        </section>
        {/* CTA Section */}
        <section className="px-8 max-w-screen-2xl mx-auto mb-40">
          <div className="bg-gradient-to-br from-primary-container/20 to-secondary/20 rounded-[3rem] p-20 text-center relative overflow-hidden">
            <div className="absolute inset-0 bg-surface/40 backdrop-blur-3xl"></div>
            <div className="relative z-10 max-w-3xl mx-auto">
              <h2 className="text-6xl font-extrabold tracking-tighter text-white mb-8" >Ready to elevate your craft?</h2>
              <p className="text-xl text-on-surface-variant mb-12" >Join 10,000+ developers building the future of the web with React Bits.</p>
              <div className="flex flex-col md:flex-row gap-6 justify-center">
                <button className="bg-primary-container text-on-primary-container px-12 py-5 rounded-full text-lg font-bold hover:scale-105 transition-transform shadow-[0_20px_40px_-15px_rgba(0,240,255,0.4)]" >
                  Start Building Now
                </button>
                <button className="border border-outline-variant/30 text-white px-12 py-5 rounded-full text-lg font-bold hover:bg-white/5 transition-colors" >
                  View Components
                </button>
              </div>
            </div>
          </div>
        </section>
      </main>
      {/* Footer */}
      <footer className="bg-zinc-950 w-full py-20 px-8 border-t border-zinc-900/50 tonal-shift from-zinc-900 to-zinc-950 flat no shadows">
        <div className="flex flex-col md:flex-row justify-between items-center gap-8 w-full max-w-screen-2xl mx-auto">
          <div className="flex flex-col items-center md:items-start gap-4">
            <div className="text-lg font-black text-white font-plus-jakarta" >React Bits</div>
            <p className="font-plus-jakarta text-xs uppercase tracking-widest text-zinc-500" >© 2024 React Bits. The Digital Atelier.</p>
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

    </div>
  );
};

export default ReactBitsScreen;
