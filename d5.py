import socket
import threading
import time
import queue
import struct
import sys
import uuid

def get_local_ip():
    """
    Gets the local IP address of the machine.
    """
    try:
        # Use an external connection to determine local IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Doesn't have to be reachable
            s.connect(('8.8.8.8', 80))
            local_ip = s.getsockname()[0]
            print(f"Local IP detected as: {local_ip}")
            return local_ip
    except Exception:
        local_ip = '127.0.0.1'
        print("Could not determine local IP. Defaulting to 127.0.0.1")
        return local_ip

def display_message(message):
    print(message)

def update_peers_display(known_peers):
    print("\nConnected Peers:")
    for uuid_key, info in known_peers.items():
        print(f"{info['ip']}:{info['chat_port']} (UUID: {uuid_key})")
    print("\nType your message and press Enter:")

def send_message(message_queue, known_peers, peer_uuid, lock):
    while True:
        message = input()
        if message.strip() != '':
            if message.lower() == 'exit':
                print("Exiting chat...")
                sys.exit()
            # Send the chat message to each peer
            with lock:
                peers = list(known_peers.values())
            for info in peers:
                threading.Thread(
                    target=send_chat_message,
                    args=(info['ip'], info['chat_port'], message, peer_uuid),
                    daemon=True
                ).start()
            display_message(f"You: {message}")

def send_chat_message(peer_ip, peer_chat_port, message, peer_uuid):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        msg = f"CHAT_MESSAGE|{peer_uuid}|{message}"
        sock.sendto(msg.encode(), (peer_ip, peer_chat_port))
        sock.close()
        print(f"Sent chat message to {peer_ip}:{peer_chat_port}")
    except Exception as e:
        print(f"Error sending message to {peer_ip}:{peer_chat_port} - {e}")

def listen_for_peers(known_peers, peer_uuid, chat_port, lock):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
        # Allow multiple sockets to use the same address and port
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind to the multicast address and port
        s.bind(('', 5007))

        # Join the multicast group on all interfaces
        mreq = struct.pack('4sL', socket.inet_aton('224.1.1.1'), socket.INADDR_ANY)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        print(f"Listening for multicast messages on 224.1.1.1:5007")

        while True:
            data, addr = s.recvfrom(4096)
            message = data.decode()
            parts = message.split('|', 3)
            if len(parts) >= 3:
                message_type, sender_chat_port, sender_uuid = parts[0], parts[1], parts[2]
                peer_ip = addr[0]
                sender_chat_port = int(sender_chat_port)
                # Ignore messages from self
                if sender_uuid == peer_uuid:
                    continue
                print(f"Received {message_type} from {peer_ip}:{sender_chat_port} (UUID: {sender_uuid})")
                if message_type == 'NODE_DISCOVERY':
                    with lock:
                        if sender_uuid not in known_peers:
                            known_peers[sender_uuid] = {'ip': peer_ip, 'chat_port': sender_chat_port}
                            update_peers_display(known_peers)
                else:
                    print(f"Unknown message type received: {message_type}")
            else:
                print(f"Received malformed message from {addr}: {message}")

def listen_for_chat_messages(message_queue, chat_port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', chat_port))
    print(f"Listening for chat messages on port {chat_port}")
    while True:
        data, addr = sock.recvfrom(4096)
        message = data.decode()
        parts = message.split('|', 2)
        if len(parts) == 3:
            message_type, sender_uuid, chat_message = parts
            if message_type == 'CHAT_MESSAGE':
                message_queue.put(f"\n[{addr[0]}]: {chat_message}")
        else:
            print(f"Received malformed chat message from {addr}: {message}")

def broadcast_presence(peer_uuid, chat_port):
    """
    Broadcasts presence using multicast.
    """
    message = f"NODE_DISCOVERY|{chat_port}|{peer_uuid}|"
    message_bytes = message.encode()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
        # Set Time-to-Live (TTL) to 1 for local network
        ttl = struct.pack('b', 1)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
        try:
            while True:
                s.sendto(message_bytes, ('224.1.1.1', 5007))
                # print(f"Broadcasted presence")
                time.sleep(2)  # Broadcast every 2 seconds (more aggressive)
        except Exception as e:
            print(f"\nError broadcasting presence: {e}")

def start_server():
    # Bind to an available port
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.bind(('', 0))
    chat_port = server_sock.getsockname()[1]  # Get the port number assigned
    server_sock.close()
    print(f"Chat server listening on port {chat_port}")
    return chat_port

def process_incoming_messages(message_queue):
    while True:
        while not message_queue.empty():
            message = message_queue.get()
            display_message(message)
        time.sleep(0.1)

def main():
    print("Welcome to the decentralized group chat!")
    print("Type messages and press Enter to send to all peers.")
    print("Type 'exit' to quit.\n")

    # Generate a unique UUID for this instance
    peer_uuid = str(uuid.uuid4())
    print(f"Assigned UUID: {peer_uuid}")

    chat_port = start_server()

    message_queue = queue.Queue()
    known_peers = {}
    lock = threading.Lock()

    # Start networking threads
    threading.Thread(
        target=listen_for_peers,
        args=(known_peers, peer_uuid, chat_port, lock),
        daemon=True
    ).start()
    threading.Thread(
        target=broadcast_presence,
        args=(peer_uuid, chat_port),
        daemon=True
    ).start()
    threading.Thread(
        target=listen_for_chat_messages,
        args=(message_queue, chat_port),
        daemon=True
    ).start()
    threading.Thread(
        target=process_incoming_messages,
        args=(message_queue,),
        daemon=True
    ).start()

    # Start the message input loop
    send_message(message_queue, known_peers, peer_uuid, lock)

if __name__ == "__main__":
    main()
