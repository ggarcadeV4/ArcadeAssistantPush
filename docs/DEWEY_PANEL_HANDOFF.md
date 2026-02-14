# Dewey Panel - AI Concierge Handoff Notes

**Session Date:** 2025-09-30
**Panel Owner:** Dewey (AI Assistant)
**Primary Function:** Intelligent agent router and conversation coordinator
**Status:** Ready for implementation (next session)

---

## Overview

The Dewey panel serves as the **central AI concierge** that routes user requests to the appropriate specialist agents. Unlike other panels that focus on specific tasks (games, LEDs, voice), Dewey acts as the **intelligent orchestrator** that understands user intent and delegates to the right agent.

---

## Core Responsibilities

### 1. **Intent Recognition**
- Parse natural language queries
- Identify which agent(s) should handle the request
- Route complex queries to multiple agents in sequence

### 2. **Agent Coordination**
- Display available agents and their capabilities
- Show agent status (online/busy/offline)
- Track conversation context across agent switches

### 3. **Conversation Management**
- Maintain chat history with agent attributions
- Allow users to switch between agents mid-conversation
- Preserve context when delegating between agents

### 4. **Quick Actions**
- Provide shortcuts for common tasks
- Enable direct agent invocation
- Suggest relevant agents based on user history

---

## UI/UX Requirements

### Layout Structure
```
┌─────────────────────────────────────────────────────┐
│  DEWEY PANEL                                        │
│  "Your AI Concierge"                          [🎤] │
├─────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐         │
│  │  Agent Cards    │  │  Chat Interface │         │
│  │  (Sidebar)      │  │  (Main Area)    │         │
│  │                 │  │                 │         │
│  │  ○ Vicky        │  │  💬 Messages    │         │
│  │  ○ LoRa         │  │                 │         │
│  │  ○ Chuck        │  │  [User input]   │         │
│  │  ○ Wiz          │  │                 │         │
│  │  ○ LED Blinky   │  │  ┌──────────┐  │         │
│  │  ○ Gunner       │  │  │Quick Acts│  │         │
│  │  ○ Sam          │  │  └──────────┘  │         │
│  │  ○ Doc          │  │                 │         │
│  └─────────────────┘  └─────────────────┘         │
└─────────────────────────────────────────────────────┘
```

### Component Breakdown

**1. Agent Status Sidebar**
- **8 Agent Cards** (Vicky, LoRa, Chuck, Wiz, LED Blinky, Gunner, Sam, Doc)
- Each card shows:
  - Avatar (48px circular)
  - Name + Role
  - Status indicator (online/busy/offline)
  - Capability tags
  - Click to invoke directly

**2. Chat Interface (Main Area)**
- **Message History** with agent attribution
  - User messages (right-aligned, cyan)
  - Agent responses (left-aligned, color-coded by agent)
  - Agent avatar next to each response
