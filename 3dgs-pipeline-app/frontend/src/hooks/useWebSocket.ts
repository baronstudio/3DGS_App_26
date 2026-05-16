import { useState, useEffect } from 'react';

const useWebSocket = (url: string) => {
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [lastMessage, setLastMessage] = useState<any>(null);

  useEffect(() => {
    const newSocket = new WebSocket(url);
    newSocket.onmessage = (event) => {
      setLastMessage(JSON.parse(event.data));
    };
    setSocket(newSocket);
    return () => newSocket.close();
  }, [url]);

  return { socket, lastMessage };
};

export default useWebSocket;
