# ScoreKeeper Sam Chat - Testing & Troubleshooting Guide

## 🚀 Quick Test Steps

### 1. Start the Dev Stack
```bash
# Make sure you're in the project root
cd "/mnt/c/Users/Dad's PC/Desktop/Arcade Assistant Local"

# Start everything
npm run dev
```

### 2. Verify API Keys
```bash
# Check if Anthropic key is set
echo $ANTHROPIC_API_KEY

# OR check OpenAI key
echo $OPENAI_API_KEY

# If empty, add to .env file:
# ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 3. Open ScoreKeeper Panel
```
http://localhost:8787/scorekeeper
```

### 4. Open Browser Console (IMPORTANT!)
- Press **F12** to open Developer Tools
- Go to the **Console** tab
- Keep this open during testing

### 5. Test Chat
1. Click the "💬 Chat with Sam" button (top right)
2. Chat sidebar should slide in from the right
3. Type: "Hello"
4. Press Enter or click "EXECUTE"

---

## 🔍 What to Look For

### Success Indicators
✅ Chat sidebar opens when you click button
✅ You can type in the input field
✅ "EXECUTE" button is enabled (not grayed out)
✅ After sending, you see "Processing..." briefly
✅ AI response appears in chat
✅ Console shows logs:
```
[ScoreKeeper] Sending chat message: Hello
[ScoreKeeper] Context: {panel: 'scorekeeper', ...}
[ScoreKeeper] AI response: {message: {content: '...'}}
[ScoreKeeper] Extracted text: Hello! I'm ScoreKeeper Sam...
```

### Failure Indicators
❌ Chat button does nothing
❌ Can't type in input field
❌ "EXECUTE" button stays grayed out
❌ Error message appears in chat
❌ Console shows red errors
❌ Status shows "AI Error: ..."

---

## 🐛 Common Issues & Fixes

### Issue 1: Chat Button Doesn't Open Sidebar

**Symptom:** Clicking "💬 Chat with Sam" does nothing

**Check:**
- Is the button actually clickable? (not behind another element)
- Check console for JavaScript errors

**Fix:**
```bash
# Restart frontend
# Press Ctrl+C in terminal, then:
npm run dev:frontend
```

### Issue 2: Can't Type in Input Field

**Symptom:** Input field is grayed out or won't accept text

**Check:**
- Is `isProcessing` stuck as `true`?
- Check browser console for errors

**Fix:**
- Reload page (Ctrl+R)
- Check if `inputMessage` state is working

### Issue 3: "EXECUTE" Button Grayed Out

**Symptom:** Button says "EXECUTE" but is disabled

**Reason:** This is normal when:
- Input field is empty
- Message is being processed

**Test:** Type something, button should become enabled

### Issue 4: "AI Error: NOT_CONFIGURED"

**Symptom:** Chat shows error about API key

**Fix:**
```bash
# Check .env file exists
ls -la .env

# Add API key if missing
echo 'ANTHROPIC_API_KEY=sk-ant-your-key-here' >> .env

# Restart gateway
npm run dev:gateway
```

### Issue 5: "AI Error: CORS" or Network Error

**Symptom:** Console shows CORS or fetch errors

**Check:**
1. Is gateway running? Test:
```bash
curl http://localhost:8787/api/health
# Should return: {"status":"ok"}
```

2. Is backend running? Test:
```bash
curl http://localhost:8888/health
# Should return JSON
```

**Fix:**
```bash
# Restart full stack
npm run dev
```

### Issue 6: Response Takes Too Long (>10 seconds)

**Symptom:** "Processing..." never completes

**Check Console For:**
- `[ScoreKeeper] Sending chat message:` ✓
- `[ScoreKeeper] AI response:` ❌ (stuck here)

**Possible Causes:**
1. API timeout
2. Rate limit
3. Network issues

**Fix:**
```bash
# Test AI endpoint directly
curl -X POST http://localhost:8787/api/ai/chat \
  -H "Content-Type: application/json" \
  -H "x-scope: state" \
  -H "x-device-id: test" \
  -d '{
    "provider": "claude",
    "messages": [{"role": "user", "content": "test"}]
  }'

