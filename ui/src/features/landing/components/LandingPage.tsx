import React from 'react';
import { Link } from '@tanstack/react-router';
import LiquidEther from '@/components/LiquidEther';

export const LandingPage: React.FC = () => {
  return (
    <div className="relative w-full h-screen bg-black overflow-hidden flex flex-col items-center justify-center font-plus-jakarta animate-pulse-glow" style={{ animationDuration: '8s' }}>
      {/* LiquidEther Background */}
      <div className="absolute inset-0 z-0">
        <LiquidEther
          mouseForce={28}
          cursorSize={150}
          isViscous
          viscous={30}
          colors={["#129cf3", "#0bb9e5", "#17f9fd"]}
          autoDemo
          autoSpeed={0.5}
          autoIntensity={2.2}
          isBounce={false}
          resolution={0.5}
        />
      </div>

      {/* Landing Content */}
      <div className="relative z-10 flex flex-col items-center justify-center text-center px-4 animate-fade-in-up pointer-events-none">
        <h1 className="text-[6rem] md:text-[9rem] font-black tracking-tighter text-white mb-6 drop-shadow-2xl">
          HelioX
        </h1>
        <p className="text-xl md:text-2xl text-cyan-100/90 font-medium max-w-2xl leading-relaxed mb-12 drop-shadow-md">
          Intelligence as a Material.<br />The adaptive multi-agent retrieval layer.
        </p>
        <div className="flex gap-6 pointer-events-auto">
          <Link
            to="/dashboard"
            className="bg-primary/20 backdrop-blur-md border border-primary/40 text-white px-8 py-4 rounded-full font-bold tracking-wide hover:bg-primary/40 hover:scale-105 transition-all cursor-pointer shadow-[0_0_30px_-5px_var(--color-primary-container)]"
          >
            Launch Dashboard
          </Link>
          <Link
            to="/react-bits"
            className="bg-white/5 backdrop-blur-md border border-white/10 text-white px-8 py-4 rounded-full font-bold tracking-wide hover:bg-white/10 transition-all cursor-pointer"
          >
            React Bits UI
          </Link>
        </div>
      </div>
    </div>
  );
};

export default LandingPage;
