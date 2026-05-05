import { useState, useEffect, useRef } from 'react';

interface Chat {
  chat_id: number;
  label: string;
  participant_count: number;
}

interface AutopilotStatus {
  [chat_id: number]: {
    active: boolean;
    goal: string;
    summary?: string;
    events?: Array<{
      type: string;
      message: string;
    }>;
    transcript?: Array<{
      speaker: string;
      message: string;
    }>;
  };
}

function App() {
  const [chats, setChats] = useState<Chat[]>([]);
  const [selectedChat, setSelectedChat] = useState<Chat | null>(null);
  const [history, setHistory] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [autopilotStatus, setAutopilotStatus] = useState<AutopilotStatus>({});
  const [goal, setGoal] = useState("");
  const [chatLoadError, setChatLoadError] = useState<string | null>(null);
  const [autopilotPendingChatId, setAutopilotPendingChatId] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchChats();
    fetchAutopilotStatus();

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        fetchChats();
        fetchAutopilotStatus();
      }
    };

    const chatInterval = setInterval(fetchChats, 20000);
    const interval = setInterval(fetchAutopilotStatus, 10000);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      clearInterval(chatInterval);
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (selectedChat) {
      fetchHistory(selectedChat.chat_id, selectedChat.label);
    }
  }, [selectedChat]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [history]);

  const fetchChats = async () => {
    try {
      const res = await fetch('/api/chats');
      if (!res.ok) {
        throw new Error(`Chat request failed with ${res.status}`);
      }
      const data = await res.json();
      setChats(data);
      setChatLoadError(null);
      setSelectedChat((current) => {
        if (!data.length) {
          return null;
        }
        if (current) {
          const matchingChat = data.find((chat: Chat) => chat.chat_id === current.chat_id);
          return matchingChat ?? data[0];
        }
        return data[0];
      });
    } catch (err) {
      console.error("Failed to fetch chats", err);
      setChatLoadError("Chat list unavailable. Retrying...");
    }
  };

  const fetchAutopilotStatus = async () => {
    try {
      const res = await fetch('/api/autopilot/status');
      const data = await res.json();
      setAutopilotStatus(data);
    } catch (err) {
      console.error("Failed to fetch autopilot status", err);
    }
  };

  const fetchHistory = async (id: number, label: string) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/chats/${id}/history?chat_filter=${encodeURIComponent(label)}`);
      const data = await res.json();
      setHistory(data.history);
    } catch (err) {
      console.error("Failed to fetch history", err);
    } finally {
      setLoading(false);
    }
  };

  const sendMessage = async () => {
    if (!selectedChat || !message.trim()) return;
    try {
      await fetch(`/api/chats/${selectedChat.chat_id}/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: message,
          recipient_label: selectedChat.label
        })
      });
      setMessage("");
      fetchHistory(selectedChat.chat_id, selectedChat.label);
    } catch (err) {
      console.error("Failed to send message", err);
    }
  };

  const toggleAutopilot = async (active: boolean) => {
    if (!selectedChat) return;
    const chatId = selectedChat.chat_id;
    const nextGoal = goal || autopilotStatus[chatId]?.goal || "";

    try {
      setAutopilotPendingChatId(chatId);
      setAutopilotStatus((current) => ({
        ...current,
        [chatId]: { active, goal: nextGoal }
      }));

      await fetch('/api/autopilot/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: chatId,
          chat_filter: selectedChat.label,
          goal: nextGoal,
          enabled: active
        })
      });
      fetchAutopilotStatus();
    } catch (err) {
      console.error("Failed to toggle autopilot", err);
      fetchAutopilotStatus();
    } finally {
      setAutopilotPendingChatId((current) => (current === chatId ? null : current));
    }
  };

  return (
    <div className="flex h-screen bg-ghost-900 text-gray-200 font-inter antialiased">
      {/* Sidebar */}
      <div className="w-80 bg-black border-r border-zinc-800 flex flex-col shadow-2xl">
        <div className="p-6 border-b border-zinc-800 flex items-center space-x-3">
          <span className="material-symbols-outlined text-gold-accent text-lg">ghost</span>
          <h1 className="text-[10px] font-bold text-gold-accent tracking-[0.3em] flex items-center uppercase font-mono gold-glow">
            MISSION_CONTROL
          </h1>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {chatLoadError && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-[10px] font-mono uppercase tracking-wide text-red-300">
              {chatLoadError}
            </div>
          )}
          {chats.map(chat => (
            <button
              key={chat.chat_id}
              onClick={() => setSelectedChat(chat)}
              className={`w-full text-left p-3 rounded-lg transition-all duration-300 flex items-center justify-between group ${
                selectedChat?.chat_id === chat.chat_id 
                ? 'bg-gold-accent/10 text-gold-accent border-r-2 border-gold-accent' 
                : 'hover:bg-zinc-900/50 text-zinc-500 hover:text-zinc-300'
              }`}
            >
              <div className="flex items-center space-x-3 truncate">
                <span className={`material-symbols-outlined text-sm ${selectedChat?.chat_id === chat.chat_id ? 'text-gold-accent' : 'text-zinc-700'}`}>
                  {chat.participant_count > 1 ? 'group' : 'person'}
                </span>
                <div className={`truncate font-mono text-[11px] uppercase tracking-wider ${selectedChat?.chat_id === chat.chat_id ? 'gold-glow' : ''}`}>
                  {chat.label}
                </div>
              </div>
              {autopilotStatus[chat.chat_id]?.active && (
                <span className="w-2 h-2 bg-status-pulse rounded-full shadow-[0_0_8px_rgba(34,197,94,0.6)] animate-pulse" />
              )}
            </button>
          ))}
        </div>
        
        {/* Sidebar Footer */}
        <div className="p-4 border-t border-zinc-800 bg-zinc-950">
          <div className="flex items-center justify-between px-2">
            <span className="text-[9px] font-mono text-zinc-600 uppercase tracking-tighter">STATUS_STEALTH</span>
            <div className="flex items-center space-x-1">
              <span className="w-1.5 h-1.5 rounded-full bg-status-pulse" />
              <span className="text-[9px] font-mono text-status-pulse uppercase">Linked</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex min-w-0 bg-ghost-900">
        {selectedChat ? (
          <>
            <div className="flex-1 flex flex-col min-w-0">
              {/* Chat Header */}
              <div className="h-16 px-6 border-b border-zinc-800 flex items-center justify-between bg-black/60 backdrop-blur-xl z-10 shadow-lg">
                <div className="flex items-center space-x-4">
                  <div className="w-9 h-9 rounded-lg bg-zinc-900 border border-zinc-800 flex items-center justify-center text-[10px] font-mono font-bold text-gold-accent chrome-reflect">
                    {selectedChat.label[0].toUpperCase()}
                  </div>
                  <div>
                    <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-zinc-300">{selectedChat.label}</h2>
                    <div className="text-[8px] font-mono text-zinc-600 uppercase tracking-widest mt-0.5">Encrypted_Ghost_Link</div>
                  </div>
                </div>
              
                <div className="flex items-center space-x-4">
                  <div className="flex items-center space-x-2 bg-zinc-900/50 border border-zinc-800 p-1 rounded-lg">
                    <input 
                      type="text" 
                      placeholder="SET_MISSION_GOAL..."
                      className="bg-transparent border-none focus:ring-0 text-[10px] font-mono text-gold-accent w-64 px-2 placeholder:text-zinc-700"
                      value={goal || autopilotStatus[selectedChat.chat_id]?.goal || ""}
                      onChange={(e) => setGoal(e.target.value)}
                    />
                    <button 
                      onClick={() => toggleAutopilot(!autopilotStatus[selectedChat.chat_id]?.active)}
                      disabled={autopilotPendingChatId === selectedChat.chat_id}
                      className={`px-4 py-1.5 rounded text-[10px] font-mono font-bold tracking-tighter transition-all ${
                        autopilotStatus[selectedChat.chat_id]?.active 
                        ? 'bg-red-500/20 text-red-500 border border-red-500/50' 
                        : 'bg-gold-accent text-black hover:brightness-110 active:scale-95'
                      } ${autopilotPendingChatId === selectedChat.chat_id ? 'opacity-60 cursor-wait' : ''}`}
                    >
                      {autopilotPendingChatId === selectedChat.chat_id
                        ? 'SYNCING...'
                        : autopilotStatus[selectedChat.chat_id]?.active
                          ? 'ABORT_AUTO'
                          : 'ENGAGE_AUTO'}
                    </button>
                  </div>
                </div>
              </div>

              {/* Messages */}
              <div 
                ref={scrollRef}
                className="flex-1 overflow-y-auto p-8 space-y-6 scroll-smooth bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')]"
              >
                {loading ? (
                  <div className="flex items-center justify-center h-full text-zinc-800 font-mono text-[10px] animate-pulse uppercase tracking-[0.5em]">
                    Synchronizing...
                  </div>
                ) : (
                  history.split('\n').map((line, i) => {
                    const isMe = line.includes("]: Me: ");
                    return (
                      <div key={i} className={`flex ${isMe ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[70%] p-4 rounded-xl text-sm ${
                          isMe 
                          ? 'bg-gold-accent text-black font-medium rounded-tr-none shadow-xl shadow-gold-accent/10 border border-gold-accent/20' 
                          : 'chrome-reflect text-zinc-300 rounded-tl-none border border-zinc-800/50'
                        }`}>
                          <div className={`text-[9px] font-mono mb-2 uppercase tracking-tighter opacity-50 ${isMe ? 'text-black' : 'text-gold-accent'}`}>
                            {line.split('] ')[0].replace('[', '')}
                          </div>
                          <p className="leading-relaxed font-body-base text-[13px]">
                            {line.split(': ').slice(2).join(': ') || line.split(': ').slice(1).join(': ')}
                          </p>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* Input Area */}
              <div className="p-6 bg-black/20 border-t border-zinc-800 backdrop-blur-sm">
                <div className="max-w-4xl mx-auto flex items-center space-x-4 bg-zinc-900/80 p-2 rounded-xl border border-zinc-800 focus-within:border-gold-accent/50 transition-all shadow-inner">
                  <input
                    type="text"
                    placeholder={`EXECUTE_COMMAND_TO_${selectedChat.label.toUpperCase().replace(/ /g, '_')}...`}
                    className="flex-1 bg-transparent border-none focus:ring-0 px-4 py-2 font-mono text-[11px] text-zinc-300 placeholder:text-zinc-700"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
                  />
                  <button 
                    onClick={sendMessage}
                    className="w-10 h-10 bg-gold-accent text-black rounded-lg flex items-center justify-center hover:scale-105 transition-transform active:scale-95 shadow-lg shadow-gold-accent/10"
                  >
                    <span className="material-symbols-outlined font-bold text-lg">send</span>
                  </button>
                </div>
              </div>
            </div>

            <aside className="w-80 border-l border-zinc-800 bg-black/40 backdrop-blur-sm p-5 overflow-y-auto">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-[10px] font-mono uppercase tracking-[0.3em] text-gold-accent">Auto Summary</h3>
                <span className={`text-[9px] font-mono uppercase ${autopilotStatus[selectedChat.chat_id]?.active ? 'text-status-pulse' : 'text-zinc-600'}`}>
                  {autopilotStatus[selectedChat.chat_id]?.active ? 'Tracking' : 'Idle'}
                </span>
              </div>
              <p className="text-[10px] font-mono uppercase tracking-wide text-zinc-600 mb-4">
                What this conversation has been about since Auto was engaged
              </p>
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-4 mb-4">
                <p className="text-[12px] leading-relaxed text-zinc-200 break-words">
                  {autopilotStatus[selectedChat.chat_id]?.summary || 'No conversation has happened yet since Auto was engaged.'}
                </p>
              </div>
              <div className="mb-3 text-[9px] font-mono uppercase tracking-[0.25em] text-zinc-500">
                Recent Auto Conversation
              </div>
              <div className="space-y-3">
                {(autopilotStatus[selectedChat.chat_id]?.transcript?.length
                  ? [...(autopilotStatus[selectedChat.chat_id]?.transcript || [])].reverse()
                  : [{ speaker: 'status', message: 'No messages exchanged yet.' }]
                ).map((entry, index) => (
                  <div key={`${entry.speaker}-${index}`} className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-3">
                    <div className="text-[9px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-2">
                      {entry.speaker}
                    </div>
                    <p className="text-[11px] leading-relaxed text-zinc-300 break-words">
                      {entry.message}
                    </p>
                  </div>
                ))}
              </div>
            </aside>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-zinc-900 space-y-6">
            <div className="text-9xl opacity-5 font-mono tracking-tighter select-none">GHOST_OS</div>
            <div className="flex flex-col items-center space-y-2">
              <p className="text-[10px] font-mono uppercase tracking-[0.4em] opacity-30">System_Idle</p>
              <p className="text-[9px] font-mono uppercase tracking-[0.2em] opacity-20 italic">Awaiting Mission Selection</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