# Should return JSON with "message" field
```

### Issue 7: Response is Generic (not tournament-specific)

**Symptom:** AI doesn't reference tournaments or ratings

**Check:**
- Is context being sent? Look in console for:
  ```
  [ScoreKeeper] Context: {systemPrompt: "...", panel: "scorekeeper", ...}
  ```

**This is Expected If:**
- No tournament is active (context.current_tournament will be null)
- AI should still respond helpfully about creating tournaments

---

## 📊 Debugging Console Logs

### Expected Console Output (Success)

```javascript
// When you send "Hello":
[ScoreKeeper] Sending chat message: Hello
[ScoreKeeper] Context: {
  systemPrompt: "You are ScoreKeeper Sam...",
  panel: "scorekeeper",
  current_tournament: null,
  player_count: 8,
  leaderboard_size: 0
}
[ScoreKeeper] AI response: {
  id: "msg_123",
  provider: "claude",
  message: {
    role: "assistant",
    content: "Hey there! I'm ScoreKeeper Sam, your Tournament Commander..."
  },
  usage: {...}
}
[ScoreKeeper] Extracted text: Hey there! I'm ScoreKeeper Sam...
```

### Error Console Output

```javascript
// If API key missing:
[ScoreKeeper] AI chat error: Error: {...}
[ScoreKeeper] Error details: NOT_CONFIGURED NOT_CONFIGURED {code: 'NOT_CONFIGURED'}

// If network error:
[ScoreKeeper] AI chat error: TypeError: Failed to fetch
[ScoreKeeper] Error details: Failed to fetch undefined TypeError: Failed to fetch

// If CORS error:
Access to fetch at 'http://localhost:8787/api/ai/chat' has been blocked by CORS policy
```

---

## 🧪 Advanced Testing

### Test 1: Basic Chat Functionality
```
User: Hello
Expected: Greeting + tournament help offer
Time: < 3 seconds
```

### Test 2: Tournament Creation Guidance
```
User: I want to create a tournament
Expected: Asks for player count, suggests 4/8/16/32
User: 8 players
Expected: Asks about skill mix or creates tournament
```

### Test 3: Rating System Questions
```
User: What's Glicko-2?
Expected: Explanation of rating deviation + volatility
```

### Test 4: Context Awareness
```
1. Create tournament via UI (click "Create Custom Bracket")
2. Type: "What tournament am I in?"
Expected: References tournament name and status
```

### Test 5: Error Recovery
```
1. Disconnect internet
2. Type: "Hello"
Expected: Shows error in chat: "Chat error: ..."
3. Reconnect internet
4. Type: "Hello" again
Expected: AI responds normally
```

---

## 🔧 Manual API Test

If chat isn't working, test the AI endpoint directly:

```bash
# Test Claude (if ANTHROPIC_API_KEY set)
curl -X POST http://localhost:8787/api/ai/chat \
  -H "Content-Type: application/json" \
  -H "x-scope: state" \
  -H "x-device-id: test_001" \
  -d '{
    "provider": "claude",
    "messages": [
      {
        "role": "system",
        "content": "You are ScoreKeeper Sam. Be concise."
      },
      {
        "role": "user",
        "content": "Hello Sam"
      }
    ]
  }' | jq .

# Should return:
# {
#   "id": "msg_...",
#   "provider": "claude",
#   "message": {
#     "role": "assistant",
#     "content": "Hello! ..."
#   },
#   "usage": {...}
# }
```

---

## ✅ Success Checklist

- [ ] Dev stack running (`npm run dev`)
- [ ] API key set (check `.env`)
- [ ] Gateway responding (`curl localhost:8787/api/health`)
- [ ] Browser console open (F12)
- [ ] ScoreKeeper panel loaded (`localhost:8787/scorekeeper`)
- [ ] Chat button visible
- [ ] Chat sidebar opens on click
- [ ] Can type in input field
- [ ] "EXECUTE" button enabled when text entered
- [ ] Console shows logs when sending message
- [ ] AI response appears within 3 seconds
- [ ] Response is relevant to tournaments

---

## 📞 If Still Not Working

### Collect This Information:

1. **Console Logs:** Copy all `[ScoreKeeper]` messages
2. **Network Tab:** F12 → Network → filter "ai" → check failed requests
3. **Environment:**
   ```bash
   echo "API Keys set:"
   env | grep -E "ANTHROPIC|OPENAI"

   echo "Ports:"
   netstat -an | grep -E "8787|8888"
   ```
4. **Browser:** Chrome/Firefox/Edge version
5. **Error Message:** Exact text from chat or console

### Quick Fixes to Try:

```bash
# 1. Full restart
npm run dev

# 2. Clear browser cache
# Chrome: Ctrl+Shift+Del → Clear cached images and files

# 3. Check .env file
cat .env | grep ANTHROPIC

# 4. Restart just gateway
npm run dev:gateway

# 5. Check if different provider works
# In .env, try switching:
AI_DEFAULT_PROVIDER=gpt  # if you have OPENAI_API_KEY
```

---

**Last Updated:** 2025-10-28
**Status:** Debugging Guide
**Next:** Test chat and report specific error messages
