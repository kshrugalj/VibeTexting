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
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchChats();
    const interval = setInterval(fetchAutopilotStatus, 5000);
    return () => clearInterval(interval);
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
      const data = await res.json();
      setChats(data);
    } catch (err) {
      console.error("Failed to fetch chats", err);
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
    try {
      await fetch('/api/autopilot/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_filter: selectedChat.label,
          goal: goal,
          enabled: active
        })
      });
      fetchAutopilotStatus();
    } catch (err) {
      console.error("Failed to toggle autopilot", err);
    }
  };

  return (
    <div className="flex h-screen bg-ghost-900 text-gray-200 font-sans">
      {/* Sidebar */}
      <div className="w-80 bg-ghost-800 border-r border-ghost-700 flex flex-col">
        <div className="p-6 border-b border-ghost-700">
          <h1 className="text-xl font-bold text-ghost-vibe tracking-tight flex items-center">
            <span className="mr-2">👻</span> Ghost Dashboard
          </h1>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {chats.map(chat => (
            <button
              key={chat.chat_id}
              onClick={() => setSelectedChat(chat)}
              className={`w-full text-left p-3 rounded-lg transition-all duration-200 flex items-center justify-between ${
                selectedChat?.chat_id === chat.chat_id 
                ? 'bg-ghost-vibe bg-opacity-20 text-ghost-vibe border border-ghost-vibe border-opacity-30' 
                : 'hover:bg-ghost-700 text-gray-400'
              }`}
            >
              <div className="truncate font-medium">{chat.label}</div>
              {autopilotStatus[chat.chat_id]?.active && (
                <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse ml-2 flex-shrink-0" />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {selectedChat ? (
          <>
            {/* Chat Header */}
            <div className="h-16 px-6 border-b border-ghost-700 flex items-center justify-between bg-ghost-800 bg-opacity-50">
              <div className="flex items-center space-x-3">
                <div className="w-8 h-8 rounded-full bg-ghost-600 flex items-center justify-center text-sm font-bold">
                  {selectedChat.label[0].toUpperCase()}
                </div>
                <h2 className="font-semibold text-lg">{selectedChat.label}</h2>
              </div>
              
              <div className="flex items-center space-x-4">
                <div className="flex items-center space-x-2 bg-ghost-700 p-1 rounded-lg">
                  <input 
                    type="text" 
                    placeholder="Auto-Pilot Goal..."
                    className="bg-transparent border-none focus:ring-0 text-sm w-48 px-2"
                    value={goal || autopilotStatus[selectedChat.chat_id]?.goal || ""}
                    onChange={(e) => setGoal(e.target.value)}
                  />
                  <button 
                    onClick={() => toggleAutopilot(!autopilotStatus[selectedChat.chat_id]?.active)}
                    className={`px-3 py-1 rounded text-xs font-bold transition-all ${
                      autopilotStatus[selectedChat.chat_id]?.active 
                      ? 'bg-red-500 hover:bg-red-600 text-white' 
                      : 'bg-ghost-vibe hover:opacity-90 text-white'
                    }`}
                  >
                    {autopilotStatus[selectedChat.chat_id]?.active ? 'STOP AUTO' : 'START AUTO'}
                  </button>
                </div>
              </div>
            </div>

            {/* Messages */}
            <div 
              ref={scrollRef}
              className="flex-1 overflow-y-auto p-6 space-y-4 scroll-smooth"
            >
              {loading ? (
                <div className="flex items-center justify-center h-full text-ghost-500 italic">
                  Loading semantic memory...
                </div>
              ) : (
                history.split('\n').map((line, i) => {
                  const isMe = line.includes("]: Me: ");
                  return (
                    <div key={i} className={`flex ${isMe ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[80%] p-3 rounded-2xl text-sm shadow-sm ${
                        isMe 
                        ? 'bg-ghost-vibe text-white rounded-tr-none' 
                        : 'bg-ghost-700 text-gray-200 rounded-tl-none border border-ghost-600'
                      }`}>
                        <div className="text-[10px] opacity-50 mb-1">
                          {line.split('] ')[0].replace('[', '')}
                        </div>
                        {line.split(': ').slice(2).join(': ') || line.split(': ').slice(1).join(': ')}
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Input Area */}
            <div className="p-4 bg-ghost-800 border-t border-ghost-700">
              <div className="max-w-4xl mx-auto flex items-center space-x-3 bg-ghost-700 p-2 rounded-2xl border border-ghost-600 focus-within:border-ghost-vibe transition-colors">
                <input
                  type="text"
                  placeholder={`Reply to ${selectedChat.label}...`}
                  className="flex-1 bg-transparent border-none focus:ring-0 px-4 py-2"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
                />
                <button 
                  onClick={sendMessage}
                  className="w-10 h-10 bg-ghost-vibe text-white rounded-xl flex items-center justify-center hover:opacity-90 transition-opacity"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 transform rotate-90" viewBox="0 0 20 20" fill="currentColor">
                    <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
                  </svg>
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-ghost-500 space-y-4">
            <div className="text-6xl grayscale opacity-20">👻</div>
            <p className="text-lg font-medium">Select a conversation to haunt.</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
