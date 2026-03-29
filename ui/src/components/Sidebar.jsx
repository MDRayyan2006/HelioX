import { MessageSquare, Plus, LogOut, Users } from 'lucide-react';
import { signOut } from 'firebase/auth';
import { auth } from '../firebase';

export default function Sidebar({ chats, currentChatId, onSelectChat, onNewChat, user, onSwitchAccount }) {
  if (!user) return null;

  return (
    <div className="w-72 h-screen flex flex-col bg-zinc-950/80 border-r border-white/5 backdrop-blur-xl z-40 hidden md:flex font-plus-jakarta flex-shrink-0 animate-fade-in-right">
      <div className="p-6 pb-2">
        <h2 className="text-xl font-bold bg-gradient-to-r from-helio-primary via-helio-accent to-helio-accent-2 bg-clip-text text-transparent mb-6 cursor-default">
          HelioX
        </h2>
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 bg-helio-primary/10 hover:bg-helio-primary/20 text-helio-primary-light border border-helio-primary/20 hover:border-helio-primary/40 rounded-xl px-4 py-3 font-semibold transition-all duration-300 shadow-[0_0_15px_-5px_rgba(0,240,255,0.2)] cursor-pointer"
        >
          <Plus size={18} />
          <span>New Chat</span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 mt-4 space-y-1">
        {chats.length === 0 ? (
          <div className="text-center text-zinc-600 text-sm mt-10 px-4">
            No chats yet. Start a new conversation!
          </div>
        ) : (
          chats.map(chat => (
            <button
              key={chat.id}
              onClick={() => onSelectChat(chat.id)}
              className={`w-full text-left px-4 py-3 rounded-xl flex items-center gap-3 transition-colors duration-200 truncate cursor-pointer ${
                currentChatId === chat.id 
                  ? 'bg-white/10 text-white font-medium shadow-inner border border-white/5' 
                  : 'text-zinc-400 hover:bg-white/5 hover:text-zinc-200 border border-transparent'
              }`}
            >
              <MessageSquare size={16} className={currentChatId === chat.id ? 'text-helio-primary' : 'text-zinc-500'} />
              <div className="flex-1 truncate text-sm">
                {chat.title || 'New Conversation'}
              </div>
            </button>
          ))
        )}
      </div>

      <div className="p-4 mt-auto border-t border-white/5">
        <div className="flex items-center gap-3 px-2 py-3 bg-white/5 rounded-xl border border-white/5">
          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-helio-primary to-helio-accent flex items-center justify-center text-white font-bold text-sm shadow-[0_0_10px_rgba(0,240,255,0.3)]">
            {user?.email?.charAt(0).toUpperCase() || 'U'}
          </div>
          <div className="flex-1 truncate text-sm text-zinc-300 font-medium" title={user?.email}>
            {user?.email}
          </div>
          <button 
            onClick={onSwitchAccount}
            className="p-2 rounded-lg text-zinc-500 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            title="Switch Account"
          >
            <Users size={16} />
          </button>
          <button 
            onClick={() => signOut(auth)}
            className="p-2 rounded-lg text-zinc-500 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            title="Sign Out"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
