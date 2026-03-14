curl --location 'http://localhost:4500/support' \
--header 'x-request-id: 6a5sda132asd54' \
--header 'x-channel-id: minutes' \
--header 'Content-Type: application/json' \
--data '{
    "conversation_id": "c1",
    "user_id": "USR-00397",
    "order_id" : "N-20260314-ITIKF",
    "session_id": "s1",
    "message": "why is my order?",
    "messages": [
        {
            "role": "user",
            "content": "Where is my order?"
        },
        {
            "role" : "system",
            "content" : "Your order N-20260314-ITIKF is currently: out_for_delivery. Total: $0.00"
        },
        {
            "role": "user",
            "content": "I had paid for my order - why would you say I paid zero?"
        }
    ]
}'