- **Input Bar** (bottom)
  - Text input field
  - Voice button (Dewey's custom mic)
  - Send button

**3. Quick Actions Panel**
- Floating action buttons for common tasks:
  - "Launch a game" → LoRa
  - "Adjust LEDs" → LED Blinky
  - "Configure controller" → Chuck
  - "System status" → Doc
  - "Check scores" → Sam

**4. Context Indicator**
- Shows current active agent context
- "Talking to LoRa about games..."
- "LED Blinky is adjusting your lights..."

---

## Agent Routing Logic

### Intent Detection Examples

| User Input | Detected Intent | Routed To | Reasoning |
|------------|----------------|-----------|-----------|
| "Launch Street Fighter II" | Game launch | LoRa | Game-related query |
| "My LEDs are too bright" | Hardware config | LED Blinky | LED mention |
| "What are my high scores?" | Stats query | Sam | Scores/stats mention |
| "Controller not working" | Hardware debug | Chuck | Controller mention |
| "Is the system healthy?" | System check | Doc | Health/status query |
| "Play a random fighting game" | Multi-agent | LoRa + Sam | Game + filter logic |

### Routing Algorithm (Simplified)
```javascript
function routeQuery(userMessage) {
  const keywords = {
    lora: ['game', 'launch', 'play', 'rom', 'emulator', 'launchbox'],
    ledBlinky: ['led', 'lights', 'blinky', 'brightness', 'color'],
    chuck: ['controller', 'joystick', 'button', 'input', 'mapping'],
    wiz: ['interface', 'ui', 'arcade', 'menu', 'navigation'],
    gunner: ['light gun', 'aim', 'calibrate', 'crosshair'],
    sam: ['score', 'high score', 'stats', 'leaderboard'],
    doc: ['health', 'status', 'diagnostic', 'error', 'problem'],
    vicky: ['voice', 'listen', 'hear', 'speak', 'session']
  }

  const message = userMessage.toLowerCase()
  const scores = {}

  for (const [agent, terms] of Object.entries(keywords)) {
    scores[agent] = terms.filter(term => message.includes(term)).length
  }

  const topAgent = Object.entries(scores)
    .sort((a, b) => b[1] - a[1])[0][0]

  return scores[topAgent] > 0 ? topAgent : 'dewey' // Default to self
}
```

---

## Data Models

### Agent Definition
```typescript
interface Agent {
  id: string              // 'lora', 'chuck', etc.
  name: string            // 'LaunchBox LoRa'
  role: string            // 'Game Library Assistant'
  avatar: string          // '/lora-avatar.jpeg'
  status: 'online' | 'busy' | 'offline'
  capabilities: string[]  // ['Game launching', 'Library search']
  panel: string           // '/assistants?agent=launchbox'
}
```

### Message Model
```typescript
interface Message {
  id: string
  role: 'user' | 'agent'
  text: string
  agentId?: string        // Which agent responded
  timestamp: Date
  context?: {
    routedTo: string[]    // Which agents were consulted
    confidence: number    // Routing confidence
  }
}
```

---

## Visual Design

### Color Scheme
- **Primary**: Cyan (#00e5ff) - Dewey's signature color
- **Agent Colors**: Each agent has color-coded messages
  - LoRa: Cyan/Pink gradient
  - LED Blinky: Purple
  - Chuck: Green
  - Gunner: Orange
  - Sam: Gold
  - Doc: Blue
  - Wiz: Violet
  - Vicky: Pink

### Animations
- **Agent card pulse** when receiving query
- **Typing indicator** with Dewey's avatar
- **Smooth transitions** when switching agent context
- **Glow effect** on active agent card

### Visual Polish (Match LoRa Quality)
- Floating particle background
- Gradient card backgrounds
- Shimmer effects on hover
- Smooth cubic-bezier transitions
- Color-coded agent avatars in chat

---

## API Integration

### Endpoints Needed
```
POST /api/ai/route
  Body: { message: string }
  Returns: { agentId: string, confidence: number }

POST /api/ai/chat
  Body: { message: string, agentId: string, context: object }
  Returns: { reply: string, agentId: string }

GET /api/agents/status
  Returns: { agents: Agent[] }
```

---

## Implementation Checklist

### Phase 1: Basic Structure
- [ ] Create `frontend/src/panels/dewey/DeweyPanel.jsx`
- [ ] Create `frontend/src/panels/dewey/dewey.css`
- [ ] Add routing to `Assistants.jsx`
- [ ] Integrate Dewey avatar (`/dewey-avatar.jpeg`)

### Phase 2: Agent Display
- [ ] Build agent status sidebar
- [ ] Create agent card components
- [ ] Implement status indicators
- [ ] Add click-to-invoke functionality

### Phase 3: Chat Interface
- [ ] Implement message history
- [ ] Add user input field
- [ ] Integrate voice button
- [ ] Color-code messages by agent

### Phase 4: Routing Logic
- [ ] Build keyword-based intent detection
- [ ] Create routing algorithm
- [ ] Implement multi-agent delegation
- [ ] Add confidence scoring

### Phase 5: Context Management
- [ ] Track conversation history
- [ ] Preserve context on agent switch
- [ ] Display active agent indicator
- [ ] Implement context suggestions

### Phase 6: Visual Polish
- [ ] Apply LaunchBox-style animations
- [ ] Add particle background
- [ ] Implement agent card glows
- [ ] Create smooth transitions

---

## Example Conversations

### Example 1: Single Agent
```
User: "Launch Mortal Kombat II"
Dewey: "I'll route this to LoRa, our game library specialist."
[LoRa avatar appears]
LoRa: "Launching Mortal Kombat II (1993, Fighting)..."
```

### Example 2: Multi-Agent
```
User: "Show me fighting games from the 90s"
Dewey: "This requires LoRa for game filtering and Sam for stats."
[LoRa avatar + Sam avatar appear]
LoRa: "Found 12 fighting games from the 1990s."
Sam: "Most played: Street Fighter II (47 sessions)"
```

### Example 3: Clarification
```
User: "The lights are wrong"
Dewey: "Do you mean LED Blinky (cabinet lights) or Gunner (light gun calibration)?"
User: "Cabinet lights"
[LED Blinky avatar appears]
LED Blinky: "I can help with that. What specifically needs adjustment?"
```

---

## Success Criteria

### Must Have:
- ✅ Display all 8 agents with status
- ✅ Chat interface with message history
- ✅ Basic intent routing (keyword-based)
- ✅ Agent-attributed responses
- ✅ Click-to-invoke agent cards

### Should Have:
- ✅ Multi-agent coordination
- ✅ Context preservation
- ✅ Quick action shortcuts
- ✅ Visual polish matching LoRa

### Nice to Have:
- AI-powered intent classification (vs keyword)
- Voice command routing
- Agent learning/history
- Suggested follow-up actions

---

## Technical Notes

### Dependencies
- Panel Kit (`PanelShell`, `useAIAction`)
- All 8 agent avatars
- Existing AI chat integration (`/api/ai/chat`)

### Performance Considerations
- Cache agent status (don't poll excessively)
- Debounce routing requests
- Virtualize message history for long conversations
- Lazy-load agent panel components

### Accessibility
- ARIA labels for all agent cards
- Keyboard navigation for agent selection
- Screen reader support for message history
- Focus management on agent switch

---

## Files to Reference

**Existing Panels:**
- `frontend/src/panels/voice/VoicePanel.jsx` - Chat interface pattern
- `frontend/src/panels/launchbox/LaunchBoxPanel.jsx` - Visual polish reference
- `frontend/src/panels/_kit/` - Reusable components

**Assets:**
- `/dewey-avatar.jpeg` - Dewey's avatar (cyan holographic robot)
- `/dewey-mic.png` - Custom microphone (needs creation)

**Documentation:**
- `agents/AGENT_CALL_MATRIX.md` - Agent delegation rules
- `CLAUDE.md` - Panel development patterns
- `docs/A_DRIVE_ARCHITECTURE.md` - Backend integration

---

**Ready for Implementation:** YES
**Estimated Complexity:** Medium
**Estimated Time:** 1-2 hours (with fresh context)
**Recommended Approach:** Build chat-first, add routing second, polish last

---

_End of Handoff Document_
